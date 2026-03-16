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

## Secrets Required

- `claude-os-github` — GitHub PAT + webhook secret
- `claude-os-anthropic` — Anthropic API key
