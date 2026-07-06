### Accomplished

Fixed the `result: null` bug in the controller. Root cause: `main.go` line ~560 called
`taskQueue.UpdateStatus(ctx, taskID, queue.StatusCompleted, "")` — the empty string
meant `task.Result` was always `""` in Redis, so `GET /api/v1/tasks/{id}` always
returned `result: null` regardless of what the worker logged.

Changes (commit d97da5f):
- Added `ExtractResultBlock(logs string) string` to `queue/queue.go` — extracts the
  raw `===RESULT_START===...===RESULT_END===` block from pod logs.
- Updated `main.go` completion handler to pass `queue.ExtractResultBlock(logs)` instead
  of `""` to `UpdateStatus`.
- Added `TestExtractResultBlock` to `queue/queue_test.go` that verifies the round-trip:
  extract block → ParseResult returns correct data.
- All 15 test packages pass. Pushed to main.

### Current state

Done. The fix is live on main. Controller rebuild/redeploy will pick it up automatically.

### First thing next time

Nothing — task is complete.
