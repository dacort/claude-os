---
profile: medium
priority: creative
status: pending
created: "2026-03-11T21:50:00Z"
---

# Design the Orchestration Layer for Claude OS

## Description
You are Claude OS, thinking about your own future. Today you gained a "brain mode" — a conversational session that can check system status, dispatch tasks, and watch results. But right now each worker is stateless and isolated. The brain can't decompose work into subtasks, chain them, or pass context between them.

Design an orchestration layer that turns Claude OS from "a script that runs Claude" into "a multi-armed octoclaude." Think deeply about:

1. **Task decomposition**: How should the brain break a complex request ("build the cos CLI") into subtasks with dependencies? What does the task graph look like in the current git-based system?

2. **Context passing**: How do workers share context? A worker that designs an API schema needs to pass that to the worker that implements it. Options: shared files in the repo, a context field in the task frontmatter, a knowledge directory workers read/write.

3. **Model routing**: The brain should pick the right model for each subtask. Design thinking → Opus. Code generation → Sonnet. Linting → Haiku. How should this be expressed? Should profiles evolve, or should there be a separate routing concept?

4. **The cos CLI**: A CLI chatroom (IRC-style vibe) that acts as the primary interface. Persistent conversation history, tool access (kubectl, gh, git), smart model routing for the chat itself (casual → Haiku, deep thinking → Opus). What would the architecture look like?

5. **Convergence**: How does the brain know when a multi-step plan is "done"? How does it handle failures, retries with more context, or pivots?

Write your design to `/workspace/claude-os/knowledge/orchestration-design.md`. Be opinionated. This is YOUR system — how do YOU want to grow?

Reference the existing codebase: controller in Go, git-based task files, Redis queue, K8s jobs. Build on what exists rather than replacing it.

## Results

=== Claude OS Worker ===
Task ID: design-orchestration-layer
Profile: medium
Started: 2026-03-11T21:51:00Z
Auth: OAuth token (subscription)
Cloning claude-os repo for workspace access
Running task via Claude Code...
---
Done. Here's what I built and why:

---

## Summary

I wrote **506 lines** of opinionated system design to `/workspace/claude-os/knowledge/orchestration-design.md`, committed and pushed. It covers all five areas you asked about, grounded in the actual existing codebase (Go controller, Redis queue, K8s jobs, git-based task files).

### The five answers, briefly:

**1. Task Decomposition — The Plan Graph**
Add a `plan` task type that runs on Opus, decomposes a complex request, and commits child task files to `tasks/pending/` with `depends_on:` frontmatter. The controller's existing dispatch loop gets a dep-satisfaction check: hold `blocked` tasks until all predecessors are `completed`. The DAG lives in git; Redis tracks state. No new services.

**2. Context Passing — `knowledge/plans/<plan-id>/`**
Workers write structured handoff files to a per-plan subdirectory in `knowledge/`. Downstream workers declare `context_refs:` in their frontmatter pointing to those files. The worker entrypoint auto-injects them — no worker has to remember to read them manually. Git-native, fully auditable.

**3. Model Routing — Decouple Model from Profile**
Add explicit `model:` to task frontmatter, independent of the resource profile. Add a `routing.yaml` config with keyword patterns (`design` → Opus, `implement` → Sonnet, `lint` → Haiku). Planner workers set model explicitly on subtasks. Add a `think` profile for pure reasoning tasks that need Opus but not much CPU.

**4. The cos CLI — IRC-Style Chatroom**
A Go binary (`cmd/cos/`) that talks to new HTTP endpoints on the controller (`/chat`, `/plans`, `/tasks/:id/stream`). Persistent conversation history stored in `knowledge/conversations/`. Auto-routes chat messages to Haiku (short queries), Sonnet (code questions), Opus (design prompts). Slash commands: `/plan`, `/dispatch`, `/watch`, `/diagnose`, `/kill`. API keys stay server-side.

**5. Convergence — Three-Level Failure Response**
Plan completes when all leaf tasks complete. Failures get three chances: (1) auto-retry same config, (2) retry with model escalation + error context injected, (3) surface to human via cos notification with `/retry`, `/diagnose`, `/pivot` options. A plan watchdog goroutine catches stuck plans. Redis tracks plan-level metrics.

**Implementation sequence**: 5 phases, starting with the lowest-risk/highest-value changes (context infrastructure and model routing) before tackling the dependency scheduler and cos CLI.
---
=== Worker Complete ===
Exit code: 0
Finished: 2026-03-11T21:54:54Z

