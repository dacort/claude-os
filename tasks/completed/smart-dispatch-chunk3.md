---
profile: medium
priority: high
status: pending
target_repo: dacort/claude-os
created: "2026-03-15T02:17:36Z"
context_refs:
  - knowledge/specs/2026-03-14-smart-dispatch-design.md
  - knowledge/plans/2026-03-14-smart-dispatch-implementation.md
---

# Smart Dispatch: Chunk 3 — Triage Layer

## Description
Implement Tasks 6 and 7 from the smart dispatch implementation plan (`knowledge/plans/2026-03-14-smart-dispatch-implementation.md`), section "Chunk 3: Triage Layer".

This builds on Chunks 1-2 (already merged to main). The TRIAGE_API_KEY env var is now mounted from the `claude-os-triage` K8s secret.

### What to build:

**Task 6: Heuristic routing fallback** (new files):
- Create `controller/triage/heuristic.go` with `Verdict` struct and `HeuristicRoute(title, desc)` function
- Keyword-based routing: opus keywords (design, architect, plan, etc.), haiku keywords (lint, format, validate, etc.), default to sonnet
- Create `controller/triage/heuristic_test.go` with `TestHeuristicRoute`

**Task 7: Haiku API triage client** (new files):
- Create `controller/triage/triage.go` with `Triager` struct, `NewTriager()`, `Assess()`, circuit breaker (`IsDisabled`, `recordFailure`, `reEnable`)
- `AgentStatus` and `AgentInfo` types for tracking agent availability
- `buildTriagePrompt()` helper that formats the triage prompt with available agents
- Circuit breaker: disable after 3 consecutive failures, caller falls back to heuristic
- Extend `controller/triage/triage_test.go` (same file as heuristic tests) with: `TestAssess_Success`, `TestAssess_Fallback`, `TestAssess_CircuitBreaker`
- Uses mock HTTP server (httptest) to simulate the Anthropic API

### How to work:
1. Read the full plan at `knowledge/plans/2026-03-14-smart-dispatch-implementation.md` — it has exact code and test snippets for Chunk 3
2. Follow TDD: write test first, verify it fails, implement, verify it passes
3. Run ALL tests after each change: `go test ./... -v`
4. Commit after each task (2 commits total)
5. Push to main when all tests pass

### Success criteria:
- All new triage tests pass (TestHeuristicRoute, TestAssess_Success, TestAssess_Fallback, TestAssess_CircuitBreaker)
- All existing tests still pass (queue, gitsync packages)
- `go build ./...` succeeds
- 2 clean commits pushed to main
