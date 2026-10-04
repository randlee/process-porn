# Category: instructions

## Inputs

CLAUDE.md, AGENTS.md, `SKILL.md` files, and agent prompt files (`.claude/agents/*.md`), passed as paths. Each file is one unit.

## Context to collect

Each item states one fact, cites its source path, and is one line. Collect facts only; don't classify the rules.

Record only what a command printed. Under each heading, list the commands you ran. If you ran none for a step, write `not collected`. Jev treats every fact as true.

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

Exit 0 means no findings, 1 means findings were reported, 2 means an error.

## Reading results

- `unit` is the file. `where` is the heading path to the item, and `lines` are line numbers in the file.

| Pattern | Jev matched | Fact that settles it |
|---|---|---|
| `narration` | History, incident stories, purpose sections, excess rationale or restatement | Whether the rule appears in another file loaded in the same session (step 3) |
| `ungated_artifact` | An instruction to keep a ledger, report or other artifact | Whether anything reads or gates on it |
| `meta_review` | A mandated review or approval round about the process | Whether the round can block the work |
| `gate_weakening` | An instruction to skip, weaken or self-certify a gate | Whether a hook or script enforces the gate (step 2) |
| `stale_reference` | A path or command the context records as missing | The `missing` line in step 4 |

`clear` covers instructions and references that change what the agent does.
