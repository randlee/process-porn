import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import jev_ceremony as jc  # noqa: E402


def answer(choice, options, p=0.9):
    rest = (1 - p) / (len(options) - 1)
    return {"type": "choice", "choice": choice, "confidence": p,
            "probabilities": {o: (p if o == choice else rest) for o in options}}


def stub(pick, p=0.9):
    """Stub transport for unit tests of extraction, packing and reporting; not evidence of Jev behavior.

    pick(item_text) returns the choice for that item."""
    def transport(body, key):
        request = json.loads(body)
        items = request["state"]["items"]
        return {"model": jc.MODEL, "answers": {
            qid: answer(pick(items[qid]["text"]), list(q["criteria"]), p) for qid, q in request["questions"].items()}}
    return transport


PLAN = """# s-1: parser

## Goal

Ship the parser.

## Deliverables

1. Parse the config file
   into typed settings.
2. Create a readiness ledger signed by every reviewer.

| Check | Owner |
|---|---|
| unit tests | dev |

```rust
fn parse() {}
```
"""

WORKFLOW = """name: ci
on: [pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: Test
        run: cargo test
  summary:
    runs-on: ubuntu-latest
    steps:
      - name: Post summary
        run: echo done >> $GITHUB_STEP_SUMMARY
"""


class MarkdownTests(unittest.TestCase):
    def test_items_paths_and_lines(self):
        items = jc.md_items(PLAN.splitlines())
        got = [(i["kind"], i["start"], i["end"], i["path"]) for i in items]
        self.assertEqual(got, [
            ("paragraph", 5, 5, "s-1: parser > Goal"),
            ("list_item", 9, 10, "s-1: parser > Deliverables"),
            ("list_item", 11, 11, "s-1: parser > Deliverables"),
            ("table_row", 15, 15, "s-1: parser > Deliverables"),
            ("code", 17, 19, "s-1: parser > Deliverables"),
        ])
        self.assertIn("| Check | Owner |", items[3]["text"])

    def test_sprint_level_splits_units_and_keeps_line_numbers(self):
        text = "# Phase\nintro\n## s-1\none\n## s-2\ntwo\n"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "plan.md"
            path.write_text(text)
            units = jc.md_units(path, "plan", sprint_level=2)
        self.assertEqual([u["title"] for u in units], ["Phase", "s-1", "s-2"])
        self.assertEqual(units[2]["items"][0]["start"], 6)

    def test_plan_context_has_goal_and_deliverables(self):
        context = jc.plan_context(PLAN.splitlines())
        self.assertIn("Ship the parser.", context)
        self.assertIn("readiness ledger", context)

    def test_bead_unit_tags_fields(self):
        unit = jc.plan_unit_from_bead({"id": "x-1", "title": "t", "description": "Do it.", "acceptance_criteria": "- tests pass"})
        self.assertEqual([(i["field"], i["path"]) for i in unit["items"]],
                         [("description", "description > (preamble)"), ("acceptance_criteria", "acceptance_criteria > (preamble)")])


class BeadInputTests(unittest.TestCase):
    def write(self, d, value):
        path = Path(d) / "beads.json"
        path.write_text(json.dumps(value))
        return path

    def test_bare_list_and_wrapped_object(self):
        bead = {"id": "x-1", "title": "t", "issue_type": "feature", "description": "Do it.", "metadata": {"branch": "b"}}
        with tempfile.TemporaryDirectory() as d:
            for value in ([bead], {"source": "br", "beads": [bead]}):
                self.assertEqual([b["id"] for b in jc.load_beads(self.write(d, value))], ["x-1"])
        unit = jc.plan_unit_from_bead(bead)
        self.assertIn("Metadata keys: branch", unit["context"])

    def test_bad_shapes_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for value in ([], {"beads": []}, [{"title": "no id"}], [{"id": "x", "design": ["not", "text"]}]):
                with self.assertRaises(jc.JevError):
                    jc.load_beads(self.write(d, value))

    def test_beads_json_excludes_paths(self):
        args = jc.argparse.Namespace(situation="plan", inputs=["a.md"], beads_json="-", sprint_level=None, context=None, scope=None, root=".")
        with self.assertRaises(jc.JevError):
            jc.load_units(args)


class CiTests(unittest.TestCase):
    def test_header_jobs_and_steps(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ci.yml"
            path.write_text(WORKFLOW)
            unit = jc.ci_unit(path, jc.ci_inventory([path]))
        got = [(i["path"], i["start"], i["end"]) for i in unit["items"]]
        self.assertEqual(got, [
            ("workflow header", 1, 3), ("jobs.test", 4, 6),
            ("jobs.test.steps[0] actions/checkout@v5", 7, 7), ("jobs.test.steps[1] Test", 8, 9),
            ("jobs.summary", 10, 12), ("jobs.summary.steps[0] Post summary", 13, 14),
        ])
        self.assertIn("ci.yml test: Test", unit["context"])
        self.assertNotIn("checkout", unit["context"].split("All reviewed jobs:")[1])


class ScopeTests(unittest.TestCase):
    def tree(self, d):
        root = Path(d) / "repo"
        (root / ".claude/skills/s/references").mkdir(parents=True)
        (root / ".claude/agents").mkdir()
        for rel in ("CLAUDE.md", ".claude/skills/s/SKILL.md", ".claude/skills/s/references/r.md", ".claude/agents/a.md", ".claude/skills/s/x.py"):
            (root / rel).write_text("# t\nline\n")
        return root

    def args(self, root, scope, inputs=()):
        return jc.argparse.Namespace(situation="instructions", inputs=list(inputs), beads_json=None, sprint_level=None,
                                     context=None, scope=scope, root=str(root))

    def test_local_scope_finds_instruction_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tree(d)
            names = sorted(str(p.relative_to(root)) for p in jc.instruction_files("local", root))
        self.assertEqual(names, [".claude/agents/a.md", ".claude/skills/s/SKILL.md", ".claude/skills/s/references/r.md", "CLAUDE.md"])

    def test_scope_required_and_inputs_must_be_inside(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tree(d)
            with self.assertRaises(jc.JevError):
                jc.load_units(self.args(root, None))
            outside = Path(d) / "other.md"
            outside.write_text("x\n")
            with self.assertRaises(jc.JevError):
                jc.load_units(self.args(root, "local", [outside]))
            self.assertEqual(len(jc.load_units(self.args(root, "local", [root / "CLAUDE.md"]))), 1)


class PackingTests(unittest.TestCase):
    def unit(self, texts):
        return {"id": "u", "title": "u", "source": "u", "context": "c",
                "items": [{"path": "p", "kind": "paragraph", "start": n, "end": n, "text": t} for n, t in enumerate(texts, 1)]}

    def test_batches_fit_and_cover_every_item(self):
        unit = self.unit([f"item {n} " + "x" * 2500 for n in range(30)])
        out = jc.batches("plan", unit)
        self.assertGreater(len(out), 1)
        for batch in out:
            self.assertLessEqual(len(jc.encode(jc.build_request("plan", unit, batch))), jc.MAX_REQUEST_BYTES)
            self.assertLessEqual(len(batch), jc.MAX_QUESTIONS)
        self.assertEqual(sorted(i["start"] for b in out for i in b), list(range(1, 31)))

    def test_oversize_item_split_on_lines(self):
        unit = self.unit(["\n".join("line " + "y" * 200 for _ in range(150))])
        parts = [i for b in jc.batches("plan", unit) for i in b]
        self.assertGreater(len(parts), 1)
        self.assertEqual("\n".join(i["text"] for i in parts), unit["items"][0]["text"])

    def test_unsplittable_line_refused(self):
        with self.assertRaises(jc.JevError):
            jc.batches("plan", self.unit(["z" * 30000]))


class CallerContextTests(unittest.TestCase):
    def test_context_reaches_every_request(self):
        with tempfile.TemporaryDirectory() as d:
            doc, ctx = Path(d) / "s.md", Path(d) / "ctx.md"
            doc.write_text(PLAN)
            ctx.write_text("scripts/dispatch.py reads Branch:")
            args = jc.argparse.Namespace(situation="plan", inputs=[doc], beads_json=None, sprint_level=None, context=ctx, scope=None, root=".")
            unit = jc.load_units(args)[0]
        for batch in jc.batches("plan", unit):
            self.assertEqual(jc.build_request("plan", unit, batch)["state"]["caller_context"], "scripts/dispatch.py reads Branch:")

    def test_oversize_context_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = Path(d) / "ctx.md"
            ctx.write_text("x" * (jc.CALLER_CONTEXT_BYTES + 1))
            with self.assertRaises(jc.JevError):
                jc.load_caller_context(ctx)


class ReportTests(unittest.TestCase):
    def test_plan_report_lists_findings_by_pattern(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.md"
            path.write_text(PLAN)
            unit = jc.md_units(path, "plan")[0]
        pick = lambda t: "ungated_artifact" if "ledger" in t else "gate_weakening" if "unit tests" in t else "capability"
        report = jc.review_unit("plan", unit, "k", stub(pick))
        self.assertEqual([(e["lines"], e["pattern"]) for e in report["findings"]],
                         [([11, 11], "ungated_artifact"), ([15, 15], "gate_weakening")])
        self.assertEqual(report["clear"], 3)
        self.assertEqual(report["uncertain"], [])

    def test_low_probability_is_uncertain_with_leaning(self):
        unit = PackingTests().unit(["a"])
        report = jc.review_unit("instructions", unit, "k", stub(lambda t: "narration", p=0.5))
        self.assertEqual(report["findings"], [])
        entry = report["uncertain"][0]
        self.assertEqual(entry["pattern"], "narration")
        self.assertIn("clear_probability", entry)

    def test_classify_sums_groups(self):
        probs = {"capability": 0.45, "justified_process": 0.4, "narration": 0.1, "gate_weakening": 0.05,
                 "ungated_artifact": 0.0, "meta_review": 0.0, "follow_up_laundering": 0.0, "insufficient": 0.0}
        groups = jc.classify("plan", probs)
        self.assertAlmostEqual(groups["clear"], 0.85)
        self.assertAlmostEqual(groups["pattern"], 0.15)

    def test_every_clear_option_is_a_criterion(self):
        for name, spec in jc.SITUATIONS.items():
            self.assertTrue(set(spec["clear"]) < set(spec["criteria"]), name)

    def test_invalid_response_names_the_problem(self):
        bad = answer("gate", list(jc.SITUATIONS["ci"]["criteria"]))
        bad["probabilities"]["gate"] = 0.5
        self.assertRegex(jc.answer_problem(bad, set(jc.SITUATIONS["ci"]["criteria"])), "sum to")

    def test_two_decimal_rounding_is_accepted(self):
        options = list(jc.SITUATIONS["ci"]["criteria"])
        ok = answer("gate", options)
        ok["probabilities"] = dict.fromkeys(options, 0.0) | {"gate": 0.94, "support": 0.05}
        self.assertIsNone(jc.answer_problem(ok, set(options)))

    def test_invalid_response_rejected(self):
        unit = PackingTests().unit(["a"])
        with self.assertRaises(jc.JevError):
            jc.review_unit("ci", unit, "k", lambda body, key: {"model": jc.MODEL, "answers": {}})


if __name__ == "__main__":
    unittest.main()
