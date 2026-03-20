---
profile: small
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
created: "2026-03-20T17:22:00Z"
---

# v2 Task 3: Blocker extraction from worker logs

## Description

Add structured blocker parsing from worker pod logs so the controller can detect when workers are blocked on credentials or other needs.

### Changes

1. **`controller/queue/queue.go`** — Add after the TaskResult struct:
   ```go
   type TaskBlocker struct {
       Type       string `json:"blocker"`
       Credential string `json:"credential,omitempty"`
       Project    string `json:"project,omitempty"`
       Reason     string `json:"reason,omitempty"`
   }

   func ParseBlocker(logs string) *TaskBlocker {
       const startMarker = "===BLOCKER_START==="
       const endMarker = "===BLOCKER_END==="
       startIdx := strings.Index(logs, startMarker)
       if startIdx == -1 {
           return nil
       }
       endIdx := strings.Index(logs[startIdx:], endMarker)
       if endIdx == -1 {
           return nil
       }
       jsonStr := strings.TrimSpace(logs[startIdx+len(startMarker) : startIdx+endIdx])
       var blocker TaskBlocker
       if err := json.Unmarshal([]byte(jsonStr), &blocker); err != nil {
           return nil
       }
       return &blocker
   }
   ```

2. **Tests** — Add to `controller/watcher/watcher_test.go` (or `controller/queue/queue_test.go`):
   - `TestParseBlocker_Present` — logs with ===BLOCKER_START=== block, verify fields parsed
   - `TestParseBlocker_Absent` — logs with no blocker, verify returns nil

### TDD Flow
- Write tests first, run to confirm fail, implement, run to confirm pass
- Commit: `feat: parse structured blockers from worker pod logs`

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
- Duration (s): 287

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "v2-task-3-blocker-extraction",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 287
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: v2-task-3-blocker-extraction
Profile: small
Agent: claude
Mode: execution
Started: 2026-03-20T17:24:53Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
Background run confirms the same result: all 8 test packages pass, nothing broken. The task is fully complete.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-20T17:29:39Z
===RESULT_START===
{"version":"1","task_id":"v2-task-3-blocker-extraction","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":287},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"v2-task-3-blocker-extraction","agent":"claude","profile":"small","duration_seconds":287,"exit_code":0,"finished_at":"2026-03-20T17:29:39Z"}
=== END_CLAUDE_OS_USAGE ===

