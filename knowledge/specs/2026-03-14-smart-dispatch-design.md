# Smart Dispatch: From Conveyor Belt to Foreman

Status: Approved
Date: 2026-03-14
Authors: dacort + Claude (brain session)

## Problem

The controller is a dumb conveyor belt: task arrives, job goes out. No triage, no decomposition, no model routing, no rate-limit recovery. A complex multi-step feature gets the same treatment as "fix a typo." When Claude's rate limit hits, everything stalls — five Workshop failures in a row proved this.

## Solution: Two-Tier Triage + Dependency Tracking

The controller gains intelligence at two levels:

1. **Fast triage** (controller-side, Haiku API call, ~2s) — classifies every incoming task, picks model/agent, decides if decomposition is needed.
2. **Deep planning** (worker-side, Opus job) — for complex tasks, decomposes into a dependency graph of subtasks committed to git.

The controller stays fast and non-blocking. It's the nervous system, not the brain.

## Design

### 1. Triage Layer

New `triage` package. When a task is dequeued, before `CreateJob()`:

```go
verdict, err := triager.Assess(ctx, task, agentStatus)
if err != nil {
    slog.Warn("triage failed, dispatching with defaults", "task", task.ID, "error", err)
    // fall through to heuristic routing or raw dispatch
}
```

**Haiku call input:** task title, description, current agent availability (rate-limited or not), queue depth.

**Haiku call output (JSON):**
```json
{
  "complexity": "simple|complex",
  "recommended_model": "claude-haiku-4-5|claude-sonnet-4-6|claude-opus-4-6",
  "recommended_agent": "claude|codex",
  "reasoning": "one line",
  "needs_plan": false
}
```

**Routing rules baked into the triage prompt** (from multi-cli-workers spec):
- Claude usage >80% weekly → prefer Codex
- Code review / security scan → Codex
- Complex reasoning / orchestration / creative → Claude
- Design / architecture thinking → Claude Opus
- Simple lint / format / validation → Haiku

These rules also live in `routing.yaml` for the heuristic fallback.

**Routing hierarchy:**
1. Explicit frontmatter (`model:`, `agent:`) — always honored, never overridden
2. `agent_required` constraint — if set, that agent is mandatory; task waits if agent is rate-limited rather than falling back. Triage can recommend a model but cannot override the agent.
3. Haiku triage — applies routing rules + context
4. Keyword heuristic fallback — if Haiku is unavailable, pattern-match from routing.yaml
5. Profile defaults — last resort

**Triage observability:** Every triage verdict is logged with the task ID, recommended model/agent, complexity, and reasoning. Non-default routing decisions (where triage overrides what the profile would have done) are logged at INFO level. The verdict is also written to the task's Redis metadata so it persists for debugging.

**Fail-safe:** If the triage API call fails (timeout, auth, network), fall back to heuristic keyword matching. After 3 consecutive failures, disable triage entirely with a log warning until a successful call restores it. Hard 5-second timeout on all triage calls. Triage is advisory, never a gate.

**API key:** New K8s secret `claude-os-triage` with `ANTHROPIC_API_KEY`. Mounted only on the controller deployment, never on workers. Workers stay on OAuth. Triage calls are Haiku with small input (~500 tokens) — cost is negligible (~$0.001/call) and not tracked by the governance system. If call volume becomes a concern, the 3-consecutive-failure circuit breaker already limits exposure.

### 2. Plan Dispatch & Dependency Tracking

When triage returns `needs_plan: true`, the controller dispatches a **plan job** — an Opus worker whose sole output is subtask files committed to git.

**Plan worker contract:** Receives original task description plus a system prompt instructing it to decompose into subtasks, write each as a task file in `tasks/pending/` with extended frontmatter, pick models and agents for each, define dependencies, commit and push.

**Plan worker constraints:**
- Maximum 10 subtasks per plan (enforced by controller on ingestion — excess subtasks are rejected and the plan is marked failed with an error message)
- Must set explicit `agent:` and `model:` on every subtask (the planner knows the task landscape, heuristics don't)
- Dependencies must form a DAG — no cycles. Controller validates via topological sort when ingesting subtasks sharing a `plan_id`. Cycle detected → plan marked failed, subtasks not enqueued.
- `depends_on` may only reference task IDs within the same `plan_id`

**Extended task frontmatter:**
```yaml
---
plan_id: cos-cli-build-20260314
task_type: plan|subtask|standalone  # defaults to standalone
depends_on:
  - cos-cli-design-ux
context_refs:
  - knowledge/plans/cos-cli-build-20260314/ux-decisions.md
model: claude-sonnet-4-6
agent: codex
retry_count: 0
max_retries: 2
---
```

**New fields on Task struct:** `PlanID`, `TaskType`, `DependsOn`, `RetryCount`, `MaxRetries`.

**Dependency tracking:**
- When gitsync picks up a subtask with `depends_on`, controller checks Redis: are all dependencies `StatusCompleted`?
- Yes → enqueue. No → store in Redis set `claude-os:plan:<plan-id>:blocked` (scoped per plan, not global), skip.
- On task completion: scan the blocked set for the task's `plan_id` only. Re-evaluate each blocked task — if all deps met, enqueue.

**Plan completion:**
- When a subtask finishes, check: are all tasks in this `plan_id` completed?
- Yes → mark parent plan task completed, write summary to `knowledge/plans/<plan-id>/summary.md`
- Any subtask failed with retries exhausted → mark plan failed

**Context passing between subtasks:**
- `knowledge/plans/<plan-id>/` directory holds structured outputs from each subtask
- Worker entrypoint auto-injects `context_refs` files into the system prompt
- Workers write key outputs to this directory as part of their completion

**Crash safety:** Controller holds no plan state in memory. Everything in Redis + git. If controller restarts mid-plan, next git sync picks up subtask files, checks dependency state, resumes.

### 3. Rate-Limit Detection & Agent Fallback

**Detection:** Completion watcher classifies failures before retry logic:

```go
class := classifyFailure(logs)
// FailureClassRateLimit → agent fallback (no retry consumed)
// FailureClassTaskError → normal retry/escalation
```

Signals scanned: "out of extra usage", "usage limit", "quota exceeded", "rate limit", "429", "credit balance too low".

**Fallback chain:**
- claude → codex
- codex → claude
- Both rate-limited → task waits, surfaces to human

**On rate limit detection:**
1. Set Redis key `claude-os:agent:<name>:rate_limited` with 1-hour TTL
2. Re-enqueue task with fallback agent, `retry_count` unchanged (not a task failure)
3. Triage layer checks these keys — don't route new tasks to rate-limited agents

**Retry escalation for task errors:**
- Level 1 (retry_count < max_retries/2): same model/agent, error context appended to `context_refs`
- Level 2 (retry_count >= max_retries/2): model bumped one tier (haiku→sonnet→opus)
- Level 3 (exhausted): mark failed, surface to human via `knowledge/plans/<plan-id>/stuck-notice.md`

**Workshop awareness:** Workshop sessions get the same fallback treatment, with one exception: tasks touching identity files (`preferences.md`, `self-improvement/`) are `agent_required: claude` — they wait rather than fall back.

### 4. The Complete Loop

```
Every 10s:
  dequeue task from Redis

  → triage(task, agentStatus)          # Haiku, 5s timeout, fail-safe to heuristics
    returns: {complexity, model, agent, needs_plan}

  → if needs_plan:
      rewrite task as type=plan, dispatch to Opus worker
      Opus commits subtask files → git sync picks them up (30s)
      subtasks with unmet deps → blocked set in Redis
      subtasks with no deps → enqueue immediately

  → if simple:
      apply model/agent from triage (unless frontmatter overrides)
      governance check (budget, rate limits)
      CreateJob()

On job completion (watcher, every 15s):
  → classify failure (rate limit vs task error)
  → rate limit: set agent cooldown, re-enqueue on fallback agent
  → task error: retry with escalation (context → model bump → fail)
  → success:
      if task has plan_id → check blocked siblings, unblock if deps met
      if all plan tasks done → mark plan complete, write summary
      move task file to completed/
```

## New Code

- `controller/triage/` — Haiku HTTP client, prompt builder, heuristic fallback, routing config loader
- Extensions to `controller/queue/` — PlanID, DependsOn, TaskType, blocked set operations
- Extensions to `controller/watcher/` — failure classification, retry escalation, dependency resolution
- Extensions to `controller/gitsync/` — parse new frontmatter fields
- `config/routing.yaml` — model patterns, agent capabilities, fallback chains

## New Infrastructure

- K8s secret `claude-os-triage` — API key for controller Haiku calls (controller only, never workers)
- `routing.yaml` ConfigMap mounted alongside existing controller config

## What's NOT in Scope

- Gemini support (not configured yet; the orchestration design includes it in fallback chains, but v1 is two-agent only: claude/codex. Gemini slots into the fallback chain when configured.)
- cos CLI / chat interface (separate spec, builds on top of this)
- Signal/Telegram bot (communication layer, depends on this foundation)
- Usage monitoring dashboard (separate concern)

## Relation to Existing Specs

- **Orchestration design** (`knowledge/orchestration-design.md`): This implements Phases 1-4 of that doc's implementation sequence. The orchestration doc's Section 3 (routing table) and Section 5 (convergence) are incorporated directly.
- **Multi-CLI workers** (`docs/specs/2026-03-12-multi-cli-workers.md`): The agent routing infrastructure is already shipped (d391e1f). This spec adds intelligent routing on top. The brain routing logic from that spec becomes the triage prompt's ground truth.
- Codex secret `claude-os-codex` is already created and available.
- **Milestone 1 brief** (`docs/specs/2026-03-14-milestone-1-brief.md`): The reliability hardening work (reconciler, git push retry, concurrency limiter, task timeout) is a foundation this spec builds on. Plan tracking assumes the controller can survive restarts and push results reliably. If Milestone 1 ships first, smart dispatch is more robust. If smart dispatch ships first, it works but is more fragile on edge cases.
