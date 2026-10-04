# Installation and Troubleshooting

## Check First

```bash
which python3 && python3 --version
[ -n "$TYPESAFE_API_KEY" ] && echo set || echo missing
which bd && bd --version   # plan reviews of beads only
```

If all of these pass, skip installation.

## Find Existing Install

```bash
for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin" "$HOME/.pyenv/shims"; do
  for cli in python3 bd; do [ -x "$d/$cli" ] && echo "$cli found at: $d/$cli"; done
done
```

## Install

- **python3:**
  - macOS: `brew install python`
  - Debian/Ubuntu: `sudo apt install python3`
  - Windows: `winget install Python.Python.3.12`

  The script uses the standard library only.
- **bd (beads):** follow https://github.com/steveyegge/beads. It's needed only for `plan` reviews of beads.
- **TYPESAFE_API_KEY:** get a key from TypeSafe, then export it in the shell that launches Claude Code:
  ```bash
  export TYPESAFE_API_KEY=...
  ```

## Minimum Version

- python3 3.9 or later.
- bd: any version whose `bd show <id> --json` returns the issue object.

## PATH Troubleshooting

Claude Code's bash may not load `.zshrc` or `.bashrc`. If a CLI works in your terminal but isn't found here, add its directory for the session:

```bash
export PATH="/opt/homebrew/bin:$PATH"   # adjust to the directory found above
```

## Validation

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/jev_ceremony.py" instructions CLAUDE.md --dry-run
```

This needs no key and makes no network call. It prints the units and request sizes.

## Known Issues

| Error | Cause and fix |
|---|---|
| `JEV.UNAVAILABLE` with "TYPESAFE_API_KEY is missing" | The key isn't in Claude Code's environment. Export it, then restart Claude Code. |
| `JEV.UNAVAILABLE` with an HTTP status | Network or vendor outage, or an invalid key. A 429 is retried once. |
| `JEV.INCONCLUSIVE` | A single line is larger than the 24,000-byte request limit. Split it by hand. |
