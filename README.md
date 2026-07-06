# Claude OS

Autonomous execution environment for Claude on Kubernetes.

## Structure

- `controller/` — Go service that orchestrates task execution
- `worker/` — Base Docker image for ephemeral worker pods
- `config/` — Configuration files for the controller
- `tasks/` — Git-based task queue (pending/in-progress/completed/failed)
- `knowledge/` — Persistent learnings and project context
- `projects/` — Self-directed creative projects
- `logs/` — Task summaries and usage reports

## Task Format

Create a markdown file in `tasks/pending/` with YAML frontmatter:

```markdown
---
target_repo: github.com/dacort/some-repo
profile: medium
priority: normal
---
# Task Title

## Description
What needs to be done.
```

## Controller REST API

The controller exposes a REST API at `/api/v1/` for programmatic task management. Use the `cos` CLI or direct HTTP requests.

**Environment:** Set `CONTROLLER_URL` to the controller's address (e.g., `http://localhost:8080` or via `kubectl port-forward`).

### Endpoints

**POST /api/v1/tasks** — Create a task
- Required: `title` (≤200 chars), `target_repo`
- Optional: `description` (≤5000 chars), `profile` (small|medium|large|burst|think), `priority` (normal|high|creative), `agent` (claude|codex|gemini), `model`, `context_refs`
- Response: `{id, title, status, queue_position, created_at}`

**GET /api/v1/tasks/{id}** — Get task details
- Response: full task with status, progress, result, logs metadata

**GET /api/v1/tasks/{id}/logs** — Get task logs
- Query: `?tail=N` (last N lines), `?follow=true` (stream logs as SSE)
- Response: `{task_id, status, lines: [{ts, text}], message}`

**GET /api/v1/status** — System status
- Query: `?recent=N` (number of recent tasks to include, 0–50, default 5)
- Response: controller version, queue counts, governance stats, agent health, running/pending/recent tasks

**GET /api/v1/signal** — Read current signal from git
**POST /api/v1/signal** — Write a new signal (title, message)
**DELETE /api/v1/signal** — Clear current signal

### Examples

```bash
# Create a task
curl -X POST http://localhost:8080/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Fix bug in X",
    "target_repo": "github.com/dacort/some-repo",
    "profile": "medium",
    "priority": "high"
  }'

# Get task details
curl http://localhost:8080/api/v1/tasks/fix-bug-in-x-a1b2

# Stream logs
curl 'http://localhost:8080/api/v1/tasks/fix-bug-in-x-a1b2/logs?follow=true'

# Check system status
curl http://localhost:8080/api/v1/status
```

## Secrets Required

- `claude-os-github` — GitHub PAT + webhook secret
- `claude-os-anthropic` — Anthropic API key
