# Category: ci

## Inputs

Pass every workflow file under `.github/workflows/`, so the script can see jobs that are duplicated across workflows. `gh` is needed for step 1 below; check it with `which gh && gh auth status`.

## Context to collect

Each item states one fact, cites its source, and is one line. Collect facts only; don't classify the jobs.

1. **Required checks.** For the trunk branches (the default branch and any integration branch the user names):
   ```bash
   gh api repos/{owner}/{repo}/rules/branches/<branch> --jq '.[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context'
   gh api repos/{owner}/{repo}/branches/<branch>/protection/required_status_checks --jq '.contexts[]'
   ```
   Record `required on <branch>: <check names>`. If both calls fail or return nothing, record `no required checks found on <branch>`.
2. **Callers.** For each workflow with `workflow_call` or `workflow_dispatch`, record which workflows or scripts call it:
   ```bash
   rg -n 'uses: \./\.github/workflows/<file>|gh workflow run <file>' .github scripts
   ```
3. **Artifact consumers.** For each `upload-artifact` name, record which workflow or job downloads it, or `<name>: no download found`.
4. **Release flow.** For each job, record whether a publish or release job has it under `needs:`: `<job>: needed by <job>`.
5. **Stated CI policy.** Record any one-line CI rules from the repo's instruction files (CLAUDE.md, AGENTS.md, CONTRIBUTING.md), quoted with their path.

## Context file

Write the file to a temporary path as markdown, with one heading per numbered step above. It must not exceed 8,000 bytes. If it would, keep the facts about jobs and steps whose names appear in the inventory, and drop the rest.

## Run

```bash
python3 <script> ci .github/workflows/*.yml --context <file> --brief 240
```

## Reading results

- `unit` is the workflow file name. `where` is `workflow header`, `jobs.<job>` (the job's keys before `steps:`) or `jobs.<job>.steps[<n>] <name>`, and `lines` are line numbers in the file.
- Jev saw every reviewed job's non-setup steps, so `redundant` refers to a job listed in that inventory.

| Pattern | Jev matched | Fact that settles it |
|---|---|---|
| `redundant` | Another job or step runs the same work for the same trigger | Which copy is a required check (step 1), or needed by a release job (step 4) |
| `report_only` | A report, summary, badge, upload or notification | Whether anything downloads or gates on it (step 3) |
| `unconsumed_check` | A check whose failure blocks nothing | Whether it is a required check (step 1) or called by another workflow (step 2) |
| `gate_weakening` | `continue-on-error`, skip conditions, path filters or retries that let failures pass | The stated CI policy (step 5) and the branches the condition covers |

`clear` covers gates, release jobs, and the triggers, permissions and setup they need.
