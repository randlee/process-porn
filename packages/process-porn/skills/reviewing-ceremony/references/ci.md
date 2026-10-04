# Category: ci

## Inputs

This category covers GitHub Actions workflows. Pass every workflow file under `.github/workflows/`, both `.yml` and `.yaml`, so the script can see jobs that are duplicated across workflows:

```bash
find .github/workflows -name '*.yml' -o -name '*.yaml'
```

`<workflow files...>` below means that list. `gh` is needed for step 1 below; check it with `which gh && gh auth status`.

## Context to collect

Each item states one fact, cites its source, and is one line. Collect facts only; don't classify the jobs.

Record only what a command printed. Under each heading, list the commands you ran. If you ran none for a step, write `not collected`. Jev treats every fact as true.

1. **Required checks.** For the trunk branches (the default branch and any integration branch the user names):
   ```bash
   gh api repos/{owner}/{repo}/rules/branches/<branch> --jq '.[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context'
   gh api repos/{owner}/{repo}/branches/<branch>/protection/required_status_checks --jq '.contexts[]'
   ```
   Run these from the repository checkout, where `gh` fills in `{owner}/{repo}`. Record `required on <branch>: <check names>`. If both calls fail or return nothing, record `no required checks found on <branch>`, and record what else gates merges, if anything: a merge queue, a stated rule that all checks must pass, or `no merge gate found`.
2. **Callers.** For each workflow with `workflow_call` or `workflow_dispatch`, record which workflows or scripts call it:
   ```bash
   grep -rnE 'uses: \./\.github/workflows/<file>|gh workflow run <file>' .github <tooling dirs>
   ```
   `<tooling dirs>` are the repo's script directories, if any. A workflow with only `workflow_dispatch` and no caller is run by hand; record `<file>: manual only`.
3. **Artifact consumers.** List the upload and download names and patterns:
   ```bash
   grep -nE -A8 'actions/(upload|download)-artifact@' <workflow files...> | grep -E 'artifact@| name:| pattern:'
   ```
   For each upload name, record which workflow or job downloads it (by name or matching pattern), or `<name>: no download found`.
4. **Dependencies and duplicate commands.**
   - For each publish or release job, record the jobs under its `needs:`: `<job>: needed by <job>`.
   - List the one-line commands that appear more than once:
     ```bash
     grep -hE '^[[:space:]]+(- )?run: ' <workflow files...> | sed -E 's/^[[:space:]]+(- )?run: //' | sort | uniq -d
     ```
     For each, find where it runs (`grep -nF '<command>' <workflow files...>`) and record `<command>: run by <job>, <job>`, adding `<job> needs <job>` when one of those jobs needs the other.
5. **Deferred failure.** Find the steps that continue on error and the steps that read outcomes:
   ```bash
   grep -nE 'continue-on-error|if: .*always\(\)|steps\.[A-Za-z0-9_-]+\.outcome|job\.status|failure\(\)' <workflow files...>
   ```
   For each job with such steps, record whether a later step reads their outcomes and exits non-zero: `<job>: <step> fails the job on collected outcomes`, or `<job>: no step fails on collected outcomes`.
6. **Stated CI policy.** Record any one-line CI rules from the repo's instruction files (CLAUDE.md, AGENTS.md, CONTRIBUTING.md) and from any CI policy document, quoted with their path. Find candidate policy documents by their headings, then open the ones whose title is about CI:
   ```bash
   grep -rlE '^#+ .*(\bCI\b|continuous integration)' --include='*.md' --exclude-dir='.*' --exclude-dir=node_modules .
   ```

## Context file

Write the file to a temporary path as markdown, with one heading per numbered step above. It must not exceed 8,000 bytes. If it would, keep the facts about jobs and steps whose names appear in the inventory, and drop the rest.

## Run

```bash
python3 <script> ci <workflow files...> --context <file> --brief 240
```

Exit 0 means no findings, 1 means findings were reported, 2 means an error.

## Reading results

- `unit` is the workflow file name. `where` is `workflow header`, `jobs.<job>` (the job's keys before `steps:`) or `jobs.<job>.steps[<n>] <name>`, and `lines` are line numbers in the file.
- Jev saw every reviewed job's non-setup steps, so `redundant` refers to a job listed in that inventory.

| Pattern | Jev matched | Fact that settles it |
|---|---|---|
| `redundant` | Another job or step runs the same work for the same trigger | The duplicate commands (step 4). The copy in a job that needs the other job is the duplicate; otherwise, which copy is a required check (step 1) or needed by a release job (step 4) |
| `report_only` | A report, summary, badge, upload or notification | Whether anything downloads or gates on it (step 3) |
| `unconsumed_check` | A check whose failure blocks nothing | Whether it is a required check (step 1) or called by another workflow (step 2). With no required checks and no other merge gate, every check matches, so this pattern carries little signal |
| `gate_weakening` | `continue-on-error`, skip conditions, path filters or retries that let failures pass | Whether a later step fails the job on the collected outcomes (step 5), the stated CI policy (step 6), and the branches the condition covers |

`clear` covers gates, release jobs, and the triggers, permissions and setup they need.
