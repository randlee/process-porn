---
name: jev-ceremony-check
description: Score a plan, sprint doc or other markdown document for unnecessary process and ceremony with the TypeSafe Jev agent. Use when asked to check a document for process porn, ceremony, ungated process artifacts, gate weakening, follow-up laundering or governance loops.
---

# jev-ceremony-check

Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/jev-ceremony-check/scripts/jev_ceremony.py" <document.md>
```

This needs `TYPESAFE_API_KEY` in the environment. `--dry-run` prints the sections and request sizes without calling Jev. `--minimum-probability` (default 0.8) sets the confidence below which an answer counts as `needs_context`.

## What it does

1. Splits the document on markdown headings. Any section whose request would exceed 24,000 bytes is split again on paragraphs, then on lines, and its parts are labelled `(part i/n)`. Nothing is dropped. A single line over the limit is refused with `JEV.INCONCLUSIVE`.
2. Sends each section to Jev with the ceremony rules (the `RULES` constant) and five Choice questions:

   | id | Flags on |
   |---|---|
   | `artifact_gate` | a process artifact without consumer, gate, observed defect and retirement |
   | `capability_share` | nothing; informational (a rules document is process by nature) |
   | `gate_weakening` | weakened or self-certified tests or gates, or mocks as live proof |
   | `follow_up_laundering` | in-scope acceptance moved to follow-ups so the original can close |
   | `meta_trap` | review or governance rounds about the process apparatus itself |

3. Computes the verdict in code:
   - a section is `ceremony` if any answer flags it;
   - otherwise it is `needs_context` if any answer is `insufficient` or below the minimum probability;
   - otherwise it is `clean`.

   The document verdict is the worst section verdict.

## Output and exit codes

The output is JSON: `{"success", "data": {"verdict", "sections", "counts", "results": [...]}, "error"}`. Each result gives the section path, its status, the flagged question ids, the low-confidence ids, and each choice with its probability.

| Exit code | Meaning |
|---|---|
| 0 | clean or `needs_context` |
| 1 | ceremony |
| 2 | error; no verdict |

## Reporting

- Report each flagged section with its path and the flagged question ids.
- A `needs_context` section is unscored. Don't count it as clean.
- An error means no evaluation ran. Report its code and message, and don't substitute your own judgment as a Jev result.
