# process-porn

Locate process porn and ceremony in sprint plans, CI workflows and agent instructions, item by item, with the [TypeSafe](https://typesafe.ai) **Jev** agent.

Agents (and teams) accrete process: ledgers nobody reads, review rounds about the review process, CI jobs that re-run other jobs, rules restated in three files, gates quietly turned report-only. The author of that process is the worst judge of it. This plugin hands every item to Jev, an independent classifier, together with facts the calling agent collects from the repo, and returns the exact locations that match a ceremony pattern. Your agent then reviews those findings against your repo's own guidelines and makes its recommendations.

> **A TypeSafe API key is required.** Set `TYPESAFE_API_KEY` in the environment that launches Claude Code or Codex. Get a key at [typesafe.ai](https://typesafe.ai). The reviewed text is sent to the TypeSafe API (`api.typesafe.ai`) for classification.

## Availability

| Client | Marketplace | Install |
|---|---|---|
| Claude Code | this repo (`.claude-plugin/marketplace.json`) | `/plugin marketplace add randlee/process-porn`<br>`/plugin install process-porn@process-porn` |
| Codex | this repo (`.agents/plugins/marketplace.json`) | `codex plugin marketplace add randlee/process-porn`<br>`codex plugin add process-porn@process-porn` |

Both install the same package, `packages/process-porn`: the `reviewing-ceremony` skill, its references, the `jev_ceremony.py` script and, for Claude Code, the `ceremony-review` agent. Under Codex, which has no plugin subagents, the skill runs the agent's steps itself.

## Requirements

| Need | For | Notes |
|---|---|---|
| `TYPESAFE_API_KEY` | every review | Never printed or returned by the skill. Under Codex, make sure the shell environment policy passes it through (`[shell_environment_policy]` in `~/.codex/config.toml`). |
| python3 3.9+ | every review | Standard library only. |
| `gh`, authenticated | `ci` | Reads branch rules and required checks. Read-only. |
| `bd` ([beads](https://github.com/steveyegge/beads)) or `br` ([beads_rust](https://github.com/Dicklesworthstone/beads_rust)) | `plan` from beads | Read-only `show` and `list`. |

## Usage

Ask your agent in plain language, for example:

- "Review the sprint plans in `docs/plans/phase-3/` for ceremony."
- "Review the sprint beads under `proj-40` for ceremony."
- "Review our CI workflows for ceremony."
- "Review the local CLAUDE.md, skills and agents for ceremony."

In Codex you can also name the skill: `$reviewing-ceremony`.

## Review modes

The skill routes by category. Each category has a reference that says what to pass, which facts to collect from the repo for Jev, and how to read the results.

### Plan, markdown files

- **Reviewed:** sprint plans in md files, one sprint per file, or several sprints in one file split at a heading level (`--sprint-level N`).
- **Items:** list items, paragraphs, table rows (with their header) and code blocks, each with its heading path and line range.
- **Context collected:** the phase goal; which tools actually parse each plan field; fields the sprint's bead already holds; whether out-of-scope owners exist; whether CI runs each validation command.
- **Patterns:** `narration`, `ungated_artifact`, `meta_review`, `gate_weakening`, `follow_up_laundering`.

### Plan, beads

- **Reviewed:** sprint beads from `bd` or `br`, piped as JSON (`show <ids...> --json`). Only the beads that describe a sprint's work; sanity, QA and review siblings are set aside and reported.
- **Items:** the `description`, `design`, `acceptance_criteria` and `notes` fields, item by item; each finding names its `field`. Metadata keys (bd) go to Jev as context.
- **Context collected:** as for markdown plans, with metadata keys in place of plan labels.
- **Patterns:** as for markdown plans.

### CI

- **Reviewed:** every GitHub Actions workflow in `.github/workflows/` (`.yml` and `.yaml`) together, so duplication across workflows is visible.
- **Items:** the workflow header, each job, each step.
- **Context collected:** required checks (or what else gates merges); callers of reusable and manual workflows; artifact consumers; release `needs:` and duplicated commands; steps that continue on error and the later steps that fail the job on their outcomes; stated CI policy.
- **Patterns:** `redundant`, `report_only`, `unconsumed_check`, `gate_weakening`.

### Instructions

- **Reviewed:** CLAUDE.md, AGENTS.md, every skill markdown file (`SKILL.md` and its references) and every agent prompt, in a scope you must choose:

  | Scope | Roots |
  |---|---|
  | `local` | the repository's `CLAUDE.md`, `AGENTS.md`, `.claude/skills/`, `.claude/agents/` |
  | `global` | `~/.claude` |
  | `both` | both; a file reached through both by symlink is reviewed once |

- **Items:** as for markdown plans.
- **Context collected:** who loads each file; rules a hook or script already enforces; other files loaded in the same session (to spot restatement); whether referenced paths, skills and agents exist.
- **Patterns:** `narration`, `ungated_artifact`, `meta_review`, `gate_weakening`, `stale_reference`.

## What you get back

Per unit (one sprint, workflow or file):

- **`findings`**: items whose pattern probability reached the threshold (0.8), each with its location (`where`, `lines`, and `field` for beads), the top `pattern`, `pattern_probability`, the per-pattern `patterns`, and the start of the item's text.
- **`uncertain`**: items Jev could not place on either side, with its leaning.
- **`clear`**: the count of items that matched no pattern.

The result also names the context file Jev saw. Findings are locations to look at, not verdicts: the calling agent reads each item in place, checks it against the collected facts and your repo's guidelines, and reports its assessment and recommendation, including where it disagrees with Jev.

## Size and cost

Every request to Jev stays within 24,000 bytes and 12 questions; large items are split, never dropped. Before calling Jev, the agent sizes the run with `--dry-run`. If it needs more than `max_requests` requests (default 100), the agent reports the size per unit instead of running, so you can narrow the inputs or raise the limit. A full `local` instructions scope in a large repo can run to hundreds of requests.

To size a run yourself (no key, no network):

```bash
python3 packages/process-porn/scripts/jev_ceremony.py instructions --scope local --dry-run
```

## Repository layout

```
.claude-plugin/marketplace.json      Claude Code marketplace
.agents/plugins/marketplace.json     Codex marketplace
packages/process-porn/
  .claude-plugin/plugin.json         Claude Code plugin manifest
  .codex-plugin/plugin.json          Codex plugin manifest
  manifest.yaml                      package manifest
  skills/reviewing-ceremony/         router skill and per-category references
  agents/ceremony-review.md          context collection and script run
  scripts/jev_ceremony.py            item extraction, request packing, Jev calls, report
  tests/                             unit tests
```

## Development

```bash
python3 -m unittest discover -s packages/process-porn/tests
```

CI runs the tests on Linux, macOS and Windows, with Python 3.9 and the latest 3.x, on every pull request and on pushes to `main`. The tests use a stub transport: they cover item extraction, scope discovery, request packing, response validation and the report, not Jev's judgment.

## License

MIT
