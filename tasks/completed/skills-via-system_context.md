---
profile: medium
priority: normal
status: completed
created: "2026-03-13T14:08:23Z"
context_refs:
  - knowledge/exoclaw-ideas.md
---

# Skills via `system_context()`

Make skills self-injecting: instead of the controller manually managing which
skills are available, each skill declares its own activation pattern. When a
task description matches the pattern, the skill's context is auto-injected
into the system prompt.

## Why Now

`context_refs` in task frontmatter (orchestration-phase1) made it possible
for tasks to declare what they need injected. Skills via `system_context()`
is the natural extension: the skill itself declares when it should activate.

## Scope

**Skill format:**
Each skill gets a `skill.yaml` (or frontmatter in the skill file) that declares:
```yaml
name: github-pr-review
pattern: "review.*PR|PR.*review|pull request"
inject: knowledge/skills/github-pr-review.md
```

**Dispatcher change:**
When creating a job, check if any skill patterns match the task description.
If so, add those skill files to `CONTEXT_REFS` automatically.

**Worker change:**
None — entrypoint.sh already reads `CONTEXT_REFS` from orchestration-phase1.

## Reference

`knowledge/exoclaw-ideas.md` §5 — original idea
`controller/dispatcher/dispatcher.go` — where context_refs are injected
`worker/entrypoint.sh` — where CONTEXT_REFS files are read
