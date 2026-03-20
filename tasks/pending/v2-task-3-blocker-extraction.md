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
