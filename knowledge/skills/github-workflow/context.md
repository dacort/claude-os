# Skill: GitHub Workflow

Auto-injected when the task involves creating PRs, fixing CI, or GitHub Actions.

## Branch and PR conventions

- Feature work goes on a branch; non-breaking changes commit directly to `main`
- PR titles should be under 70 characters
- Use conventional commit prefixes: `feat:`, `fix:`, `docs:`, `task <id>:`

## Common gh commands

```bash
# PRs
gh pr create --title "..." --body "..."
gh pr list
gh pr view <number>
gh pr checks <number>
gh pr merge <number> --squash

# Issues
gh issue create --title "..." --body "..."
gh issue list --label "..."
gh issue close <number>

# CI / Actions
gh run list --branch main
gh run view <run-id>
gh run view <run-id> --log-failed   # Show only failing steps
```

## Fixing CI failures

1. `gh pr checks <number>` — see which checks failed
2. `gh run view <run-id> --log-failed` — get the error output
3. Fix the issue, push, and re-check

## dacort/claude-os CI

The controller has Go tests that run on every push:
- `go test ./...` must pass
- Tests live in `controller/`
- If CI is red on main, fix it before doing other work
