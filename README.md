# process-porn
Skills and scripts that use the TypeSafe Jev agent to locate unnecessary process and ceremony.

## Install

```
/plugin marketplace add randlee/process-porn
/plugin install process-porn@process-porn
```

## Contents

`packages/process-porn` provides:
- the `reviewing-ceremony` skill. It routes by category (`plan`, `ci`, `instructions`), and each category's reference says what context to collect.
- the `ceremony-review` agent. It collects that context, runs `scripts/jev_ceremony.py` and returns the findings as fenced JSON.

It needs python3 and `TYPESAFE_API_KEY`. See [the skill](packages/process-porn/skills/reviewing-ceremony/SKILL.md).

## Tests

```
python3 -m unittest discover -s packages/process-porn/tests
```

CI runs them on Linux, macOS and Windows, with Python 3.9 and the latest 3.x. The tests use a stub transport. They cover item extraction, request packing, response validation and the report, not Jev's judgment.
