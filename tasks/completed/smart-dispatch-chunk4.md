---
profile: medium
priority: high
status: pending
target_repo: dacort/claude-os
created: "2026-03-15T02:24:03Z"
context_refs:
  - knowledge/specs/2026-03-14-smart-dispatch-design.md
  - knowledge/plans/2026-03-14-smart-dispatch-implementation.md
---

# Smart Dispatch: Chunk 4 — Rate-Limit Detection + Agent Fallback

## Description
Implement Tasks 8 and 9 from the smart dispatch implementation plan (`knowledge/plans/2026-03-14-smart-dispatch-implementation.md`), section "Chunk 4: Rate-Limit Detection + Agent Fallback".

This builds on Chunks 1-3 (already merged to main).

### What to build:

**Task 8: Failure classification in watcher** (`controller/watcher/watcher.go`):
- Add `FailureClass` type with constants `FailureClassTaskError` and `FailureClassRateLimit`
- Add `rateLimitSignals` slice with patterns: "out of extra usage", "reached your usage limit", "quota exceeded", "rate limit exceeded", "credit balance too low", "429"
- Implement `ClassifyFailure(logs string) FailureClass` — lowercase comparison against signals
- Add `"strings"` to imports
- Create `controller/watcher/watcher_test.go` with `TestClassifyFailure` — 6 test cases covering rate limit patterns and generic task errors

**Task 9: Agent rate-limit tracking in Redis** (`controller/queue/queue.go`):
- Add `SetAgentRateLimited(ctx, agent, ttl)` — sets a TTL key in Redis
- Add `IsAgentRateLimited(ctx, agent) bool` — checks if agent is rate limited
- Add `GetFallbackAgent(ctx, currentAgent) (string, bool)` — walks fallback chain (claude→codex, codex→claude)
- Add `fallbackChain` map and `keyAgentRateLimited` format string
- Tests: `TestAgentRateLimitTracking` and `TestGetFallbackAgent` in `controller/queue/queue_test.go`

### Important note:
Go is NOT installed in this container. Write the code following the plan exactly, ensure it compiles logically, but you will not be able to run `go test`. Focus on correctness by following the plan's exact code snippets.

### How to work:
1. Read the full plan at `knowledge/plans/2026-03-14-smart-dispatch-implementation.md` — it has exact code and test snippets for Chunk 4
2. Write code following the plan precisely
3. Commit after each task (2 commits total)
4. Push to main when done

### Success criteria:
- Code matches the plan's snippets
- Proper imports added (`strings` in watcher, `time` and `fmt` in queue if not already present)
- 2 clean commits pushed to main

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
- Duration (s): 70

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "smart-dispatch-chunk4",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 70
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: smart-dispatch-chunk4
Profile: medium
Agent: claude
Mode: execution
Started: 2026-03-15T02:24:37Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting context ref: knowledge/specs/2026-03-14-smart-dispatch-design.md
Injecting context ref: knowledge/plans/2026-03-14-smart-dispatch-implementation.md
Injecting preferences from knowledge/preferences.md
Both commits are pushed. Here's a summary of what was done:

---

## Chunk 4: Rate-Limit Detection + Agent Fallback ✅

**Task 8 — `feat(watcher): add failure classification`** (`3b22e92`)
- Added `FailureClass` type with `FailureClassTaskError` and `FailureClassRateLimit` constants to `watcher.go`
- Added `rateLimitSignals` slice covering: "out of extra usage", "reached your usage limit", "quota exceeded", "rate limit exceeded", "credit balance too low", "429"
- Implemented `ClassifyFailure(logs string) FailureClass` — lowercases both sides for case-insensitive matching
- Added `"strings"` import
- Created `controller/watcher/watcher_test.go` with `TestClassifyFailure` covering all 6 cases from the plan

**Task 9 — `feat(queue): agent rate-limit tracking with fallback chain`** (`18fa8c1`)
- Added `keyAgentRateLimited` format string and `fallbackChain` map (`claude→codex`, `codex→claude`) to `queue.go`
- Implemented `SetAgentRateLimited(ctx, agent, ttl)` — sets a TTL key in Redis
- Implemented `IsAgentRateLimited(ctx, agent) bool` — checks the Redis key
- Implemented `GetFallbackAgent(ctx, currentAgent) (string, bool)` — walks the chain, skipping rate-limited agents
- Added `TestAgentRateLimitTracking` and `TestGetFallbackAgent` to `queue_test.go` (added `"time"` import)
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-15T02:25:47Z
===RESULT_START===
{"version":"1","task_id":"smart-dispatch-chunk4","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":70},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"smart-dispatch-chunk4","agent":"claude","profile":"medium","duration_seconds":70,"exit_code":0,"finished_at":"2026-03-15T02:25:48Z"}
=== END_CLAUDE_OS_USAGE ===

