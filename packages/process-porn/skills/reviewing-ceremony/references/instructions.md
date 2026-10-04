# Category: instructions

## Inputs

CLAUDE.md, AGENTS.md, `SKILL.md` files, and agent prompt files (`.claude/agents/*.md`), passed as paths. Each file is one unit.

## Context to collect

Each item states one fact, cites its source path, and is one line. Don't judge rules here; Jev does that.

1. **Who loads each file and when.**
   - CLAUDE.md and AGENTS.md: every session in the repo.
   - A skill: its frontmatter `description`, and the skills, agents or commands that name it (`rg -l '<skill-name>' .claude`).
   - An agent: the skills, agents or templates that invoke it (`rg -l '<agent-name>' .claude`).

   Record `<file>: loaded by <loader>`.
2. **Enforcement outside the text.** List the hooks in `.claude/settings.json` and the scripts that enforce a rule the file states. Record `<rule, quoted briefly>: enforced by <hook or script path>`. A rule that a hook already enforces may still need a line telling the agent why it was refused, but not a restatement.
3. **Loaded together.** List the other instruction files loaded in the same session as each reviewed file (for example, CLAUDE.md plus the repo's skills index), with their headings. Jev uses this list to spot restatement.
4. **Referenced files.** For each path or command the file names, record whether it exists:
   ```bash
   test -e <path> && echo exists || echo missing
   ```
   Record `<path>: exists` or `<path>: missing`.

## Context file

Write the file to a temporary path as markdown, with one heading per numbered step above. It must not exceed 8,000 bytes. If it would, cut step 3 to headings only.

## Run

```bash
python3 <script> instructions <files...> --context <file> --brief 240
```

## Reading results

| Reason | Meaning |
|---|---|
| `remove_narration` | History, incident stories, purpose sections, excess rationale or restatement. Every line costs context on every load. |
| `remove_ungated_artifact`, `remove_meta_review` | The file tells the agent to keep a ledger, report or review round that nothing consumes. |
| `fix_gate_weakening` | The file tells the agent to skip, weaken or self-certify a gate. |
| `keep_reference` on a missing path | Fix the path. This is a stale reference, not ceremony. |
