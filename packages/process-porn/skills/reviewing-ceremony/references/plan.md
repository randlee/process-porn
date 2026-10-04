# Category: plan

## Inputs

- Sprint md files: one sprint per file, passed as paths.
- One md file holding several sprints: pass `--sprint-level N`, where N is the heading level that starts each sprint.
- Sprint beads: pass the bead ids with `--beads`. This needs `bd` on PATH; check with `which bd && bd --version`.

One run covers one phase. Run once per phase, because the context below is phase-wide.

## Context to collect

Each item states one fact, cites its source path, and is one line, two at most. Don't judge plan items here; Jev does that.

1. **Phase goal.** Take the opening paragraph of the phase plan or README, up to about 1,000 bytes.
2. **Tools that read plan fields.** These stop data that tools read from being flagged as narration.
   - For each `Label:` in the sprint's metadata lists, search the repo's tooling, skipping `docs/`:
     ```bash
     rg -l --fixed-strings '<Label>' scripts .claude .github
     ```
   - For each hit, record `<Label>: read by <path>`.
   - For a label with no hits, record `<Label>: no reader found`.
3. **Fields the bead already holds.** For bead-backed plans, run `bd show <sprint-bead> --json` and list the metadata keys. Record `bead metadata holds: <keys>`. A field present in both the md and the bead is a duplicate.
4. **Out-of-scope owners.** For each sprint named in an out-of-scope or "does not close" section, record whether it exists in the phase: `d-32: exists in phase` or `d-32: not found`.
5. **Validation commands.** For each command in the sprint's required-validation section, record whether CI or a gate runs it: `cargo clippy ...: run by .github/workflows/ci.yml` or `not run by CI`.

## Context file

Write the file to a temporary path as markdown, with one heading per numbered step above. It must not exceed 8,000 bytes. If it would, shorten step 2 to the labels that appear in the reviewed sprints.

## Run

```bash
python3 <script> plan <inputs...> [--beads] [--sprint-level N] --context <file> --brief 240
```

## Reading results

| Reason | Meaning |
|---|---|
| `remove_narration` on a metadata field | The context named no reader. If a reader exists that the search missed, report it rather than deleting the field. |
| `remove_ungated_artifact`, `remove_meta_review` | A ledger, report or review round with no consumer and no gate. |
| `fix_gate_weakening`, `fix_follow_up_laundering` | Rewrite the item so the gate holds, or restore the in-scope acceptance. |
