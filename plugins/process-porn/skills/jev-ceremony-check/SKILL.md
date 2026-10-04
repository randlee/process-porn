---
name: jev-ceremony-check
description: Find exactly what to remove or fix in sprint plans (md files or beads), CI workflows, and agent instructions (CLAUDE.md, AGENTS.md, skills, agent prompts) with the TypeSafe Jev agent. Use when asked to review any of these for process porn, ceremony, ungated process artifacts, narration, redundant or report-only CI, or gate weakening.
---

# jev-ceremony-check

```bash
J="${CLAUDE_PLUGIN_ROOT}/skills/jev-ceremony-check/scripts/jev_ceremony.py"
python3 "$J" plan docs/plans/phase-x/sprint-*.md        # one sprint per file
python3 "$J" plan plan.md --sprint-level 2              # each H2 starts a sprint
python3 "$J" plan --beads <sprint-bead-id>...           # read with `bd show <id> --json`
python3 "$J" ci .github/workflows/*.yml                 # pass every workflow, so redundancy is visible
python3 "$J" instructions CLAUDE.md AGENTS.md .claude/skills/*/SKILL.md .claude/agents/*.md
```

This needs `TYPESAFE_API_KEY` in the environment.
- `--dry-run` prints the units, item counts and request sizes without calling Jev.
- `--minimum-probability` (default 0.8) sets the confidence below which an item goes to `needs_context`.

## Routing

- **Unit:** one sprint, one workflow file, or one instruction file. Each unit is reviewed on its own.
- **Item:** one Choice question per item. For markdown, an item is a list item with its continuation lines, a paragraph, a table row (with its header) or a code block. For a workflow, it's the header, one job, or one step.
- **Context**, repeated in every request for the unit:

  | Situation | Context |
  |---|---|
  | plan | heading outline plus the goal, deliverables and scope sections |
  | ci | the workflow's header plus every reviewed job with its non-setup steps |
  | instructions | heading outline plus the text before the first H2 |

  For beads, the context is the title, the field outlines and the description.
- **Packing:** items go into requests of at most 12 questions and 24,000 bytes. An item too large on its own is split on lines into `a`/`b` parts. Nothing is dropped.

## Report

Each unit gets `remove`, `fix` and `needs_context` lists, plus a `kept` count.
- Every entry gives `where` (heading path or job/step), `lines` (1-based, inclusive; for beads, within `field`), `reason`, `probability` and `text`.
- The action is the group (keep, remove or fix) with the highest summed probability. The reason is the top option within that group.

| Exit code | Meaning |
|---|---|
| 0 | nothing to remove or fix |
| 1 | at least one remove or fix |
| 2 | error; no review ran |

## Applying it

- **remove:** delete the item's lines. Then re-read the surrounding text, and fix any reference or numbering the deletion broke.
- **fix:** change the item so the gate holds, for example by dropping `continue-on-error` or restoring the in-scope acceptance. Don't delete it.
- **needs_context:** leave it unchanged and list it in your report.
- Report every change with its unit, lines and reason.
- An error means no review ran. Report the code and message, and don't substitute your own judgment as a Jev result.
