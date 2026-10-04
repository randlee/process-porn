# Category: plan

## Inputs

- Sprint md files: one sprint per file, passed as paths.
- One md file holding several sprints: pass `--sprint-level N`, where N is the heading level that starts each sprint.
- Plans stored as beads: use `plan-beads.md` instead.

One run covers one phase. Run once per phase, because the context below is phase-wide.

## Context to collect

Each item states one fact and is one line, two at most. Collect facts only; don't classify the plan items.

Record only what a command printed. Under each heading, list the commands you ran. If you ran none for a step, write `not collected`. Jev treats every fact as true.

1. **Phase goal.** Take the opening paragraph of the phase plan or README, up to about 1,000 bytes.
2. **Tools that read plan fields.** These stop data that tools read from being flagged as narration.
   - For each `Label:` in the sprint's metadata lists, search the repo's tooling directories (scripts, `.claude/`, `.github/`, whichever exist), skipping documentation:
     ```bash
     grep -rlF '<Label>' <tooling dirs>
     ```
   - Open each hit and classify it:
     - **parsed:** code, a schema or a template that reads the value. Record `<Label>: parsed by <path>`.
     - **mentioned:** prose that only talks about the field. Record `<Label>: mentioned in <path>, not parsed`.
   - For a label with no hits, record `<Label>: no reader found`.
3. **Fields the bead already holds.** If the md plan also has sprint beads, list each bead's metadata keys as `plan-beads.md` describes. Record `<bead id>: metadata holds <keys>`. A field present in both the md and the bead is a duplicate.
4. **Out-of-scope owners.** For each sprint named in an out-of-scope or "does not close" section, record whether it exists in the phase: `<sprint>: exists in phase` or `<sprint>: not found`.
5. **Validation commands.** For each command in the sprint's required-validation section, record whether CI or a gate runs it: `<command>: run by <workflow file>` or `<command>: not run by CI`.

## Context file

Write the file to a temporary path as markdown, with one heading per numbered step above. It must not exceed 8,000 bytes. If it would, shorten step 2 to the labels that appear in the reviewed sprints.

## Run

```bash
python3 <script> plan <inputs...> [--sprint-level N] --context <file> --brief 240
```

Exit 0 means no findings, 1 means findings were reported, 2 means an error.

## Reading results

- `unit` is `<file>:<sprint heading>`. `where` is the heading path to the item, and `lines` are line numbers in the file.
- Items are list items, paragraphs, table rows (sent with the table's header row) and code blocks.

| Pattern | Jev matched | Fact that settles it |
|---|---|---|
| `narration` | History, provenance, rationale, status or restatement that instructs no one | Whether a tool reads the field (step 2), or the bead already holds it (step 3) |
| `ungated_artifact` | A ledger, report, matrix or certificate with no consumer, gate, observed defect and retirement | Whether anything reads or gates on the artifact |
| `meta_review` | A review or governance round about the process rather than the deliverable | Whether the round can block the deliverable |
| `gate_weakening` | A skip, `continue-on-error`, reduced check, mock or self-review accepted as proof | Whether CI runs the check as written (step 5) |
| `follow_up_laundering` | In-scope acceptance moved to a follow-up | Whether the follow-up owner exists in the phase (step 4) |

`clear` covers capability items and justified process: a validation command that runs and blocks merge, or a process step that names its consumer, gate, defect and retirement.
