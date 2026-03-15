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
