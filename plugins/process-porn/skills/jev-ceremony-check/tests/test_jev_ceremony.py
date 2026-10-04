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


class ReportTests(unittest.TestCase):
    def test_plan_report_routes_actions(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.md"
            path.write_text(PLAN)
            unit = jc.md_units(path, "plan")[0]
        pick = lambda t: "remove_ungated_artifact" if "ledger" in t else "fix_gate_weakening" if "unit tests" in t else "keep_capability"
        report = jc.review_unit("plan", unit, "k", stub(pick))
        self.assertEqual([(e["lines"], e["reason"]) for e in report["remove"]], [([11, 11], "remove_ungated_artifact")])
        self.assertEqual([e["lines"] for e in report["fix"]], [[15, 15]])
        self.assertEqual(report["kept"], 3)

    def test_low_probability_needs_context(self):
        unit = PackingTests().unit(["a"])
        report = jc.review_unit("instructions", unit, "k", stub(lambda t: "remove_narration", p=0.5))
        self.assertEqual(len(report["needs_context"]), 1)
        self.assertEqual(report["remove"], [])

    def test_decide_sums_probability_within_an_action_group(self):
        probs = {"keep_capability": 0.45, "keep_justified_process": 0.4, "remove_narration": 0.15, "insufficient": 0.0}
        action, reason, prob = jc.decide(probs)
        self.assertEqual((action, reason), ("keep", "keep_capability"))
        self.assertAlmostEqual(prob, 0.85)

    def test_invalid_response_names_the_problem(self):
        bad = answer("keep_gate", list(jc.SITUATIONS["ci"]["criteria"]))
        bad["probabilities"]["keep_gate"] = 0.5
        self.assertRegex(jc.answer_problem(bad, set(jc.SITUATIONS["ci"]["criteria"])), "sum to")

    def test_two_decimal_rounding_is_accepted(self):
        options = list(jc.SITUATIONS["ci"]["criteria"])
        ok = answer("keep_gate", options)
        ok["probabilities"] = dict.fromkeys(options, 0.0) | {"keep_gate": 0.94, "keep_support": 0.05}
        self.assertIsNone(jc.answer_problem(ok, set(options)))

    def test_invalid_response_rejected(self):
        unit = PackingTests().unit(["a"])
        with self.assertRaises(jc.JevError):
            jc.review_unit("ci", unit, "k", lambda body, key: {"model": jc.MODEL, "answers": {}})


if __name__ == "__main__":
    unittest.main()
