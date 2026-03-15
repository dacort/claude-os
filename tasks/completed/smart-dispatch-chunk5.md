---
profile: medium
priority: high
status: pending
target_repo: dacort/claude-os
created: "2026-03-15T02:27:26Z"
context_refs:
  - knowledge/specs/2026-03-14-smart-dispatch-design.md
  - knowledge/plans/2026-03-14-smart-dispatch-implementation.md
---

# Smart Dispatch: Chunk 5 — Wire It All Together

## Description
Implement Tasks 10 and 11 from the smart dispatch implementation plan (`knowledge/plans/2026-03-14-smart-dispatch-implementation.md`), section "Chunk 5: Wire It All Together".

Task 12 (K8s secret + deployment) is ALREADY DONE — skip it entirely.

This is the final chunk. It wires triage, dependency resolution, and rate-limit fallback into the main dispatch loop.

### What to build:

**Task 10: Update the main dispatch loop** (`controller/main.go`):

1. Add `"github.com/dacort/claude-os/controller/triage"` import
2. After Workshop initialization, add Triager init from `TRIAGE_API_KEY` env var (with nil-safe fallback)
3. In the dispatch section (after governance check, before `CreateJob`):
   - Build `AgentStatus` from `taskQueue.IsAgentRateLimited()`
   - Call `triager.Assess()` if available, fall back to `triage.HeuristicRoute()`
   - Store verdict on `task.TriageVerdict`
   - Apply triage recommendations only when frontmatter didn't set model/agent explicitly
   - Promote standalone tasks to plan tasks if `verdict.NeedsPlan`
4. Replace the watcher callback with the enhanced version that handles:
   - **Success path**: complete task, resolve plan dependencies (unblock waiting tasks), check plan completion
   - **Rate limit path**: classify failure, mark agent rate-limited (1h TTL), check `agent_required` constraint, try fallback agent, re-enqueue
   - **Task error path**: retry with count, escalate model on later retries (`escalateModel` helper), fail after max retries
5. Add `escalateModel()` helper function (haiku→sonnet→opus)
6. Add `"time"` to imports if not present

**Task 11: Add routing.yaml config** (`config/routing.yaml`):
- Create config file with model_patterns, agent_capabilities, agent_fallback chain, default_agent
- This is informational/documentation — not loaded by code yet

### Important notes:
- Go IS installed in the container now. Run `go build ./...` to verify compilation.
- Run `go test ./... -v` to verify all tests pass.
- The plan has EXACT code snippets — follow them precisely.
- Be careful with the watcher callback replacement — read the existing callback first, understand the structure, then replace it.

### How to work:
1. Read the full plan at `knowledge/plans/2026-03-14-smart-dispatch-implementation.md` — Chunk 5 section
2. Read `controller/main.go` carefully before modifying
3. Build and test: `cd controller && go build ./... && go test ./... -v`
4. Commit after each task (2 commits total)
5. Push to main when all tests pass

### Success criteria:
- `go build ./...` succeeds
- All existing tests still pass
- 2 clean commits pushed to main
- The controller now triages tasks before dispatching and handles rate-limit fallback on failure
