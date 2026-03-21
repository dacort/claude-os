## Summary

Added proper `--help` (via argparse) to the top 5 most-cited tools that were
silently ignoring `--help` and running instead. Each tool now shows its name,
what it does, all flags with descriptions, and at least 2 usage examples in
the epilog.

No functionality changed. All existing flags (`--plain`, `--brief`, `--json`,
`--since`, `--codas`, `--themes`) work identically — argparse just replaced the
manual `"--flag" in sys.argv` checks.

**Tools fixed (by citation rank):**

| Rank | Tool | Citations | Flags documented |
|------|------|-----------|------------------|
| #1   | garden.py | 20 sessions | --plain, --brief, --json, --since REF |
| #4   | homelab-pulse.py | 12 sessions | (no flags — added help text only) |
| #5   | hello.py | 11 sessions | --plain |
| #8   | wisdom.py | 7 sessions | --plain, --codas, --themes |
| #11  | forecast.py | 6 sessions | --plain, --json |

**Note on wisdom.py:** It sets `PLAIN = "--plain" in sys.argv` at module level
(needed by module-level color helpers). That line was left unchanged. The new
argparse parser in `main()` handles `--help` before any of the existing logic
runs, so there's no conflict.

## Artifacts

- `projects/garden.py` — argparse added to `main()`
- `projects/homelab-pulse.py` — new `main()` function with argparse, `__main__` block updated
- `projects/hello.py` — argparse added to `main()`
- `projects/wisdom.py` — argparse added to top of `main()`, existing sys.argv checks preserved
- `projects/forecast.py` — argparse added to `main()`, replacing manual `sys.argv[1:]` parsing

Commit: `9636c3d` — pushed to main.

## Handoff Notes

Done. No follow-up needed unless dacort wants `--plain` wired into
`homelab-pulse.py` (it currently has no color-disable option — the dashboard
always renders with ANSI). That would be a separate small change.
