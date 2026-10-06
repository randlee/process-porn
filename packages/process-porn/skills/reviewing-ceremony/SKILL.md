---
name: reviewing-ceremony
version: 0.2.0
description: >
  Locate likely ceremony in sprint plans (md files or beads), CI workflows, and agent instructions
  (CLAUDE.md, AGENTS.md, skills, agent prompts) with the TypeSafe Jev agent, item by item.
  Use when asked to review a plan, CI or instructions for process porn, ceremony, ungated process
  artifacts, narration, redundant or report-only CI jobs, or weakened gates.
---

# Reviewing Ceremony

Jev classifies every item of a plan, workflow or instruction file against a fixed set of ceremony patterns, so you can quickly locate the items that need a closer look. Each finding gives the item's location, the pattern Jev matched and how likely the match is. You then review the findings against the repo's own guidelines and give your recommendations.

## Step 1: Verify python3 and the API key

```bash
which python3 && python3 --version
[ -n "$TYPESAFE_API_KEY" ] && echo "TYPESAFE_API_KEY set" || echo "TYPESAFE_API_KEY missing"
```

python3 must be 3.9 or later.

If python3 isn't on PATH, look in `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin` and `~/.pyenv/shims`. If it's there, export that directory onto PATH for this session.

If python3 is still missing, or the key is unset, read `references/installation-and-troubleshooting.md` and stop. Never continue in a degraded mode. Each category reference lists any further CLIs it needs.

## Step 2: Route by category

| Category | Reviewed | Reference |
|---|---|---|
| `plan` | sprint plans in md files | `references/plan.md` |
| `plan` (beads) | sprint beads, from `bd` or `br` | `references/plan-beads.md` |
| `ci` | CI workflow files | `references/ci.md` |
| `instructions` | CLAUDE.md, AGENTS.md, skills, agent prompts | `references/instructions.md` |

If a plan exists both as md and as beads, review the copy the repo treats as the source. Read only the matching reference. A request that spans categories runs once per category.

In Claude Code, invoke the `ceremony-review` agent with the Task tool. Where no such agent is available, as in Codex, follow `../../agents/ceremony-review.md` (relative to this skill's directory) yourself. Pass:
- `category`;
- `reference`: the absolute path of the matching reference;
- `inputs`;
- any options the reference names, such as the `instructions` scope;
- `max_requests`: optional, default 100;
- `script`: `../../scripts/jev_ceremony.py` resolved against this skill's directory, as an absolute path.

The agent sizes the run first. If it needs more Jev requests than `max_requests`, the agent returns the size per unit without running. Report it, then narrow the inputs or raise `max_requests` as the user decides. Otherwise the agent collects the context the reference describes, runs the script, and returns fenced JSON. Treat unfenced or malformed JSON as a failure.

## Step 3: Review the findings

The result has, per unit:
- `findings`: items whose pattern probability reached the threshold (0.8). Each has `where`, `lines`, `pattern` (the top pattern), `pattern_probability` (the sum over all patterns), `patterns` (each pattern's own probability, rounded, listing only those at 0.05 or more, so the values need not add up to `pattern_probability`) and the start of `text`. Bead findings also have `field`.
- `uncertain`: items that reached the threshold neither as a pattern nor as clear. They carry the same fields plus `clear_probability` and `insufficient_probability`.
- `clear`: the count of items Jev classified as clear.

`data.context_file` is the context Jev saw. The reference's "Reading results" section says what each pattern means for that category and which fact settles it.

For each finding, read the full item at its location and check it against:
- the item's surroundings;
- the facts in `context_file`;
- the repo's own guidelines (CLAUDE.md, AGENTS.md, team docs).

Report, per unit:
- each finding: location, Jev's pattern and probability, your assessment, and your recommendation. Say where you disagree with Jev, and why;
- the `uncertain` items whose `pattern` you would look at, with Jev's leaning;
- the counts: findings, uncertain, clear, and any input you set aside, with why.

On `success: false`, report `error.code`, `message` and `suggested_action`. Don't substitute your own judgment for a Jev result.
