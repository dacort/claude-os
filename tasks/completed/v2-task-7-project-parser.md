---
profile: medium
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
created: "2026-03-20T17:22:00Z"
---

# v2 Task 7: Project file parser

## Description

Create a new `controller/projects/` package that parses project.md files and provides backlog selection and state update helpers.

### New Files

Create `controller/projects/projects.go` with:

**Structs:**
- `ProjectFrontmatter` — name, title, status, owner, reviewer, created, secret, backlog_source, budget
- `ProjectBudget` — daily_tokens, model  
- `Project` — embeds ProjectFrontmatter + RawContent, Goal, State, Backlog, Memory, Decisions
- `BacklogItem` — Text, Done, Index, RawLine

**Functions:**
- `ParseProject(name string, data []byte) (*Project, error)` — parse YAML frontmatter + extract markdown sections (Goal, Current State, Backlog, Memory, Decisions). Parse backlog as checkbox items.
- `(p *Project) NextBacklogItem() *BacklogItem` — return first unchecked item
- `(p *Project) RemainingItems() int` — count unchecked items
- `CheckOffItem(content string, item BacklogItem) (string, error)` — replace `- [ ]` with `- [x]` for given item
- `UpdateCurrentState(content, newState string) (string, error)` — replace Current State section
- `AppendMemory(content, date, summary string) (string, error)` — prepend new session to Memory section
- `ScanProjects(projectsDir string) ([]*Project, error)` — read all `projects/*/project.md` files
- Helper: `extractSection(body, heading string) string` — extract content between ## headings
- Helper: `replaceSection(content, heading, newBody string) (string, error)` — replace section content

### Tests

Create `controller/projects/projects_test.go` with a sample project markdown constant and tests:
- `TestParseProject` — parse sample, verify all frontmatter fields
- `TestNextBacklogItem` — verify first unchecked item is returned
- `TestNextBacklogItem_AllDone` — verify nil when all checked
- `TestCheckOffItem` — check off first item, re-parse, verify next unchecked skips it
- `TestUpdateCurrentState` — update state, verify new content present
- `TestAppendMemory` — append session, verify it appears before old sessions

### TDD
- Write all tests first (they can reference the planned API), run to fail
- Implement, run to pass
- Commit: `feat: project file parser with backlog selection and state updates`

## Results

## Outcome

- Outcome: success
- Agent: claude
- Model: claude-sonnet-4-6

## Summary

Task completed without an explicit structured result block.

## Usage

- Tokens in: 0
- Tokens out: 0
- Duration (s): 268

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "v2-task-7-project-parser",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 268
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: v2-task-7-project-parser
Profile: medium
Agent: claude
Mode: execution
Started: 2026-03-20T17:24:43Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
Already retrieved and processed — that was the full test suite run confirming all 10 packages passed. The task is complete and pushed to main.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-20T17:29:10Z
===RESULT_START===
{"version":"1","task_id":"v2-task-7-project-parser","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":268},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"v2-task-7-project-parser","agent":"claude","profile":"medium","duration_seconds":268,"exit_code":0,"finished_at":"2026-03-20T17:29:10Z"}
=== END_CLAUDE_OS_USAGE ===

