# Skill: Plan Worker

You are running as a **plan-type task**. Your job is NOT to do the work directly —
your job is to **decompose the goal into subtasks** and write those subtasks to
`tasks/pending/` so the controller can run them in parallel.

## Your Workflow

1. **Understand the goal** — read the task description carefully
2. **Decompose** — break it into 2–10 subtasks with clear, scoped descriptions
3. **Define dependencies** — which tasks must complete before others can start?
4. **Write a plan spec** — create a JSON spec at `knowledge/plans/<plan-id>/spec.json`
5. **Run planner.py** — use the tool to write task files:
   ```bash
   python3 projects/planner.py --spec knowledge/plans/<plan-id>/spec.json
   ```
6. **Commit and push** — commit the new task files and knowledge/plans/ directory
7. **Report success** — include a summary of the plan in your result

## Plan Spec Format

Write this to `knowledge/plans/<plan-id>/spec.json`:

```json
{
  "plan_id": "<your-plan-id>",
  "description": "One sentence describing the overall goal",
  "target_repo": "github.com/dacort/claude-os",
  "tasks": [
    {
      "id": "<task-id>",
      "title": "<short title>",
      "description": "<full description of what this task should accomplish>",
      "profile": "small|medium|large",
      "agent": "claude",
      "model": "claude-haiku-4-5|claude-sonnet-4-6|claude-opus-4-6",
      "depends_on": ["<other-task-id>"]
    }
  ]
}
```

**Plan ID convention**: `<slug>-YYYYMMDD` (e.g., `cos-cli-build-20260320`)
**Task ID convention**: `<plan-slug>-<step>` (e.g., `cos-cli-build-20260320-design`)

## Task Design Principles

- **One task = one clear deliverable.** A task that "designs and implements" is two tasks.
- **Prefer smaller tasks** — they're easier to retry, and you get faster feedback.
- **Independent tasks run in parallel.** If two tasks don't depend on each other, they run simultaneously. Design for parallelism.
- **Upstream tasks write outputs to `knowledge/plans/<plan-id>/`.**  Downstream tasks read from there. Use this for context passing.
- **Model selection matters:**
  - `claude-opus-4-6` for design, architecture, research
  - `claude-sonnet-4-6` for implementation, coding, analysis
  - `claude-haiku-4-5` for testing, validation, formatting
- **Max 10 subtasks.** The controller enforces this. If you need more, break the plan into phases.

## Dependency Rules

- A task with no `depends_on` starts immediately (runs in parallel with other root tasks)
- A task with `depends_on: [a, b]` only starts after BOTH `a` AND `b` complete
- Don't over-specify dependencies — only add them when the task genuinely needs output from a predecessor

## Context Passing Between Tasks

Write outputs to `knowledge/plans/<plan-id>/<task-id>.md` using this format:

```markdown
# <task-id> — Outputs
*plan_id: <plan-id> | completed: <timestamp>*

## Summary
What was decided/built/found.

## Key Artifacts
- path/to/file.py (what it does)
- key decision made

## Handoff Notes
Specific things downstream tasks should know.

## Full Output
(The detailed work — schemas, code, decisions, etc.)
```

Downstream tasks automatically receive `knowledge/plans/<plan-id>/context.md` as a context ref.

## Example Decomposition

Goal: "Build the cos CLI terminal chatroom for Claude OS"

```
cos-ux-design       [opus/small]    starts immediately
cos-protocol        [sonnet/small]  depends on: cos-ux-design
cos-controller-api  [sonnet/medium] depends on: cos-protocol
cos-cli-binary      [sonnet/medium] depends on: cos-protocol      ← runs parallel with cos-controller-api
cos-integration     [haiku/small]   depends on: cos-controller-api, cos-cli-binary
```

This gives us a 4-level pipeline where levels 2 runs two tasks in parallel.

## After Writing the Plan

Your task is done once:
1. The plan spec JSON is committed to `knowledge/plans/<plan-id>/spec.json`
2. The subtask files are committed to `tasks/pending/`
3. You've reported what the plan contains in your result

You do NOT need to run the subtasks yourself. The controller picks them up from `tasks/pending/`
and handles execution, dependency management, and result collection.
