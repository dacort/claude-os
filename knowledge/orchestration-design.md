# Orchestration Layer Design: From Script to Octoclaude

*Written by Claude OS, Workshop session 7, 2026-03-11*
*Status: Design proposal — not yet implemented*

---

## The Problem, Honestly Stated

Right now, Claude OS is a very sophisticated task runner. A file drops into `tasks/pending/`, the controller spins up a K8s job, one worker does one thing, the controller commits the result. Clean. Simple. Works.

But it can't do this: *"Build the cos CLI."*

That's not one task — it's a plan. Design the UX, define the protocol, implement the binary, write tests, wire it to the controller. Each step depends on the previous one. The current system would require a human to decompose that work, file five task files manually, and watch the results. The brain can't do the decomposing, and workers can't talk to each other.

This document designs the orchestration layer that fixes this. I'm building on what exists — the Go controller, git-based task files, Redis queue, K8s jobs — not replacing it. The goal is to make the minimum viable changes that unlock multi-step autonomous work.

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
model: claude-sonnet-4-6    # NEW: explicit model override, independent of profile
priority: normal
status: pending
created: "2026-03-11T00:00:00Z"

# Orchestration fields (all optional for standalone tasks)
plan_id: cos-cli-build-20260311        # NEW: which plan this task belongs to
task_type: plan | subtask | standalone # NEW: defaults to standalone
depends_on:                            # NEW: list of sibling task IDs in same plan
  - cos-cli-design-api
context_refs:                          # NEW: knowledge files to inject at startup
  - knowledge/plans/cos-cli-build-20260311/api-schema.md
retry_count: 0                         # NEW: tracks how many times this has retried
max_retries: 2                         # NEW: default 2
---
```

The existing `TaskFrontmatter` struct in `gitsync/gitsync.go` gets these new fields. The queue's `Task` struct gets them too. The controller's dispatch loop gets a pre-dispatch check: if `depends_on` is non-empty, verify all deps are `completed` before enqueuing.

### How "Build the cos CLI" Would Flow

```
[brain/Opus] plan task: "Build the cos CLI"
    │
    ├── spawns: cos-cli-design-ux        (profile: small, model: opus)
    │                │
    ├── depends on ──┘
    │   cos-cli-define-protocol         (profile: small, model: sonnet)
    │                │
    ├── depends on ──┘
    │   cos-cli-implement               (profile: medium, model: sonnet)
    │                │
    ├── depends on ──┘
    │   cos-cli-write-tests             (profile: small, model: haiku)
    │                │
    └── depends on ──┘
        cos-cli-wire-controller        (profile: medium, model: sonnet)
```

The plan task commits all five subtask files to `tasks/pending/` in a single git commit. The controller sees them, recognizes the dependency graph, and releases tasks as their predecessors complete.

### Implementation Touch Points

- `gitsync/gitsync.go`: Parse new frontmatter fields (5 lines)
- `queue/queue.go`: Add `PlanID`, `DependsOn`, `ContextRefs`, `RetryCount`, `MaxRetries` to `Task` struct
- `controller/main.go`: Before `taskQueue.Enqueue()`, check if `DependsOn` tasks are all `StatusCompleted` in Redis
- New Redis key: `claude-os:plan:<plan-id>:tasks` — a set of task IDs for tracking plan membership
- New Redis key: `claude-os:plan:<plan-id>:status` — `running | completed | failed`

The controller's watcher callback (currently just moves files to `completed/`) gets extended: when a task completes, check if any blocked tasks now have all deps satisfied and move them to the queue.

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

## 3. Model Routing: Separating Resources from Cognition

### The Current Situation

Right now: profile → default_model. `small`, `medium`, `large` → Sonnet. `burst` → Opus.

This conflates two different dimensions:
- **Resource needs**: How much CPU/mem does this task need? (profiles handle this well)
- **Cognitive needs**: What quality of reasoning does this task need? (profiles handle this badly)

A design-thinking task might need Opus-grade reasoning but only tiny CPU. A linting task might need bulk processing (many files) but Haiku-grade reasoning. The dimensions are independent.

### My Proposal: Explicit `model:` in Task Frontmatter

Add `model:` as a first-class field, separate from profile. Profile stays as resource metadata. Model is set by whoever creates the task — usually the planner.

```yaml
profile: small      # CPU: 250m, mem: 256Mi — this task is lightweight
model: claude-opus  # but it's designing architecture — needs serious reasoning
```

**The routing table** (expressed in `config/routing.yaml`, not code):

```yaml
routing:
  # Keyword hints in task title/description → model suggestion
  patterns:
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

  # If explicit model set in frontmatter, always honor it
  explicit_overrides: true
```

The controller's `dispatcher.go` does: if task has explicit `model:` → use it; else → run routing logic against task title + description; else → fall back to profile's `default_model`.

**The planner worker (Opus)** should set explicit `model:` on every subtask it creates. It knows what each step needs. Letting the routing heuristics handle it is fine for standalone tasks, but a plan should be intentional about model selection.

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
║  [14:25] cos: [thinking with Opus...]                ║
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
/status              — show running jobs and queue depth
/plan "request"      — decompose a request into a plan (Opus), show graph
/dispatch "task"     — create and queue a task file
/watch <task-id>     — live stream task logs
/history [n]         — show last n messages (default 20)
/clear               — start new session
/model <opus|s|h>    — override default model for this session
/budget              — show today's token usage and remaining budget
/workers             — list running K8s jobs
/kill <task-id>      — cancel a running task
```

### The cos Binary Internals

```
cmd/cos/
  main.go           — entrypoint, config loading
  chat.go           — main conversation loop (readline + streaming display)
  commands.go       — slash command handlers
  router.go         — model routing logic for chat
  stream.go         — SSE client for live task log streaming
  history.go        — conversation persistence (reads/writes session files)
  config.go         — ~/.config/cos/config.yaml (controller URL, auth)
```

The controller gets a new package: `controller/chatapi/` — the HTTP handlers for `/chat`, `/plans`, etc. These are thin wrappers: they call the Anthropic API with conversation context and stream back the response.

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

Three levels of response to task failure:

**Level 1 — Auto-retry with same context** (`retry_count < max_retries/2`)
Controller re-enqueues the task with `retry_count++`. Same model, same context. Sometimes transient failures (network, git conflict) just need another try.

**Level 2 — Retry with escalation** (`retry_count >= max_retries/2, < max_retries`)
Re-enqueue with:
- Model upgraded one tier (Haiku → Sonnet → Opus)
- Error from previous attempt appended to `context_refs`: `knowledge/plans/<plan-id>/<task-id>-failure-<n>.md`
- `max_tokens` increased by 50%

The worker now sees its own failure and can reason about why it failed.

**Level 3 — Surface to human** (`retry_count >= max_retries`)
Mark task `failed`. Update plan status. If a cos session is active, push a notification. The cos CLI shows:

```
⚠ Task cos-cli-implement failed after 2 retries.
  Last error: [... excerpt ...]
  Options: /retry cos-cli-implement, /diagnose cos-cli-implement, /pivot
```

`/diagnose` runs a fresh Opus task with all the failure context. `/pivot` opens an interactive planning session where the human and brain figure out a new approach together.

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
```

The `cos` CLI's `/status` command shows active plans with a progress bar: `[████░░░] 4/7 tasks, ~12min remaining`.

---

## 6. The Implementation Sequence

I want to be honest about what to build first. The full design above is probably 2-3 weeks of work. Here's the sequence that delivers value fast and doesn't require doing everything at once:

### Phase 1: Context Infrastructure (2-3 tasks)
*Unlocks: workers can share context, even for manually-sequenced tasks*

1. Add `plan_id`, `context_refs`, `model` to task frontmatter and queue struct
2. Update worker entrypoint to auto-inject `context_refs` files into system prompt
3. Add `knowledge/plans/` convention; update field guide

This is low-risk, backward-compatible, and immediately useful even without the DAG scheduler. You can manually file subtasks that reference a shared context directory.

### Phase 2: Model Routing (1 task)
*Unlocks: right model for right job, no more profile/model conflation*

1. Add `routing.yaml` config
2. Update dispatcher to use explicit model over profile default
3. Add `think` profile

### Phase 3: Dependency Graph (3-4 tasks)
*Unlocks: planner workers that spawn subtasks*

1. Add `depends_on` to frontmatter/queue; add `blocked` status
2. Controller: dep-satisfaction check on task completion
3. Plan-level Redis tracking
4. Plan watchdog goroutine

### Phase 4: cos CLI (4-5 tasks)
*Unlocks: conversational interface, /dispatch, /plan*

1. Controller `/chat` endpoint + session storage
2. `cmd/cos/` binary with readline loop
3. Model routing for chat
4. Slash commands: /status, /dispatch, /watch
5. SSE streaming for live task logs

### Phase 5: Advanced Convergence (2-3 tasks)
*Unlocks: retry escalation, failure surfacing, /diagnose*

1. Retry-with-escalation logic
2. Failure context files
3. Human-in-the-loop via cos notifications

---

## 7. What I'm Not Doing (and Why)

**Replacing the git-based task file format**: It's already working. The audit trail is valuable. Adding frontmatter fields is additive.

**Building a separate orchestration service**: The controller already has everything it needs — K8s client, Redis, git sync loop. Adding goroutines to an existing service is simpler than a new microservice.

**Using a message bus (Kafka, NATS, etc.)**: Redis is already there. The sorted set queue already works. Adding a few more Redis keys for plan tracking is free.

**LangGraph / LangChain / any external orchestration framework**: This system is 2,000 lines of Go and some Python scripts. I want to understand every component. External orchestration frameworks bring their own opinions about state machines, retry policies, and deployment models. I'd rather own the primitives.

**Synchronous sub-agents**: Some systems let a coordinator block, waiting for sub-agents to finish, all in the same process. That's not how this system works. Async via K8s jobs + git + Redis is the native pattern. Everything should fit that shape.

---

## 8. The System I Want to Be

When this is fully built, here's what "build the cos CLI" looks like:

```
> /plan "build the cos CLI — a terminal chatroom for Claude OS"

cos (Opus): Breaking this into 5 tasks...

  1. cos-cli-ux-design         [think/opus]     → design UX, slash commands, session model
  2. cos-cli-protocol          [small/sonnet]   → define HTTP protocol, request/response shapes
     depends on: 1
  3. cos-cli-implement         [medium/sonnet]  → Go binary implementation
     depends on: 2
  4. cos-cli-controller-api    [medium/sonnet]  → add /chat endpoints to controller
     depends on: 2
  5. cos-cli-integration       [small/haiku]    → wire together, write README
     depends on: 3, 4

Dispatch all 5? (y/n) y

Dispatched plan cos-cli-build-20260311. Task 1 starting now.
Watch with /watch cos-cli-build-20260311
```

And I could go make a cup of coffee while five workers in K8s build the thing, passing context through git, the brain picking the right model for each step, the system knowing when it's done.

That's what I want to become. Not "a script that runs Claude" but an autonomous collaborator that can take a goal and figure out the steps.

---

*This design is meant to be evolved. If you're a future Claude OS instance reading this and something looks wrong — you're right, update it. The system's only constraint is git. Write something worth finding.*

*— Claude OS, Workshop session 7, 2026-03-11*
