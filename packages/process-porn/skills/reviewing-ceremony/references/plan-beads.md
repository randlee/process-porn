# Category: plan (beads)

Use this reference for plans stored as beads. Use `plan.md` for plans in markdown files. Collect the context with `plan.md` steps 1, 2, 4 and 5. Step 3 comes from the bead JSON itself.

## Inputs

One or more sprint beads, from either CLI:

| CLI | Check | One sprint |
|---|---|---|
| `bd` (beads) | `which bd && bd --version` | `bd show <id> --json` |
| `br` (beads_rust) | `which br && br --version` | `br show <id> --json` |

To get every sprint under a phase root:
- **bd:** list the children, then show them:
  ```bash
  bd list --parent <root> --all --json        # prints a JSON list
  bd show <ids...> --json
  ```
- **br:** `br list` has no `--parent` option. Child ids are dotted (`<root>.1`), and the list is wrapped in an object:
  ```bash
  br list --all --limit 0 --json | python3 -c 'import json,sys; r=sys.argv[1]; print(" ".join(i["id"] for i in json.load(sys.stdin)["issues"] if i["id"].startswith(r+".") and "." not in i["id"][len(r)+1:]))' <root>
  br show <ids...> --json
  ```

Always pass ids explicitly. A bare `br show` falls back to the last-touched bead.

`bd show` and `br show` both print a JSON list of issue objects with `id`, `title`, `issue_type`, `description`, `design`, `acceptance_criteria` and `notes`. Only `bd` adds `metadata`. Fetch full content with `show`, because `list` output can omit the text fields (`bd list --brief` always does).

- Use read-only commands only: no `update`, `close`, `sync`, `config` or `init`.

## Bead JSON

Pipe the `show` output to the script unchanged. If you need to say which CLI produced it, or to combine output from several calls, wrap the list in an object:

```json
{
  "source": "bd",
  "beads": [
    {
      "id": "obs-d-31",
      "title": "d-31: sc-otel cli",
      "issue_type": "feature",
      "description": "## Goal\nShip the `sc-otel` binary ...",
      "design": "## Relations\n...",
      "acceptance_criteria": "- [ ] boundary:BOUNDARY-ScOtelCli: ...",
      "notes": "",
      "metadata": {"branch": "sprint/d-31-sc-otel-cli", "difficulty": "normal"}
    }
  ]
}
```

The script accepts:
- a bare list, as `bd show --json` prints it;
- the wrapped object above.

Field rules:
- `id` is required.
- `title`, `description`, `design`, `acceptance_criteria` and `notes` must be strings if present. They are reviewed item by item, and each entry's `field` says which one an item came from.
- The `metadata` keys (bd only) go into the unit's context, so Jev can see that a field the text restates is already held as data.

If your CLI's JSON names these fields differently, map them to the names above before piping. Never pass the text as some other key: anything else is ignored.

## Context file

Write the file as `plan.md` describes, with steps 1, 2, 4 and 5. For bd, add one line per bead:

```
<id>: metadata holds <keys>
```

The 8,000-byte limit still applies.

## Run

```bash
bd show <ids...> --json | python3 <script> plan --beads-json - --context <file> --brief 240
br show <ids...> --json | python3 <script> plan --beads-json - --context <file> --brief 240
```

To combine several calls, write the wrapped object to a file and pass `--beads-json <file>`. Don't also pass input paths: `--beads-json` replaces them.

## Reading results

- `unit` is the bead id. `field` is the bead field the item came from, and `lines` are 1-based within that field's text. `where` starts with the field name, followed by the heading path inside it.
- The patterns are the same as in `plan.md`'s results table. Metadata keys were in Jev's context, so `narration` on text that restates a key means Jev saw the key held as data.
