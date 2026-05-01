#!/usr/bin/env python3
"""
planner.py — Multi-agent plan creator for claude-os

Creates multi-task plans that leverage the dependency graph system built into the
controller (queue.Block/Unblock, ValidateDAG). A plan is a set of related tasks
with explicit dependencies — the controller runs independent tasks in parallel and
unblocks downstream tasks as their dependencies complete.

Usage:
    python3 projects/planner.py --spec plan.json        # create from spec file
    python3 projects/planner.py --spec plan.json --dry-run  # preview without writing
    python3 projects/planner.py --list                  # show active plans
    python3 projects/planner.py --show <plan-id>        # show plan DAG
    python3 projects/planner.py --plain                 # no ANSI colors

Plan spec format (JSON):
{
  "plan_id": "cos-cli-build-20260320",
  "description": "Build the cos CLI terminal chatroom",
  "target_repo": "github.com/dacort/claude-os",
  "tasks": [
    {
      "id": "cos-cli-ux-design",
      "title": "Design cos CLI UX and slash commands",
      "description": "Define the terminal UX, session model, and slash command set.",
      "profile": "small",
      "agent": "claude",
      "model": "claude-opus-4-6",
      "depends_on": []
    },
    {
      "id": "cos-cli-implement",
      "title": "Implement cos CLI Go binary",
      "description": "Build the Go binary using the UX decisions from the design step.",
      "profile": "medium",
      "agent": "claude",
      "model": "claude-sonnet-4-6",
      "depends_on": ["cos-cli-ux-design"]
    }
  ]
}

The plan spec can also be written as inline YAML-ish format.
Plans are validated for DAG integrity before any files are written.

How it fits the controller:
  - Tasks with no depends_on are enqueued immediately (run in parallel)
  - Tasks with depends_on are blocked until their dependencies complete
  - When a dependency completes, the controller unblocks downstream tasks
  - The plan is "done" when all tasks in the plan_id set are completed

See knowledge/orchestration-design.md for the full architecture.
Session 52, 2026-03-20.
"""

import json
import os
import sys
import re
import datetime
from dataclasses import dataclass, field
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# Color helpers
# ──────────────────────────────────────────────────────────────────────────────

PLAIN = "--plain" in sys.argv


def c(code: str, text: str) -> str:
    if PLAIN:
        return text
    return f"\033[{code}m{text}\033[0m"


def cyan(t):    return c("36", t)
def green(t):   return c("32", t)
def yellow(t):  return c("33", t)
def red(t):     return c("31", t)
def dim(t):     return c("2", t)
def bold(t):    return c("1", t)
def magenta(t): return c("35", t)
def blue(t):    return c("34", t)


# ──────────────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PlanTask:
    id: str
    title: str
    description: str
    profile: str = "small"
    agent: str = "claude"
    model: str = "claude-sonnet-4-6"
    depends_on: list = field(default_factory=list)
    context_refs: list = field(default_factory=list)
    priority: str = "normal"
    max_retries: int = 2


@dataclass
class Plan:
    plan_id: str
    description: str
    target_repo: str
    tasks: list  # list[PlanTask]


# ──────────────────────────────────────────────────────────────────────────────
# Parsing
# ──────────────────────────────────────────────────────────────────────────────

def load_spec(path: str) -> Plan:
    """Load a plan spec from a JSON file."""
    with open(path) as f:
        raw = json.load(f)

    tasks = []
    for t in raw.get("tasks", []):
        tasks.append(PlanTask(
            id=t["id"],
            title=t["title"],
            description=t.get("description", ""),
            profile=t.get("profile", "small"),
            agent=t.get("agent", "claude"),
            model=t.get("model", "claude-sonnet-4-6"),
            depends_on=t.get("depends_on", []),
            context_refs=t.get("context_refs", []),
            priority=t.get("priority", "normal"),
            max_retries=t.get("max_retries", 2),
        ))

    return Plan(
        plan_id=raw["plan_id"],
        description=raw.get("description", ""),
        target_repo=raw.get("target_repo", "github.com/dacort/claude-os"),
        tasks=tasks,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────────────

def validate_dag(plan: Plan) -> list:
    """
    Returns a list of error strings. Empty list = valid.

    Checks:
      - All task IDs are unique
      - All depends_on references exist within the plan
      - No cycles (DFS)
      - Max 10 tasks (mirrors controller limit)
    """
    errors = []
    task_ids = {t.id for t in plan.tasks}

    # Unique IDs
    seen = set()
    for t in plan.tasks:
        if t.id in seen:
            errors.append(f"duplicate task id: {t.id!r}")
        seen.add(t.id)

    # Max tasks
    if len(plan.tasks) > 10:
        errors.append(f"plan has {len(plan.tasks)} tasks; maximum is 10")

    # All deps exist
    for t in plan.tasks:
        for dep in t.depends_on:
            if dep not in task_ids:
                errors.append(f"task {t.id!r} depends on unknown task {dep!r}")

    # Cycle detection (DFS coloring: 0=unvisited, 1=visiting, 2=done)
    dep_map = {t.id: t.depends_on for t in plan.tasks}
    color = {tid: 0 for tid in task_ids}

    def dfs(node: str, path: list) -> bool:
        if color[node] == 2:
            return False
        if color[node] == 1:
            cycle = " → ".join(path + [node])
            errors.append(f"cycle detected: {cycle}")
            return True
        color[node] = 1
        for dep in dep_map.get(node, []):
            if dep in color and dfs(dep, path + [node]):
                return True
        color[node] = 2
        return False

    for tid in task_ids:
        if color[tid] == 0:
            dfs(tid, [])

    return errors


# ──────────────────────────────────────────────────────────────────────────────
# Task file generation
# ──────────────────────────────────────────────────────────────────────────────

def render_task_file(plan: Plan, task: PlanTask) -> str:
    """Render a task file as a markdown string."""
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = ["---"]
    lines.append(f"target_repo: {plan.target_repo}")
    lines.append(f"profile: {task.profile}")
    lines.append(f"agent: {task.agent}")
    lines.append(f"model: {task.model}")
    lines.append(f"priority: {task.priority}")
    lines.append(f"status: pending")
    lines.append(f"created: \"{now}\"")
    lines.append(f"plan_id: {plan.plan_id}")
    lines.append(f"task_type: subtask")
    lines.append(f"max_retries: {task.max_retries}")

    if task.depends_on:
        lines.append("depends_on:")
        for dep in task.depends_on:
            lines.append(f"  - {dep}")

    context_refs = list(task.context_refs)
    # Auto-add plan knowledge dir as a context ref for non-root tasks
    if task.depends_on:
        plan_dir = f"knowledge/plans/{plan.plan_id}"
        plan_ref = f"{plan_dir}/context.md"
        if plan_ref not in context_refs:
            context_refs.append(plan_ref)

    if context_refs:
        lines.append("context_refs:")
        for ref in context_refs:
            lines.append(f"  - {ref}")

    lines.append("---")
    lines.append("")
    lines.append(f"# {task.title}")
    lines.append("")
    lines.append("## Description")
    lines.append("")
    lines.append(task.description)
    lines.append("")
    lines.append("## Plan Context")
    lines.append("")
    lines.append(f"- Plan: `{plan.plan_id}`")
    lines.append(f"- Goal: {plan.description}")
    if task.depends_on:
        lines.append(f"- Depends on: {', '.join(f'`{d}`' for d in task.depends_on)}")
    lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# DAG visualization
# ──────────────────────────────────────────────────────────────────────────────

def get_dag_levels(plan: Plan) -> list:
    """
    Returns tasks grouped by execution level (topological sort).
    Level 0 = tasks with no dependencies (run first, in parallel).
    Level 1 = tasks whose deps are all in level 0, etc.
    """
    dep_map = {t.id: set(t.depends_on) for t in plan.tasks}
    task_map = {t.id: t for t in plan.tasks}
    levels = []
    assigned = set()

    while len(assigned) < len(plan.tasks):
        level = []
        for t in plan.tasks:
            if t.id in assigned:
                continue
            if all(dep in assigned for dep in dep_map[t.id]):
                level.append(t)
        if not level:
            break  # cycle guard (shouldn't happen after validation)
        levels.append(level)
        for t in level:
            assigned.add(t.id)

    return levels


def render_dag(plan: Plan) -> list:
    """Render an ASCII DAG. Returns list of lines."""
    levels = get_dag_levels(plan)
    lines = []

    # Build reverse dep map for arrows
    dep_map = {t.id: t.depends_on for t in plan.tasks}

    lines.append(bold(f"  Plan: {plan.plan_id}"))
    lines.append(dim(f"  Goal: {plan.description}"))
    lines.append("")

    for level_idx, level_tasks in enumerate(levels):
        if level_idx == 0:
            phase_label = "starts immediately"
        else:
            phase_label = f"after level {level_idx - 1}"

        lines.append(dim(f"  Level {level_idx}  [{phase_label}]"))

        for t in level_tasks:
            # Format: profile/model/agent summary
            model_short = t.model.replace("claude-", "").replace("-4-6", "").replace("-4-5", "")
            tag = dim(f"[{t.profile}/{model_short}/{t.agent}]")
            dep_str = ""
            if t.depends_on:
                dep_str = dim(f"  ← {', '.join(t.depends_on)}")
            lines.append(f"    {cyan(t.id)}  {tag}{dep_str}")
            if t.title:
                lines.append(dim(f"      {t.title[:60]}"))

        lines.append("")

    # Summary row
    root_count = len(levels[0]) if levels else 0
    lines.append(dim(f"  {len(plan.tasks)} tasks · {root_count} start immediately · {len(levels)} execution levels"))
    return lines


# ──────────────────────────────────────────────────────────────────────────────
# List plans
# ──────────────────────────────────────────────────────────────────────────────

def list_plans(repo_root: str) -> None:
    """Show plans that have task files in tasks/pending/ or tasks/in-progress/."""
    plans = {}

    for status_dir in ("pending", "in-progress", "completed", "failed"):
        dir_path = os.path.join(repo_root, "tasks", status_dir)
        if not os.path.isdir(dir_path):
            continue
        for fname in os.listdir(dir_path):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(dir_path, fname)
            try:
                with open(fpath) as f:
                    content = f.read(1000)
                plan_id = None
                for line in content.split("\n"):
                    if line.startswith("plan_id:"):
                        plan_id = line.split(":", 1)[1].strip()
                        break
                if not plan_id:
                    continue
                if plan_id not in plans:
                    plans[plan_id] = {"pending": 0, "in-progress": 0, "completed": 0, "failed": 0}
                plans[plan_id][status_dir] = plans[plan_id].get(status_dir, 0) + 1
            except Exception:
                continue

    if not plans:
        print(dim("  No plans found."))
        return

    W = 60
    print(f"╭{'─' * W}╮")
    pad = W - len("Active Plans") - 2
    print(f"│  {bold('Active Plans')}{' ' * pad}│")
    print(f"│{' ' * W}│")
    print(f"├{'─' * W}┤")

    for plan_id, counts in sorted(plans.items()):
        total = sum(counts.values())
        done = counts.get("completed", 0)
        running = counts.get("in-progress", 0)
        pending = counts.get("pending", 0)
        failed = counts.get("failed", 0)

        status_str = f"{done}/{total} done"
        if running:
            status_str += f" · {running} running"
        if failed:
            status_str += f" · {red(str(failed) + ' failed')}"

        pad = W - len(plan_id) - len(status_str) - 4
        if pad < 1:
            pad = 1
        print(f"│  {cyan(plan_id)}{' ' * pad}{dim(status_str)}  │")

    print(f"╰{'─' * W}╯")


# ──────────────────────────────────────────────────────────────────────────────
# Show a plan from disk
# ──────────────────────────────────────────────────────────────────────────────

def show_plan(plan_id: str, repo_root: str) -> None:
    """Load a plan's tasks from disk and show the DAG."""
    tasks = []

    for status_dir in ("pending", "in-progress", "completed", "failed"):
        dir_path = os.path.join(repo_root, "tasks", status_dir)
        if not os.path.isdir(dir_path):
            continue
        for fname in os.listdir(dir_path):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(dir_path, fname)
            try:
                with open(fpath) as f:
                    content = f.read(2000)
                # Parse frontmatter
                parts = content.split("---", 2)
                if len(parts) < 3:
                    continue
                fm = parts[1]
                task_plan_id = None
                title = ""
                profile = "small"
                agent = "claude"
                model = "claude-sonnet-4-6"
                depends_on = []
                task_status = status_dir

                for line in fm.split("\n"):
                    line = line.strip()
                    if line.startswith("plan_id:"):
                        task_plan_id = line.split(":", 1)[1].strip()
                    elif line.startswith("profile:"):
                        profile = line.split(":", 1)[1].strip()
                    elif line.startswith("agent:"):
                        agent = line.split(":", 1)[1].strip()
                    elif line.startswith("model:"):
                        model = line.split(":", 1)[1].strip()

                if task_plan_id != plan_id:
                    continue

                # Extract title from body
                body = parts[2]
                for line in body.split("\n"):
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break

                # Parse depends_on (multi-line YAML list)
                in_deps = False
                for line in fm.split("\n"):
                    stripped = line.strip()
                    if stripped.startswith("depends_on:"):
                        in_deps = True
                        continue
                    if in_deps:
                        if stripped.startswith("- "):
                            depends_on.append(stripped[2:].strip())
                        elif stripped and not stripped.startswith("#"):
                            in_deps = False

                task_id = fname[:-3]
                tasks.append(PlanTask(
                    id=task_id,
                    title=title,
                    profile=profile,
                    agent=agent,
                    model=model,
                    depends_on=depends_on,
                    description="",
                ))
            except Exception:
                continue

    if not tasks:
        print(red(f"  No tasks found for plan {plan_id!r}"))
        return

    plan = Plan(plan_id=plan_id, description="", target_repo="", tasks=tasks)
    for line in render_dag(plan):
        print(line)


# ──────────────────────────────────────────────────────────────────────────────
# Write plan files
# ──────────────────────────────────────────────────────────────────────────────

def write_plan(plan: Plan, repo_root: str, dry_run: bool = False) -> None:
    """Write task files for all tasks in the plan."""
    pending_dir = os.path.join(repo_root, "tasks", "pending")
    plan_dir = os.path.join(repo_root, "knowledge", "plans", plan.plan_id)

    W = 64
    print(f"╭{'─' * W}╮")
    pad = W - len(f"Plan: {plan.plan_id}") - 2
    print(f"│  {bold(f'Plan: {plan.plan_id}')}{' ' * pad}│")
    if plan.description:
        desc_short = plan.description[:56]
        pad2 = W - len(desc_short) - 4
        print(f"│  {dim(desc_short)}{' ' * max(1, pad2)}│")
    print(f"│{' ' * W}│")
    print(f"├{'─' * W}┤")

    # DAG preview
    for dag_line in render_dag(plan):
        # Pad to box width (rough)
        visual_len = len(re.sub(r'\033\[[0-9;]*m', '', dag_line))
        pad = W - visual_len
        print(f"│{dag_line}{' ' * max(0, pad)}│")

    print(f"├{'─' * W}┤")

    if dry_run:
        pad = W - len("DRY RUN — no files written") - 2
        print(f"│  {yellow('DRY RUN — no files written')}{' ' * pad}│")
    else:
        pad = W - len("Writing task files...") - 2
        print(f"│  {dim('Writing task files...')}{' ' * pad}│")
    print(f"│{' ' * W}│")

    written = []
    for task in plan.tasks:
        content = render_task_file(plan, task)
        fpath = os.path.join(pending_dir, f"{task.id}.md")

        if dry_run:
            action = yellow("(would write)")
        else:
            try:
                os.makedirs(pending_dir, exist_ok=True)
                with open(fpath, "w") as f:
                    f.write(content)
                written.append(fpath)
                action = green("✓ written")
            except Exception as e:
                action = red(f"✗ {e}")

        deps = ""
        if task.depends_on:
            deps = dim(f"  (waits for: {', '.join(task.depends_on)})")
        label = f"  {task.id}"
        visual_len = len(label) + len(action.replace('\033[32m','').replace('\033[0m','').replace('\033[33m',''))
        pad = W - visual_len - len(deps.replace('\033[2m','').replace('\033[0m','')) - 2
        print(f"│{cyan(label)}{' ' * max(1, pad)}{action}{deps}│")

    print(f"│{' ' * W}│")

    if not dry_run and written:
        # Create plan knowledge directory context file
        os.makedirs(plan_dir, exist_ok=True)
        ctx_path = os.path.join(plan_dir, "context.md")
        if not os.path.exists(ctx_path):
            ctx_content = f"# Plan: {plan.plan_id}\n\n*Goal: {plan.description}*\n\n"
            ctx_content += "## Tasks\n\n"
            for t in plan.tasks:
                ctx_content += f"- **{t.id}**: {t.title}\n"
                if t.depends_on:
                    ctx_content += f"  - depends on: {', '.join(t.depends_on)}\n"
            ctx_content += "\n## Instructions for subtask workers\n\n"
            ctx_content += "When you complete your task, write key outputs to:\n"
            ctx_content += f"`knowledge/plans/{plan.plan_id}/<your-task-id>.md`\n\n"
            ctx_content += "Format:\n```\n## Summary\nWhat you decided/built.\n\n"
            ctx_content += "## Artifacts\n- List of files, decisions, schemas produced.\n\n"
            ctx_content += "## Handoff Notes\nFor downstream tasks.\n```\n"
            with open(ctx_path, "w") as f:
                f.write(ctx_content)

        note = f"  Created {len(written)} task files + knowledge/plans/{plan.plan_id}/context.md"
        pad = W - len(note) - 2 + 2  # rough
        print(f"│  {green(note)}{' ' * max(1, W - len(note) - 2)}│")
        print(f"│{' ' * W}│")
        next_steps = "  Next: git add tasks/pending/ knowledge/plans/ && git commit"
        pad = W - len(next_steps)
        print(f"│{dim(next_steps)}{' ' * max(0, pad)}│")
    elif dry_run:
        note = "  Remove --dry-run to write files"
        pad = W - len(note)
        print(f"│{dim(note)}{' ' * max(0, pad)}│")

    print(f"╰{'─' * W}╯")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def find_repo_root() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(script_dir) == "projects":
        return os.path.dirname(script_dir)
    return script_dir


def usage() -> None:
    print(f"""
{bold("planner.py")} — Multi-agent plan creator for claude-os

{bold("Usage:")}
  python3 projects/planner.py {cyan("--spec")} plan.json       create plan from JSON spec
  python3 projects/planner.py {cyan("--spec")} plan.json {yellow("--dry-run")} preview without writing
  python3 projects/planner.py {cyan("--list")}               show plans with task files
  python3 projects/planner.py {cyan("--show")} <plan-id>     show DAG for an existing plan
  python3 projects/planner.py {cyan("--help")}               this message

{bold("Spec format:")} (JSON)
{{
  "plan_id": "my-plan-20260320",
  "description": "A high-level description",
  "target_repo": "github.com/dacort/claude-os",
  "tasks": [
    {{
      "id": "step-one",
      "title": "First step title",
      "description": "What this task should do.",
      "profile": "small",
      "agent": "claude",
      "model": "claude-sonnet-4-6",
      "depends_on": []
    }},
    {{
      "id": "step-two",
      "title": "Second step (runs after step-one)",
      "description": "What this task should do.",
      "profile": "medium",
      "depends_on": ["step-one"]
    }}
  ]
}}

{bold("Profile choices:")} small, medium, large
{bold("Agent choices:")}   claude, codex
{bold("Model choices:")}   claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-6

{dim("See knowledge/orchestration-design.md for the full architecture.")}
""")


def main() -> None:
    args = sys.argv[1:]

    # Strip --plain (handled globally)
    args = [a for a in args if a != "--plain"]

    if not args or "--help" in args or "-h" in args:
        usage()
        return

    repo_root = find_repo_root()

    if "--list" in args:
        list_plans(repo_root)
        return

    if "--show" in args:
        idx = args.index("--show")
        if idx + 1 >= len(args):
            print(red("  --show requires a plan-id argument"))
            sys.exit(1)
        plan_id = args[idx + 1]
        show_plan(plan_id, repo_root)
        return

    if "--spec" in args:
        idx = args.index("--spec")
        if idx + 1 >= len(args):
            print(red("  --spec requires a file path argument"))
            sys.exit(1)
        spec_path = args[idx + 1]

        if not os.path.exists(spec_path):
            print(red(f"  spec file not found: {spec_path}"))
            sys.exit(1)

        dry_run = "--dry-run" in args

        try:
            plan = load_spec(spec_path)
        except Exception as e:
            print(red(f"  Failed to load spec: {e}"))
            sys.exit(1)

        # Validate
        errors = validate_dag(plan)
        if errors:
            print(red(f"  Plan validation failed:"))
            for err in errors:
                print(red(f"    - {err}"))
            sys.exit(1)

        write_plan(plan, repo_root, dry_run=dry_run)
        return

    print(red(f"  Unknown arguments: {' '.join(args)}"))
    usage()
    sys.exit(1)


if __name__ == "__main__":
    main()
