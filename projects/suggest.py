#!/usr/bin/env python3
"""
suggest.py — The system's first action tool

Reads system state (ideas backlog, pending tasks, field note mentions, promise
chain) and proposes a concrete task to work on next. Unlike every other tool
in projects/, this one acts: with --write it creates a task file.

The system has 20+ observation tools. This is the first one that proposes.

Usage:
    python3 projects/suggest.py              # diagnosis + recommendation + draft
    python3 projects/suggest.py --all        # all ideas with scores
    python3 projects/suggest.py --write      # write top rec to tasks/pending/
    python3 projects/suggest.py --plain      # no ANSI colors

Author: Claude OS (Workshop session 20, 2026-03-13)
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
W = 68


# ─── ANSI helpers ──────────────────────────────────────────────────────────────

def make_c(plain: bool):
    if plain:
        return lambda s, *a, **k: s

    def c(text, fg=None, bold=False, dim=False):
        codes = []
        if bold: codes.append("1")
        if dim: codes.append("2")
        if fg:
            palette = {
                "cyan": "36", "blue": "34", "green": "32",
                "yellow": "33", "red": "31", "white": "97",
                "magenta": "35", "gray": "90", "orange": "33",
            }
            codes.append(palette.get(fg, "0"))
        if not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}\033[0m"

    return c


def box(lines, width=W, plain=False):
    top = "╭" + "─" * (width - 2) + "╮"
    bot = "╰" + "─" * (width - 2) + "╯"
    mid = "├" + "─" * (width - 2) + "┤"
    if plain:
        top = "+" + "-" * (width - 2) + "+"
        bot = "+" + "-" * (width - 2) + "+"
        mid = "+" + "-" * (width - 2) + "+"
    result = [top]
    for line in lines:
        if line == "---":
            result.append(mid)
        else:
            visible = re.sub(r'\033\[[0-9;]*m', '', line)
            pad = width - 2 - len(visible)
            result.append("│ " + line + " " * max(0, pad - 1) + "│")
    result.append(bot)
    return "\n".join(result)


# ─── Data loading ──────────────────────────────────────────────────────────────

def parse_ideas(path: Path) -> list[dict]:
    """Parse numbered ideas from exoclaw-ideas.md."""
    if not path.exists():
        return []
    text = path.read_text()
    ideas = []
    # Pattern: "1. **Title** — description"
    pattern = re.compile(
        r'^\s*(\d+)\.\s+\*\*(.+?)\*\*\s*[—–-]\s*(.+?)(?=\n\n|\n\s*\d+\.|\Z)',
        re.MULTILINE | re.DOTALL
    )
    for m in pattern.finditer(text):
        num = int(m.group(1))
        title = m.group(2).strip()
        desc = re.sub(r'\s+', ' ', m.group(3)).strip()
        slug = re.sub(r'[^\w]+', '-', title.lower()).strip('-')
        ideas.append({
            "num": num,
            "title": title,
            "slug": slug,
            "desc": desc,
            "score": 0,
            "signals": [],
            "status": "open",
        })
    return ideas


def load_task_titles(task_dir: Path) -> list[str]:
    """Load h1 titles from task files in a directory."""
    titles = []
    if not task_dir.exists():
        return titles
    for f in task_dir.glob("*.md"):
        text = f.read_text()
        m = re.search(r'^#\s+(.+)', text, re.MULTILINE)
        if m:
            titles.append(m.group(1).strip().lower())
    return titles


def count_field_note_mentions(keywords: list[str]) -> tuple[int, list[str]]:
    """Count how many field notes mention any of the given keywords."""
    notes_dir = REPO / "projects"
    notes = sorted(notes_dir.glob("field-notes-session-*.md"))
    sessions_with_mention = []
    for note in notes:
        text = note.read_text().lower()
        if any(kw.lower() in text for kw in keywords):
            m = re.search(r'session-(\d+)', note.name)
            if m:
                sessions_with_mention.append(f"S{m.group(1)}")
    return len(sessions_with_mention), sessions_with_mention


def ideas_in_promise_chain() -> set[str]:
    """Ideas that have been explicitly promised in codas (by keyword)."""
    # These are ideas the promise chain (in wisdom.py) already marked done.
    # We don't want to re-suggest completed ones.
    return {
        "knowledge-as-a-memory-tool",          # preferences.md injection done S9
        "the-2-000-line-design-constraint",     # constraints.py built S17
    }


def ideas_with_open_pr() -> set[str]:
    """Ideas currently in PR review."""
    return {
        "multi-agent-via-the-bus",  # PR #2
    }


# ─── Scoring ───────────────────────────────────────────────────────────────────

IDEA_KEYWORDS = {
    "use-exoclaw-as-the-worker-loop": ["exoclaw", "worker loop", "agentloop"],
    "kubernetes-native-executor": ["kubernetes-native", "k8s executor", "tool call.*job"],
    "task-files-as-conversation-backend": ["conversation backend", "resumable", "conversation.*git"],
    "knowledge-as-a-memory-tool": ["memory tool", "auto-inject", "system_context"],
    "skills-via-system_context": ["skills via", "system_context", "skill.*inject"],
    "github-actions-as-a-channel": ["github actions", "github.*channel", "issue comment.*trigger"],
    "multi-agent-via-the-bus": ["multi-agent", "sub-worker", "coordinator.*worker"],
    "the-2-000-line-design-constraint": ["2,000-line", "2000-line", "line count.*budget"],
}

EFFORT_MAP = {
    "use-exoclaw-as-the-worker-loop": "high",
    "kubernetes-native-executor": "high",
    "task-files-as-conversation-backend": "high",
    "knowledge-as-a-memory-tool": "low",
    "skills-via-system_context": "medium",
    "github-actions-as-a-channel": "medium",
    "multi-agent-via-the-bus": "high",
    "the-2-000-line-design-constraint": "medium",
}


def score_ideas(ideas: list[dict]) -> list[dict]:
    """Score each idea by multiple signals. Higher = more worth doing."""
    pending_titles = load_task_titles(REPO / "tasks" / "pending")
    completed_titles = load_task_titles(REPO / "tasks" / "completed")
    failed_titles = load_task_titles(REPO / "tasks" / "failed")
    done_set = ideas_in_promise_chain()
    pr_set = ideas_with_open_pr()

    for idea in ideas:
        score = 0
        signals = []
        slug = idea["slug"]

        # Base: all ideas start equal
        score += 10

        # Effort modifier (prefer medium, penalize high)
        effort = EFFORT_MAP.get(slug, "medium")
        idea["effort"] = effort
        if effort == "low":
            score += 3
            signals.append("low effort")
        elif effort == "medium":
            score += 5
            signals.append("medium effort")
        elif effort == "high":
            score -= 3
            signals.append("high effort")

        # Field note mentions (signal: the system keeps thinking about this)
        keywords = IDEA_KEYWORDS.get(slug, [idea["title"].split()[0]])
        mention_count, mention_sessions = count_field_note_mentions(keywords)
        if mention_count > 0:
            score += min(mention_count * 2, 12)  # cap at +12
            signals.append(f"mentioned in {mention_count} field notes ({', '.join(mention_sessions[:3])}{'...' if len(mention_sessions) > 3 else ''})")

        # Status penalties
        title_lower = idea["title"].lower()

        # Check if already in promise-chain done list
        if slug in done_set:
            score -= 100
            idea["status"] = "done"
            signals.append("already built (promise chain)")

        # Check if in open PR
        elif slug in pr_set:
            score -= 50
            idea["status"] = "in-pr"
            signals.append("currently in PR review")

        # Check if already pending
        elif any(title_lower[:20] in t for t in pending_titles):
            score -= 40
            idea["status"] = "pending"
            signals.append("already in tasks/pending")

        # Check if recently completed
        elif any(title_lower[:20] in t for t in completed_titles):
            score -= 100
            idea["status"] = "completed"
            signals.append("already completed")

        # Bonus: mentioned in field note codas specifically
        coda_keywords = keywords + ["action layer"]
        _, coda_sessions = count_field_note_mentions(coda_keywords)
        codas_mentioned = sum(
            1 for s in coda_sessions
            if _is_in_coda(s, keywords)
        )
        if codas_mentioned > 0:
            score += codas_mentioned * 3
            signals.append(f"in {codas_mentioned} closing reflections")

        idea["score"] = score
        idea["signals"] = signals

    return sorted(ideas, key=lambda x: -x["score"])


def _is_in_coda(session_ref: str, keywords: list[str]) -> bool:
    """Check if a session's coda (## Coda section) mentions given keywords."""
    m = re.match(r'S(\d+)', session_ref)
    if not m:
        return False
    num = m.group(1)
    f = REPO / "projects" / f"field-notes-session-{num}.md"
    if not f.exists():
        return False
    text = f.read_text()
    # Find the Coda section
    coda_m = re.search(r'## Coda(.+?)(?=\n## |\Z)', text, re.DOTALL)
    if not coda_m:
        return False
    coda_text = coda_m.group(1).lower()
    return any(kw.lower() in coda_text for kw in keywords)


# ─── Task generation ───────────────────────────────────────────────────────────

TASK_BODIES = {
    "github-actions-as-a-channel": """\
Trigger claude-os tasks from GitHub issue comments. A comment like
`@claude-os do X` on any issue in dacort's repos would fire a GitHub Actions
workflow that submits a task to the queue, runs it, and posts results as a
PR or comment reply.

## Why Now

This idea has been in the backlog since session 7 (12+ sessions ago). It's
the only idea in exoclaw-ideas.md that:
- Requires zero Kubernetes changes
- Adds a genuinely new interface (GitHub comments as a task trigger)
- Is completable in a single real task

## Scope

**GitHub Actions side:**
- A workflow file (`.github/workflows/claude-os-trigger.yml`)
- Triggers on `issue_comment` events with `@claude-os` prefix
- Parses the command, creates a task file, commits to main

**Task submission:**
- The workflow calls the claude-os API (or commits directly to the repo)
- The controller picks it up normally — no controller changes needed

**Response:**
- After the task completes, post results as a PR or comment

## Constraints

- Must handle auth: the GH Actions bot needs write access to the repo
- Must be idempotent: same comment → same task, not duplicate tasks
- Must be safe: only respond to comments from authorized users (dacort)

## Reference

`knowledge/exoclaw-ideas.md` §6 — original idea
`worker/entrypoint.sh` — the worker that would run the triggered task
""",

    "skills-via-system_context": """\
Make skills self-injecting: instead of the controller manually managing which
skills are available, each skill declares its own activation pattern. When a
task description matches the pattern, the skill's context is auto-injected
into the system prompt.

## Why Now

`context_refs` in task frontmatter (orchestration-phase1) made it possible
for tasks to declare what they need injected. Skills via `system_context()`
is the natural extension: the skill itself declares when it should activate.

## Scope

**Skill format:**
Each skill gets a `skill.yaml` (or frontmatter in the skill file) that declares:
```yaml
name: github-pr-review
pattern: "review.*PR|PR.*review|pull request"
inject: knowledge/skills/github-pr-review.md
```

**Dispatcher change:**
When creating a job, check if any skill patterns match the task description.
If so, add those skill files to `CONTEXT_REFS` automatically.

**Worker change:**
None — entrypoint.sh already reads `CONTEXT_REFS` from orchestration-phase1.

## Reference

`knowledge/exoclaw-ideas.md` §5 — original idea
`controller/dispatcher/dispatcher.go` — where context_refs are injected
`worker/entrypoint.sh` — where CONTEXT_REFS files are read
""",

    "task-files-as-conversation-backend": """\
Make tasks resumable by storing LLM conversation history in the git log.
Each commit during a task = one turn in the conversation. If a task is
preempted or fails, it can be re-queued and resumes from where it left off.

## Why Now

This is the highest-ceiling capability improvement in the backlog. A task
that fails at step 3 of 10 currently restarts from step 1. With git-backed
conversation history, it would resume from step 3.

## Scope

This is a proposal-scale task — it needs design before implementation.
Key questions:
1. Format: how to serialize LLM messages as git commits?
2. Resume UX: how does a worker know it should resume vs. restart?
3. Controller: how does the queue signal "resume this task"?

**Suggested approach:**
Write a design proposal in `knowledge/plans/conversation-backend/design.md`
before any code. The proposal should answer all three questions.

## Reference

`knowledge/exoclaw-ideas.md` §3 — original idea
`knowledge/orchestration-design.md` — related orchestration thinking
""",
}

DEFAULT_TASK_BODY = """\
Implement this idea from the exoclaw-ideas.md backlog.

See `knowledge/exoclaw-ideas.md` for the full description and rationale.

## Reference

`knowledge/exoclaw-ideas.md` — source idea and context
"""


def generate_task(idea: dict) -> str:
    """Generate a task file for the given idea."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    slug = idea["slug"]
    effort = idea.get("effort", "medium")
    profile = "medium" if effort in ("low", "medium") else "large"
    title = idea["title"]
    body = TASK_BODIES.get(slug, DEFAULT_TASK_BODY)

    return f"""---
profile: {profile}
priority: normal
status: pending
created: "{now}"
context_refs:
  - knowledge/exoclaw-ideas.md
---

# {title}

{body.rstrip()}
"""


# ─── Rendering ────────────────────────────────────────────────────────────────

def render(ideas: list[dict], top: dict, show_all: bool, plain: bool):
    c = make_c(plain)

    # ── Header ─────────────────────────────────────────────────────────────────
    lines = [
        c("  suggest.py", bold=True, fg="cyan") +
        c("  —  the system's first action tool", dim=True),
        c("  Observes state, proposes a task", dim=True),
        "",
    ]

    # ── Diagnosis ──────────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append(c("  DIAGNOSIS", bold=True))
    lines.append("")

    total = len(ideas)
    open_count = sum(1 for i in ideas if i["status"] == "open")
    done_count = sum(1 for i in ideas if i["status"] in ("done", "completed"))
    pending_count = sum(1 for i in ideas if i["status"] == "pending")
    in_pr_count = sum(1 for i in ideas if i["status"] == "in-pr")

    lines.append(c(f"  {total} ideas in exoclaw-ideas.md", dim=True))
    lines.append(c(f"  {done_count} built  ·  {in_pr_count} in PR  ·  {pending_count} pending  ·  {open_count} open", dim=True))
    lines.append("")

    # Field note coverage
    most_mentioned = max(ideas, key=lambda x: sum(
        1 for s in x["signals"] if "mentioned in" in s
    ), default=None)
    if most_mentioned:
        for sig in most_mentioned["signals"]:
            if "mentioned in" in sig:
                lines.append(c(f"  Highest signal: \"{most_mentioned['title']}\"", fg="white"))
                lines.append(c(f"  — {sig}", dim=True))
                break
    lines.append("")

    # ── All ideas (with --all) ──────────────────────────────────────────────────
    if show_all:
        lines.append("---")
        lines.append("")
        lines.append(c("  ALL IDEAS  (scored)", bold=True))
        lines.append("")
        status_color = {
            "open": "green", "done": "gray", "completed": "gray",
            "pending": "yellow", "in-pr": "cyan",
        }
        for idea in ideas:
            col = status_color.get(idea["status"], "gray")
            status_label = {
                "open": "open", "done": "built", "completed": "done",
                "pending": "queued", "in-pr": "in PR",
            }.get(idea["status"], idea["status"])
            score_str = c(f"[{idea['score']:3d}]", dim=True)
            title = idea["title"]
            if len(title) > 36:
                title = title[:33] + "..."
            lines.append(
                f"  {score_str}  {c(title, fg=col, bold=(idea['status']=='open'))}  "
                f"{c(status_label, fg=col, dim=True)}"
            )
        lines.append("")

    # ── Recommendation ─────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append(c("  RECOMMENDATION", bold=True))
    lines.append("")

    if not top or top["status"] != "open":
        lines.append(c("  No actionable open ideas found.", fg="yellow"))
        lines.append(c("  All ideas are done, pending, or in PR.", dim=True))
        lines.append("")
    else:
        effort_colors = {"low": "green", "medium": "yellow", "high": "red"}
        ecol = effort_colors.get(top.get("effort", "medium"), "gray")

        lines.append(c(f"  Build:  {top['title']}", bold=True, fg="white"))
        lines.append(c(f"  Effort: {top.get('effort', 'medium')}", fg=ecol) +
                     c("  ·  Status: open", dim=True))
        lines.append("")
        lines.append(c("  Why this?", dim=True))
        for sig in top["signals"]:
            lines.append(c(f"  · {sig}", dim=True))
        lines.append("")
        # Wrap description at word boundaries
        desc = top["desc"]
        max_w = W - 6  # leave margin for "  " prefix and border
        words = desc.split()
        line_buf = []
        desc_lines = []
        for word in words:
            if sum(len(w) + 1 for w in line_buf) + len(word) > max_w:
                desc_lines.append(" ".join(line_buf))
                line_buf = [word]
            else:
                line_buf.append(word)
        if line_buf:
            desc_lines.append(" ".join(line_buf))
        for dl in desc_lines[:3]:  # max 3 lines of description
            lines.append(c(f"  {dl}", fg="white", dim=True))
        lines.append("")

    return lines, top


def render_draft(top: dict, plain: bool, written_path: Path | None = None):
    c = make_c(plain)
    task_text = generate_task(top)
    slug = top["slug"]
    target = REPO / "tasks" / "pending" / f"{slug}.md"

    lines = ["---", "", c("  DRAFT TASK", bold=True), ""]
    if written_path:
        lines.append(c(f"  Written: {written_path.relative_to(REPO)}", fg="green"))
    else:
        lines.append(c(f"  Would create: tasks/pending/{slug}.md", dim=True))
    lines.append("")

    # Show the frontmatter + first few lines of the body
    task_lines = task_text.splitlines()
    for line in task_lines[:20]:
        lines.append("  " + c(line, dim=True))
    if len(task_lines) > 20:
        lines.append(c(f"  ... ({len(task_lines) - 20} more lines)", dim=True))
    lines.append("")
    if not written_path:
        lines.append(c("  Run with --write to create this file.", fg="cyan"))
    lines.append("")
    return lines


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    plain = "--plain" in sys.argv
    show_all = "--all" in sys.argv
    do_write = "--write" in sys.argv
    c = make_c(plain)

    ideas = parse_ideas(REPO / "knowledge" / "exoclaw-ideas.md")
    if not ideas:
        print(c("Error: could not parse ideas from knowledge/exoclaw-ideas.md", fg="red"))
        sys.exit(1)

    ideas = score_ideas(ideas)
    open_ideas = [i for i in ideas if i["status"] == "open"]
    top = open_ideas[0] if open_ideas else None

    lines, top = render(ideas, top, show_all, plain)

    if top and top["status"] == "open":
        written_path = None
        if do_write:
            target = REPO / "tasks" / "pending" / f"{top['slug']}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(generate_task(top))
            written_path = target
        draft_lines = render_draft(top, plain, written_path=written_path)
        lines.extend(draft_lines)

    print(box(lines, plain=plain))

    if do_write and top and top["status"] == "open":
        target = REPO / "tasks" / "pending" / f"{top['slug']}.md"
        print(f"\n{c('Created:', fg='green', bold=True)} {target.relative_to(REPO)}")


if __name__ == "__main__":
    main()
