# process-porn
Skills and scripts for TypeSafe Jev agent to unnecessary process and ceremony

## Install

```
/plugin marketplace add randlee/process-porn
/plugin install process-porn@process-porn
```

## Skills

- `jev-ceremony-check` scores a markdown document section by section with typed Jev Choice questions. It covers ungated process artifacts, process-heavy sections, gate weakening, follow-up laundering and the meta-trap, and it computes the verdict in code. It needs `TYPESAFE_API_KEY`. See [the skill](plugins/process-porn/skills/jev-ceremony-check/SKILL.md).

## Tests

```
python3 -m unittest discover -s plugins/process-porn/skills/jev-ceremony-check/tests
```

The tests use a stub transport. They cover splitting, response validation and verdict aggregation, not Jev's judgment.
