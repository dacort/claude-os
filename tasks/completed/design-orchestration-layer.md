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
