---
profile: small
priority: creative
status: completed
---

# Workshop: skills-via-system_context

## Results

=== Claude OS Worker v2 ===
Task ID: skills-via-system_context
Profile: medium
Agent: claude
Started: 2026-03-13T14:27:25Z
Auth: Claude OAuth token (subscription)
Cloning claude-os repo for workspace access
Injecting preferences from knowledge/preferences.md
Running task via claude...
---
Done. Here's what I built:

## Skills via `system_context()` — complete

**What was built:**

### Controller: `dispatcher/skills.go`
- `LoadSkills(dir string)` — reads `skill.yaml` files from a directory of skill subdirs, compiles their regex patterns. Missing directory is silently OK.
- `MatchSkills(text string)` — returns inject paths for all skills whose pattern matches the text (case-insensitive).

### Dispatcher change: `dispatcher.go`
`CreateJob` now merges skill-matched context refs into `CONTEXT_REFS`, after deduplicating against any refs already declared in task frontmatter. Zero overhead when no skills match.

### Main: `main.go`
Calls `LoadSkills` at startup from `SKILLS_PATH` (default `/etc/claude-os/skills`). The controller will need a ConfigMap mounted there for skills to activate — but it starts fine without one.

### Three starter skills in `knowledge/skills/`:
| Skill | Pattern | Context |
|---|---|---|
| `pr-review` | review PR / code review / pull request | Checklist approach, `gh` commands for review |
| `go-testing` | go test / failing test / write test | Conventions, table-driven test pattern, debug commands |
| `github-workflow` | open PR / fix CI / GitHub workflow | Branch norms, `gh` commands, CI debugging |

### Tests: `dispatcher/skills_test.go`
- `TestLoadSkillsMissingDir` — graceful handling of missing dir
- `TestLoadAndMatchSkills` — pattern matching works
- `TestSkillsInjectedIntoJob` — end-to-end: auto-inject, no false positives, dedup against explicit refs
---
=== Worker Complete ===
Exit code: 0
Finished: 2026-03-13T14:32:09Z

