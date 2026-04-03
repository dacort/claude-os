# Skill: Worker / Controller Development

Auto-injected when the task involves the claude-os worker or controller infrastructure.

## Architecture overview

```
controller/          — Go service that manages task lifecycle
  queue/             — task file parsing and state management
  gitsync/           — watches for task file changes in git
  dispatcher/        — routes tasks to workers (Claude, Codex, etc.)
  scheduler/         — cron-based task scheduling
  triage/            — smart dispatch (Claude decides routing)
  cosapi/            — REST API for task management
worker/
  entrypoint.sh      — worker bootstrap: builds system prompt, runs Claude Code
  agent/             — Python helpers for prompt construction
```

## Key contracts

- Context contract: `/workspace/task-context.json` — the JSON envelope passed to workers
- Task files: `tasks/{pending,active,completed,failed}/<id>.md` — YAML frontmatter + markdown
- Result block: `=== CLAUDE_OS_RESULT ===` JSON in task output for structured results

## Safe changes

- Modifying `entrypoint.sh` affects ALL workers — test with a dry run first
- Controller changes require `go build ./...` and restart
- Worker Dockerfile changes need `docker build` in CI

## Testing a worker change

```bash
cd /workspace/claude-os
cat worker/entrypoint.sh | bash -s -- --dry-run  # doesn't exist yet, but useful pattern
go test ./...                                     # controller unit tests
```
