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


def fake_transport(choices):
    """Stub transport for unit tests of splitting and aggregation; not evidence of Jev behavior."""
    defaults = {"artifact_gate": "none", "capability_share": "capability",
                "gate_weakening": "no", "follow_up_laundering": "no", "meta_trap": "no"}

    def transport(body, key):
        request = json.loads(body)
        return {"model": jc.MODEL, "answers": {
            qid: answer(choices.get(qid, defaults[qid]), list(q["criteria"]))
            for qid, q in request["questions"].items()}}

    return transport


class SplitTests(unittest.TestCase):
    def test_heading_paths_and_fenced_hashes(self):
        text = "intro\n# A\none\n## B\n```\n# not a heading\n```\n# C\nthree\n"
        paths = [s["path"] for s in jc.split_sections(text)]
        self.assertEqual(paths, ["(preamble)", "A", "A > B", "C"])

    def test_heading_only_sections_are_skipped(self):
        paths = [s["path"] for s in jc.split_sections("# Title\n## Sub\nbody\n")]
        self.assertEqual(paths, ["Title > Sub"])

    def test_oversize_section_is_split_without_dropping_text(self):
        paragraphs = [f"paragraph {i} " + "x" * 3000 for i in range(20)]
        text = "# Big\n\n" + "\n\n".join(paragraphs)
        fitted = jc.fit_sections("doc.md", jc.split_sections(text))
        self.assertGreater(len(fitted), 1)
        for s in fitted:
            self.assertLessEqual(len(jc.encode(jc.build_request("doc.md", s))), jc.MAX_REQUEST_BYTES)
            self.assertRegex(s["path"], r"^Big \(part \d+/\d+\)$")
        joined = "\n\n".join(s["text"] for s in fitted)
        for p in paragraphs:
            self.assertIn(p, joined)

    def test_unsplittable_line_is_refused(self):
        with self.assertRaises(jc.JevError) as ctx:
            jc.fit_sections("doc.md", [{"path": "A", "text": "y" * 30000}])
        self.assertEqual(ctx.exception.code, "JEV.INCONCLUSIVE")


class VerdictTests(unittest.TestCase):
    def run_doc(self, text, choices):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "plan.md"
            path.write_text(text, encoding="utf-8")
            return jc.run(path, transport=fake_transport(choices), key="k")

    def test_clean(self):
        result = self.run_doc("# A\nship the parser\n", {"artifact_gate": "none"})
        self.assertEqual(result["verdict"], "clean")

    def test_unjustified_artifact_flags_ceremony(self):
        result = self.run_doc("# A\nadd a readiness ledger\n# B\nship it\n", {"artifact_gate": "unjustified"})
        self.assertEqual(result["verdict"], "ceremony")
        self.assertEqual(result["results"][0]["flags"], ["artifact_gate"])

    def test_process_share_alone_is_not_ceremony(self):
        result = self.run_doc("# A\nreview cadence\n", {"capability_share": "process"})
        self.assertEqual(result["verdict"], "clean")
        self.assertEqual(result["results"][0]["answers"]["capability_share"]["choice"], "process")

    def test_insufficient_needs_context(self):
        result = self.run_doc("# A\nTBD\n", {"artifact_gate": "insufficient"})
        self.assertEqual(result["verdict"], "needs_context")

    def test_invalid_response_is_rejected(self):
        request = jc.build_request("d", {"path": "A", "text": "t"})
        with self.assertRaises(jc.JevError):
            jc.evaluate(request, "k", transport=lambda body, key: {"model": jc.MODEL, "answers": {}})


if __name__ == "__main__":
    unittest.main()
