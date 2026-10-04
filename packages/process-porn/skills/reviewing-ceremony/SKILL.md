---
name: reviewing-ceremony
version: 0.1.0
description: >
  Find exactly what to remove or fix in sprint plans (md files or beads), CI workflows,
  and agent instructions (CLAUDE.md, AGENTS.md, skills, agent prompts) with the TypeSafe Jev agent.
  Use when asked to review a plan, CI or instructions for process porn, ceremony, ungated process
  artifacts, narration, redundant or report-only CI jobs, or weakened gates.
---

# Reviewing Ceremony

## Step 1: Verify python3 and the API key

```bash
which python3 && python3 --version
[ -n "$TYPESAFE_API_KEY" ] && echo "TYPESAFE_API_KEY set" || echo "TYPESAFE_API_KEY missing"
```

python3 must be 3.9 or later.

If python3 isn't on PATH, look in `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin` and `~/.pyenv/shims`. If it's there, export that directory onto PATH for this session.

If python3 is still missing, or the key is unset, read `references/installation-and-troubleshooting.md` and stop. Never continue in a degraded mode. Each category reference lists any further CLIs it needs.

## Step 2: Route by category

| Category | Reviewed | Reference | Agent |
|---|---|---|---|
| `plan` | sprint plans: md files, or sprint beads | `references/plan.md` | `ceremony-review` |
| `ci` | CI workflow files | `references/ci.md` | `ceremony-review` |
| `instructions` | CLAUDE.md, AGENTS.md, skills, agent prompts | `references/instructions.md` | `ceremony-review` |

Read only the matching reference. It defines:
- the inputs;
- the context to collect and how to collect it;
- the context file format;
- how to read the results.

A request that spans categories runs once per category.

## Agent Delegation

Invoke `ceremony-review` with the Task tool, passing these parameters:
- `category`;
- `reference`: the absolute path of the matching reference;
- `inputs`;
- any options the reference names.

The agent collects the context, runs the script once per run the reference calls for, and returns fenced JSON:
- per unit, the `remove`, `fix` and `needs_context` lists, each entry with `where`, `lines`, `reason`, `probability` and `text`, plus `kept`;
- `totals`;
- `context_file`, the context it sent.

Treat unfenced or malformed JSON as a failure.

## Step 3: Report, then apply on request

- Show `totals`, then one line per remove or fix: unit, `where`, lines and reason. List `needs_context` separately as unscored.
- Apply changes only when the user asks.
  - **remove:** delete the item's lines, working from the bottom of the file up so the line numbers stay valid. Then fix any reference or numbering the deletion broke.
  - **fix:** change the item so the gate holds. Don't delete it.
  - Leave `needs_context` items unchanged.
- On `success: false`, report `error.code`, `message` and `suggested_action`. Don't substitute your own judgment as a Jev result.
