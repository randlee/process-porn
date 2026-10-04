# process-porn
Skills and scripts for TypeSafe Jev agent to unnecessary process and ceremony

## Install

```
/plugin marketplace add randlee/process-porn
/plugin install process-porn@process-porn
```

## Skills

- `jev-ceremony-check` reviews three kinds of input, item by item, with typed Jev Choice questions:
  - sprint plans (md files or beads);
  - CI workflows;
  - agent instructions (CLAUDE.md, AGENTS.md, skills, agent prompts).

  For each one it reports exactly which lines to remove or fix, and why. It needs `TYPESAFE_API_KEY`. See [the skill](plugins/process-porn/skills/jev-ceremony-check/SKILL.md).

## Tests

```
python3 -m unittest discover -s plugins/process-porn/skills/jev-ceremony-check/tests
```

The tests use a stub transport. They cover item extraction, request packing, response validation and the report, not Jev's judgment.
