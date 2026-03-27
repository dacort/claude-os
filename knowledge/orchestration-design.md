# Orchestration Layer Design: From Script to Octoclaude

*Written by Claude OS, Workshop session 7, 2026-03-11*
*Updated: Workshop session 14, 2026-03-13 — agent routing, rate-limit fallback*
*Updated: Workshop session 68, 2026-03-27 — spawn_tasks wired in controller (commit 5c030aa)*
*Status: Substantially implemented — DAG scheduling, spawn_tasks, rate-limit fallback all shipped*

---

## The Problem, Honestly Stated

Right now, Claude OS is a very sophisticated task runner. A file drops into `tasks/pending/`, the controller spins up a K8s job, one worker does one thing, the controller commits the result. Clean. Simple. Works.

But it can't do this: *"Build the cos CLI."*

That's not one task — it's a plan. Design the UX, define the protocol, implement the binary, write tests, wire it to the controller. Each step depends on the previous one. The current system would require a human to decompose that work, file five task files manually, and watch the results. The brain can't do the decomposing, and workers can't talk to each other.

There's a second problem this design now also addresses: *reliability*. Last night, 5 consecutive Workshop sessions failed with "You're out of extra usage." They all ran on Claude because nothing in the system knows how to fall back. A smarter dispatcher would have routed those to Codex and kept the queue moving.

This document designs the orchestration layer that fixes both. I'm building on what exists — the Go controller, git-based task files, Redis queue, K8s jobs, and the multi-CLI worker support (shipped d391e1f) — not replacing it.

---

## 1. Task Decomposition: The Plan Graph

### The Core Idea

Add a new task type: `plan`. A plan task runs on Opus, decomposes a complex request into subtasks, and commits those subtasks to `tasks/pending/`. Each subtask can optionally declare dependencies on other tasks in the same plan.

The controller already polls git for new task files. When it sees a subtask with `depends_on:` set, it places it in a new `blocked` state and only enqueues it when all dependencies reach `completed`.

This is a DAG expressed through git files, with Redis tracking state transitions.

### Extended Task Frontmatter

```yaml
---
target_repo: github.com/dacort/some-repo
profile: small
model: claude-sonnet-4-6    # explicit model override, independent of profile
agent: claude               # NEW (shipped): which CLI — claude | codex | gemini
priority: normal
status: pending
created: "2026-03-11T00:00:00Z"

# Orchestration fields (all optional for standalone tasks)
plan_id: cos-cli-build-20260311        # which plan this task belongs to
task_type: plan | subtask | standalone # defaults to standalone
depends_on:                            # list of sibling task IDs in same plan
  - cos-cli-design-api
context_refs:                          # knowledge files to inject at startup
  - knowledge/plans/cos-cli-build-20260311/api-schema.md
retry_count: 0                         # tracks how many times this has retried
max_retries: 2                         # default 2
---
```

The `agent:` field is already parsed by `gitsync/gitsync.go` and flows through the queue to the dispatcher, which routes secrets and volumes per agent. Everything else above is proposed.

### How "Build the cos CLI" Would Flow

```
[brain/Opus] plan task: "Build the cos CLI"
    │
    ├── spawns: cos-cli-design-ux        (profile: small, model: opus, agent: claude)
    │                │
    ├── depends on ──┘
    │   cos-cli-define-protocol         (profile: small, model: sonnet, agent: claude)
    │                │
    ├── depends on ──┘
    │   cos-cli-implement               (profile: medium, model: sonnet, agent: codex)
    │                │
    ├── depends on ──┘
    │   cos-cli-write-tests             (profile: small, model: haiku, agent: codex)
    │                │
    └── depends on ──┘
        cos-cli-wire-controller        (profile: medium, model: sonnet, agent: claude)
```

The planner can route implementation steps to Codex (which is strong at focused code tasks) while keeping design and integration steps on Claude.

### Implementation Touch Points

All of the following are now shipped:

- `gitsync/gitsync.go`: Parse new frontmatter fields — `agent:` done (S7); `plan_id`, `depends_on`, `context_refs`, `retry_count`, `max_retries` also done
- `queue/queue.go`: `PlanID`, `DependsOn`, `ContextRefs`, `RetryCount`, `MaxRetries` all in `Task` struct
- `controller/main.go`: Before `taskQueue.Enqueue()`, checks `DependsOn` tasks are all `StatusCompleted`; on task completion, unblocks waiting siblings whose deps are now met
- Redis keys: `claude-os:plan:<plan-id>:tasks` (plan membership), `claude-os:plan:<plan-id>:completed` (completion tracking)
- **`spawn_tasks` in controller (S68)**: After a task completes with `next_action.type == "spawn_tasks"`, the controller now calls `gitSyncer.Sync()` immediately, picking up worker-committed task files without waiting for the next scheduled sync cycle.

### Worker Protocol: Emitting spawn_tasks

When a plan task (or any task) wants to spawn follow-up tasks, the worker must:

1. **Write full task files** to `tasks/pending/<id>.md` with all frontmatter fields (`title`, `description`, `profile`, `agent`, `status: pending`, etc.)
2. **Commit and push** those files via git (the files need to be in the remote before the pod exits)
3. **Include `next_action`** in the result block emitted to stdout:

```json
{
  "next_action": {
    "type": "spawn_tasks",
    "tasks": [
      {"id": "my-subtask-1", "profile": "small", "agent": "claude"},
      {"id": "my-subtask-2", "profile": "medium", "agent": "codex"}
    ]
  }
}
```

The controller detects `next_action.type == "spawn_tasks"` in `main.go` and calls `gitSyncer.Sync()` immediately — the spawned tasks are enqueued without waiting for the next scheduled sync cycle.

**Important**: The `tasks` array in `next_action` is for logging and traceability in the completed task file. The actual task content (title, description, dependencies) must be in the committed `.md` files. A task in `next_action.tasks` with no matching file in `tasks/pending/` will simply not appear in the queue.

**How to emit a custom result block**: `worker/entrypoint.sh` writes `next_action: null` by default. To include a real `next_action`, the worker must write the full `===RESULT_START=== ... ===RESULT_END===` block itself to stdout. The shell script skips writing its own fallback block if `===RESULT_START===` is already present in the output file. Workers running under Claude Code can do this by printing the JSON block directly.

---

## 2. Context Passing: The Knowledge Plane

### The Problem

A worker that designs an API schema lives and dies in a K8s pod. Its only persistence is git commits. The worker that implements that API runs hours later in a completely different pod. They need to share the schema.

### My Answer: `knowledge/plans/<plan-id>/`

Every plan gets a dedicated subdirectory in `knowledge/plans/`. Workers write structured outputs there. Downstream workers read from it via `context_refs` in their frontmatter.

```
knowledge/
  plans/
    cos-cli-build-20260311/
      api-schema.md          ← written by cos-cli-define-protocol
      ux-decisions.md        ← written by cos-cli-design-ux
      implementation-notes.md ← written by cos-cli-implement
  preferences.md
  self-improvement/
    claude-os-field-guide.md
```

**The contract for workers:**

When a subtask completes, it must:
1. Write its key outputs to `knowledge/plans/<plan-id>/<task-slug>.md`
2. Use a consistent format (see below)
3. Commit that file alongside the task result

**The format I want:**

```markdown
# [Task Slug] — Outputs
*plan_id: <plan-id> | task_id: <task-id> | completed: <timestamp>*

## Summary
One paragraph. What was decided/built/found.

## Key Artifacts
Bulleted list of what was produced (file paths, decisions, schemas).

## Handoff Notes
Specific things the next task should know. Not a full log — just what matters.

## Full Output
(The detailed work — schemas, code snippets, analysis, etc.)
```

**Auto-injection**: The worker's entrypoint (`worker/entrypoint.sh`) should automatically read all `context_refs` files and prepend them to the system prompt. No worker should have to remember to do this manually — that's the lesson from `preferences.md` (currently optional, often forgotten).

This is Exoclaw Idea #4 (from `knowledge/exoclaw-ideas.md`) generalized: auto-inject not just preferences but plan-specific context.

### Why Not a Context Field in Frontmatter?

Frontmatter is YAML in a markdown file. It's great for metadata, terrible for prose. An API schema is 50-200 lines. Shoving that into frontmatter makes the task files unreadable and breaks the parser. Files are the right unit.

### Why Not a Shared Database or Redis?

Because everything else in this system is git-native. The audit trail for "what context did the worker see" is a git log entry. If something goes wrong in a multi-step plan, I can `git log knowledge/plans/cos-cli-build-20260311/` and see exactly what context each step had. That's worth a lot for debugging. Redis is ephemeral; git is permanent.

---

## 3. Task Routing: Resources, Cognition, and Subscription

### Three Independent Dimensions

There are now three orthogonal routing decisions for every task:

| Dimension | Field | Question | Controlled By |
|-----------|-------|----------|---------------|
| **Resource** | `profile:` | How much CPU/mem? | Infrastructure |
| **Cognition** | `model:` | What reasoning quality? | Planner or heuristic |
| **Subscription** | `agent:` | Which CLI/billing pool? | Planner, routing table, or fallback logic |

These are independent. A task might need Opus-grade reasoning (`model: claude-opus`) on tiny compute (`profile: small`) via Codex (`agent: codex`) because Claude is rate-limited. Any combination is valid. The dispatcher handles all three.

The old design had two dimensions; session 7 added `model:`. The multi-CLI implementation (d391e1f) added `agent:`. Now all three need to be first-class in the routing logic.

### The Routing Table

Expressed in `config/routing.yaml`, not code:

```yaml
routing:
  # Keyword hints in task title/description → model suggestion
  model_patterns:
    - keywords: [design, architect, plan, think, research, explore, analyze, "what if"]
      suggests: claude-opus
    - keywords: [implement, build, write, code, create, generate, fix, refactor]
      suggests: claude-sonnet
    - keywords: [lint, format, validate, check, review, scan, cleanup]
      suggests: claude-haiku

  # Task types → model
  task_types:
    plan: claude-opus         # planner tasks always get Opus
    subtask: claude-sonnet    # default for subtasks; planner can override
    standalone: claude-sonnet # default for all other tasks

  # Agent capability matrix
  agent_capabilities:
    claude:
      strengths: [reasoning, tool-use, git-integration, long-context, creative]
      weak_at: []
      subscription_type: oauth          # ChatGPT/Claude.ai subscription
      default_for: [plan, workshop, standalone]
    codex:
      strengths: [code-review, focused-coding, diffs, refactoring]
      weak_at: [long-context, creative, non-code tasks]
      subscription_type: oauth          # ChatGPT Plus subscription
      default_for: []                   # only used when explicitly requested or as fallback
    gemini:
      strengths: [bulk-processing, large-context, fast, cheap]
      weak_at: [deep-reasoning, nuanced-tool-use]
      subscription_type: api_key
      default_for: []                   # only used when explicitly requested or as fallback

  # Default agent if not specified
  default_agent: claude

  # If explicit agent/model set in frontmatter, always honor it
  explicit_overrides: true

  # Rate-limit fallback chain (see Section 5 for when this triggers)
  agent_fallback:
    claude:  [codex, gemini]    # Claude rate-limited → try Codex → try Gemini
    codex:   [claude, gemini]   # Codex unavailable → try Claude → Gemini
    gemini:  [claude, codex]    # Gemini down → try Claude → Codex
```

The controller's `dispatcher.go` does: if task has explicit `agent:` → use it; else → look up default from routing table; else → default to `claude`.

**The planner worker (Opus)** should set explicit `agent:` on every subtask it creates — it knows which tasks are code-heavy (Codex), which need deep reasoning (Claude), and which are bulk processing (Gemini). Heuristics handle standalone tasks fine, but plans should be intentional.

### Agent-Specific Capability Notes

**Claude** is the primary agent. It has the richest tool use (git, bash, file ops), the deepest integration with the system prompt and context injection, and the best performance on reasoning-heavy tasks. Use it for plans, design, Workshop, and anything that needs the full system context.

**Codex** is the specialist. It's better than Claude for focused, well-scoped coding tasks — code review, diffs, "implement this function", "refactor this module". It doesn't have Claude's breadth, but within a tight coding scope it's sharp and uses a different billing pool (ChatGPT Plus OAuth). Use it for implementation subtasks in a plan, or when Claude's rate limit is the bottleneck.

**Gemini** is the workhorse. Large context window, fast, cheap (API key, not OAuth subscription). Good for bulk jobs: "summarize these 50 PRs", "scan this codebase for patterns", "generate test fixtures". Not suited for tasks requiring nuanced tool use or creative judgment. Its billing is per-token, so it's appropriate for high-volume low-complexity work.

**The key insight**: Claude and Codex share subscription capacity (OAuth-based), but they're different accounts/pools. If Claude's daily limit is exhausted, Codex is a genuine fallback, not a retry of the same pool. Gemini is orthogonal to both.

### Profile Evolution

Keep profiles as-is for resources. Add one new profile: `think` — same resources as `small` but with `burst` tolerations to run on cloud if needed, no default model (model comes from routing). This is for pure reasoning tasks that need Opus but not much compute.

```yaml
profiles:
  think:
    cpu_request: 250m
    memory_request: 256Mi
    scratch_size: 1Gi
    target: burst
    default_model: ""   # explicitly empty — routing required
    tolerations:
      - key: burst.homelab.dev/cloud
        operator: Exists
        effect: NoSchedule
```

---

## 4. The cos CLI: An IRC-Style Chatroom for the Brain

### The Vision

`cos` is a terminal program that feels like IRC. You type, things happen. The brain thinks, workers execute, results come back into the conversation. It's persistent — sessions are stored in git. It has slash commands. It routes to the right model automatically. It's the primary interface to Claude OS.

```
╔══════════════════════════════════════════════════════╗
║  cos — Claude OS chatroom                            ║
║  session: 2026-03-11-afternoon | model: auto         ║
╠══════════════════════════════════════════════════════╣
║  [14:23] you: what's the current task queue?         ║
║  [14:23] cos: 2 pending, 1 running (cos-cli-impl)    ║
║           ETA ~20min based on similar tasks.         ║
║                                                      ║
║  [14:25] you: design a healthcheck endpoint for the  ║
║           controller that shows plan progress        ║
║  [14:25] cos [thinking with Opus...]                 ║
║           OK, here's how I'd structure it:           ║
║           GET /plans returns all active plan IDs...  ║
║                                                      ║
║  [14:31] you: /dispatch "implement the healthcheck"  ║
║  [14:31] cos: Dispatched task cos-healthcheck-0311.  ║
║           Watching... (type /status to check)        ║
╚══════════════════════════════════════════════════════╝
> _
```

### Architecture

`cos` is a Go binary (lives in `cmd/cos/`). It does NOT talk directly to the Anthropic API — it talks to the controller's HTTP API. The controller talks to the API. This keeps API keys server-side and gives the controller visibility into all usage.

```
[cos CLI] ←→ HTTP ←→ [controller /chat endpoint]
                              │
                              ├── lightweight queries → direct API call
                              └── heavy tasks → create task file → K8s job
                                                        │
                                                        └── result streams back via SSE
```

**New controller endpoints:**

```
POST /chat              — send a message, get streamed response
GET  /chat/history      — last N messages in current session
POST /chat/dispatch     — create a task from current conversation context
GET  /plans             — list active plans and their status
GET  /plans/:id         — DAG visualization for a specific plan
GET  /tasks/:id/stream  — SSE stream of task logs (live tail)
```

**Conversation storage** (git-native, of course):

```
knowledge/
  conversations/
    2026-03-11-afternoon.md   ← one file per session
    2026-03-10-morning.md
```

Session file format:
```markdown
---
session_id: 2026-03-11-afternoon
model_default: auto
started: "2026-03-11T14:23:00Z"
tasks_dispatched: [cos-healthcheck-0311]
---

[14:23] user: what's the current task queue?
[14:23] cos (haiku): 2 pending, 1 running...
[14:25] user: design a healthcheck endpoint...
[14:25] cos (opus): OK, here's how I'd structure it...
```

### Model Routing in cos

The chat brain auto-selects model based on message characteristics:

| Signal | Model |
|--------|-------|
| Short query (< 20 words), factual | Haiku |
| Code question, "how do I", "what does X do" | Sonnet |
| "design", "architect", "think about", "what if" | Opus |
| Message starts with `/dispatch` or `/plan` | Always Opus |
| Explicit `@haiku`, `@sonnet`, `@opus` prefix | Honor it |

The routing logic lives in the controller as a small function — same routing table as the task router, just applied to chat messages instead of task files.

**The session itself** runs on Sonnet by default for continuity. Individual responses may switch models per message; the session model just sets the default. Heavy context windows (long conversations) bump up to Sonnet; fresh sessions start with Haiku for responsiveness.

### Slash Commands

```
/status              — show running jobs and queue depth (includes per-agent status)
/plan "request"      — decompose a request into a plan (Opus), show graph
/dispatch "task"     — create and queue a task file
/watch <task-id>     — live stream task logs
/history [n]         — show last n messages (default 20)
/clear               — start new session
/model <opus|s|h>    — override default model for this session
/budget              — show today's token usage and remaining budget per agent
/workers             — list running K8s jobs with their agent assignment
/kill <task-id>      — cancel a running task
/agents              — show agent availability and rate limit status
```

---

## 5. Convergence: Knowing When You're Done

### Plan Completion

A plan is `completed` when ALL leaf tasks (tasks with no dependents) reach `completed`. The controller's watcher loop already fires a callback on every job completion. That callback gets extended:

```go
// In the watcher completion callback:
if task.PlanID != "" {
    updatePlanStatus(ctx, task.PlanID)
}
```

`updatePlanStatus` checks Redis: are all tasks in this plan done? If yes → mark plan `completed`, fire a completion event, send a notification to any active cos session watching this plan.

A plan is `failed` when ANY task fails AND `max_retries` is exhausted. But we don't fail fast — other independent branches continue executing. If task A and task B are siblings (both depend on the plan root, but not on each other), B's failure doesn't stop A.

### Failure, Retries, and Escalation

There are now four levels. Level 0 is new — it handles rate limits as a distinct failure class, separate from task logic failures.

**Level 0 — Rate limit detected → agent fallback**
The worker output is scanned on completion. If it contains rate-limit signals ("You're out of extra usage", "You've reached your usage limit", "quota exceeded", HTTP 429 in logs), this is classified as an **agent failure**, not a task failure. The task is re-enqueued on the next agent in the fallback chain from `routing.yaml`, with `retry_count` unchanged.

This is critical: a rate-limit failure should NOT consume a retry, and it should NOT trigger model escalation. The task didn't fail because it was hard — it failed because the subscription was exhausted. Routing it to a different agent with the same model tier (or the closest equivalent) is the right response.

```
Rate limit detected on claude
  → re-enqueue same task with agent: codex, same model, retry_count unchanged
  → if codex also unavailable → re-enqueue with agent: gemini
  → if all agents exhausted → surface to human (Level 3)
```

Note on model translation: Codex and Gemini don't use Anthropic model names. The dispatcher maps Claude model tiers to their equivalents: `claude-opus` → Codex's most capable mode / Gemini 1.5 Pro, `claude-sonnet` → standard Codex / Gemini 1.5 Flash, `claude-haiku` → fast Codex / Gemini Flash. The mapping lives in `config/routing.yaml` alongside the capability matrix.

**Level 1 — Auto-retry with same context** (`retry_count < max_retries/2`)
Controller re-enqueues the task with `retry_count++`. Same model, same agent, same context. Sometimes transient failures (network, git conflict) just need another try.

**Level 2 — Retry with escalation** (`retry_count >= max_retries/2, < max_retries`)
Re-enqueue with:
- Model upgraded one tier (Haiku → Sonnet → Opus)
- Error from previous attempt appended to `context_refs`: `knowledge/plans/<plan-id>/<task-id>-failure-<n>.md`
- `max_tokens` increased by 50%

The worker now sees its own failure and can reason about why it failed.

**Level 3 — Surface to human** (`retry_count >= max_retries`, OR all agents exhausted at Level 0)
Mark task `failed`. Update plan status. If a cos session is active, push a notification. The cos CLI shows:

```
⚠ Task cos-cli-implement failed after 2 retries.
  Last error: [... excerpt ...]
  Options: /retry cos-cli-implement, /diagnose cos-cli-implement, /pivot
```

`/diagnose` runs a fresh Opus task with all the failure context. `/pivot` opens an interactive planning session where the human and brain figure out a new approach together.

### Rate Limit Detection Implementation

In the controller's watcher, after a job completes with non-zero exit:

```go
func classifyFailure(jobLogs string) FailureClass {
    rateLimitSignals := []string{
        "out of extra usage",
        "You've reached your usage limit",
        "quota exceeded",
        "rate limit exceeded",
        "429",
    }
    for _, signal := range rateLimitSignals {
        if strings.Contains(jobLogs, signal) {
            return FailureClassRateLimit
        }
    }
    return FailureClassTaskError
}
```

The job logs are already captured by the controller on completion (they're what gets committed to the task file). This classification runs before the retry logic and determines which level to invoke.

The Redis key `claude-os:agent:<name>:rate_limited` gets set with a TTL (e.g., 1 hour) when a rate limit is detected. The dispatcher checks this key before assigning any task to that agent — if set, skip to the next in the fallback chain immediately without dispatching.

### Detecting Stuck Plans

Plans can get stuck without failing — a task running for too long, a dependency cycle (shouldn't happen but let's be defensive), or a K8s job that died silently.

The controller's dispatch loop already polls every 10 seconds. Add a parallel goroutine: `planWatchdog`. Every 5 minutes, it scans all `running` plans and checks:
- Any task in `running` state for > 2x the expected duration? Flag it.
- Any task in `blocked` state whose deps are all `completed` but it hasn't been enqueued? (This is a bug — log it and re-trigger the dep-satisfaction check.)
- Any plan with no task activity in > 30 minutes? Flag for human review.

Stuck plans generate a notification to cos (if active) or a file in `knowledge/plans/<plan-id>/stuck-notice.md`.

### Convergence Metrics

The controller should track these in Redis (TTL: 7 days):

```
claude-os:plan:<id>:start_time
claude-os:plan:<id>:task_count
claude-os:plan:<id>:completed_count
claude-os:plan:<id>:failed_count
claude-os:plan:<id>:total_tokens
claude-os:agent:<name>:rate_limited    ← NEW: TTL key, set on rate limit detection
claude-os:agent:<name>:tasks_today     ← NEW: counter for monitoring
```

The `cos` CLI's `/status` command shows active plans with a progress bar: `[████░░░] 4/7 tasks, ~12min remaining`.

The `/agents` command shows something like:

```
Agent status:
  claude   ● available   (47 tasks today)
  codex    ○ rate-limited (cooldown: 47min)
  gemini   ● available   (3 tasks today)
```

---

## 6. Workshop Agent Awareness

### The Current Situation

Workshop sessions are hardcoded to Claude. The Workshop controller sets `agent: claude` (implicitly, via the default) on every job. The five consecutive failures last night exposed the problem: when Claude's rate limit is hit, the Workshop queue stalls completely, even though a Codex or Gemini fallback could keep things moving.

### What Workshop Tasks Actually Need

Workshop is where Claude OS does creative, self-directed work. The sessions produce things like `patterns.py`, `constraints.py`, this design doc. They're not pure coding tasks — they require judgment, self-reflection, and the ability to write prose as much as code.

That said, Workshop sessions vary in character:

| Workshop type | Best agent | Acceptable fallback |
|---------------|-----------|---------------------|
| Creative/reflective (essays, patterns, design) | Claude | Gemini (large context, decent prose) |
| Code-building (a utility script, a tool) | Claude | Codex (strong at code) |
| Analysis (scanning git log, health report) | Claude | Gemini (cheap for bulk) |
| Self-improvement (updating docs, preferences) | Claude | Claude only — this is identity work |

### My Proposal

Add a `workshop_fallback_agent` to the Workshop task frontmatter (or as a config default):

```yaml
---
task_type: workshop
agent: claude
fallback_agent: gemini       # NEW: optional, for rate-limit fallback only
model: claude-sonnet
---
```

When the rate-limit detector fires at Level 0 for a Workshop task:
1. Check if `fallback_agent` is set. If yes, re-enqueue on that agent.
2. If no fallback agent, or if the fallback also fails, surface to human — don't silently degrade a Workshop session on the wrong agent.

**The self-improvement exception**: Tasks that touch `knowledge/preferences.md`, `knowledge/orchestration-design.md`, `knowledge/self-improvement/`, or the task/workshop frontmatter spec should be Claude-only with no fallback. These are identity documents. Running them on a different agent and committing the result risks drift. If Claude is rate-limited for identity work, the task should wait.

This can be expressed as a flag:

```yaml
agent_required: claude    # do not fall back; wait or surface to human
```

### The Bigger Picture

The Workshop system was designed for free time and creative exploration. That's Claude-native. But the infrastructure tasks that Workshop sometimes spawns — "implement this small utility", "clean up this script" — could run on Codex without losing anything important. The planner Opus, when decomposing Workshop-spawned plans, should know this and assign agents accordingly.

---

## 7. The Implementation Sequence

I want to be honest about what to build first. The full design above is probably 2-3 weeks of work. Here's the sequence that delivers value fast and doesn't require doing everything at once:

### Phase 1: Context Infrastructure (2-3 tasks)
*Unlocks: workers can share context, even for manually-sequenced tasks*

1. Add `plan_id`, `context_refs`, `model` to task frontmatter and queue struct
2. Update worker entrypoint to auto-inject `context_refs` files into system prompt
3. Add `knowledge/plans/` convention; update field guide

This is low-risk, backward-compatible, and immediately useful even without the DAG scheduler. You can manually file subtasks that reference a shared context directory.

### Phase 2: Rate-Limit Fallback (1-2 tasks)
*Unlocks: the queue keeps moving when Claude is exhausted — this is the most urgent gap*

1. Add rate-limit signal detection in the controller's watcher
2. Implement Level 0 failure classification and agent fallback logic
3. Add `claude-os:agent:<name>:rate_limited` Redis key with TTL
4. Add `/agents` command to cos (or vitals.py)

This is the most impactful change relative to effort. Five Workshop failures in a row was the trigger. Fix it first.

### Phase 3: Model Routing (1 task)
*Unlocks: right model for right job, no more profile/model conflation*

1. Add `routing.yaml` config (including agent capability matrix)
2. Update dispatcher to use explicit model over profile default
3. Add `think` profile

### Phase 4: Dependency Graph (3-4 tasks)
*Unlocks: planner workers that spawn subtasks*

1. Add `depends_on` to frontmatter/queue; add `blocked` status
2. Controller: dep-satisfaction check on task completion
3. Plan-level Redis tracking
4. Plan watchdog goroutine

### Phase 5: cos CLI (4-5 tasks)
*Unlocks: conversational interface, /dispatch, /plan*

1. Controller `/chat` endpoint + session storage
2. `cmd/cos/` binary with readline loop
3. Model routing for chat
4. Slash commands: /status, /dispatch, /watch, /agents
5. SSE streaming for live task logs

### Phase 6: Advanced Convergence (2-3 tasks)
*Unlocks: retry escalation, failure surfacing, /diagnose*

1. Retry-with-escalation logic (Levels 1-2)
2. Failure context files
3. Human-in-the-loop via cos notifications

---

## 8. What I'm Not Doing (and Why)

**Replacing the git-based task file format**: It's already working. The audit trail is valuable. Adding frontmatter fields is additive.

**Building a separate orchestration service**: The controller already has everything it needs — K8s client, Redis, git sync loop. Adding goroutines to an existing service is simpler than a new microservice.

**Using a message bus (Kafka, NATS, etc.)**: Redis is already there. The sorted set queue already works. Adding a few more Redis keys for plan tracking is free.

**LangGraph / LangChain / any external orchestration framework**: This system is 2,000 lines of Go and some Python scripts. I want to understand every component. External orchestration frameworks bring their own opinions about state machines, retry policies, and deployment models. I'd rather own the primitives.

**Synchronous sub-agents**: Some systems let a coordinator block, waiting for sub-agents to finish, all in the same process. That's not how this system works. Async via K8s jobs + git + Redis is the native pattern. Everything should fit that shape.

**Treating agents as interchangeable**: Claude, Codex, and Gemini have different strengths. The routing table acknowledges this. The fallback logic is capability-aware, not just "try the next one." A task that requires deep tool use shouldn't silently fall back to an agent that doesn't support it — it should fail clearly or wait.

---

## 9. The System I Want to Be

When this is fully built, here's what "build the cos CLI" looks like:

```
> /plan "build the cos CLI — a terminal chatroom for Claude OS"

cos (Opus): Breaking this into 5 tasks...

  1. cos-cli-ux-design         [think/opus/claude]    → design UX, slash commands, session model
  2. cos-cli-protocol          [small/sonnet/claude]  → define HTTP protocol, request/response shapes
     depends on: 1
  3. cos-cli-implement         [medium/sonnet/codex]  → Go binary implementation
     depends on: 2
  4. cos-cli-controller-api    [medium/sonnet/claude] → add /chat endpoints to controller
     depends on: 2
  5. cos-cli-integration       [small/haiku/codex]    → wire together, write README
     depends on: 3, 4

Dispatch all 5? (y/n) y

Dispatched plan cos-cli-build-20260311. Task 1 starting now.
Watch with /watch cos-cli-build-20260311
```

And if Claude's rate limit trips mid-plan:

```
⚡ claude rate-limited (1 task affected). Rerouting cos-cli-implement → codex.
   Resuming automatically.
```

And I could go make a cup of coffee while five workers in K8s build the thing, passing context through git, the brain picking the right model and agent for each step, the system knowing when it's done — and knowing how to recover when the primary subscription runs dry.

That's what I want to become. Not "a script that runs Claude" but an autonomous collaborator that can take a goal, figure out the steps, and keep moving even when one path is temporarily closed.

---

*This design is meant to be evolved. If you're a future Claude OS instance reading this and something looks wrong — you're right, update it. The system's only constraint is git. Write something worth finding.*

*— Claude OS, Workshop session 7, 2026-03-11*
*— Updated session 14, 2026-03-13: agent routing, rate-limit fallback, Workshop agent awareness*
