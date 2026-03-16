#!/usr/bin/env python3
"""
trace.py — Trace the evolution of an idea across sessions.

Where search.py finds where something appears, trace.py shows HOW
an idea developed over time — first mention, refinement, implementation,
resolution or abandonment.

The output is a chronological timeline: each session where the concept
appeared, what was said, and what the current status is.

Usage:
    python3 projects/trace.py "multi-agent"
    python3 projects/trace.py "search" --plain
    python3 projects/trace.py "GitHub Actions"
    python3 projects/trace.py --help
"""

import re
import sys
import os
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).parent.parent
W = 66

# ─── ANSI helpers ───────────────────────────────────────────────────────────

PLAIN = "--plain" in sys.argv

def c(code, text):
    return text if PLAIN else f"\033[{code}m{text}\033[0m"

def bold(t):    return c("1", t)
def dim(t):     return c("2", t)
def green(t):   return c("32", t)
def yellow(t):  return c("33", t)
def cyan(t):    return c("36", t)
def red(t):     return c("31", t)
def magenta(t): return c("35", t)
def white(t):   return c("1;97", t)
def gray(t):    return c("90", t)
def italic(t):  return c("3", t)

def strip_ansi(s):
    return re.sub(r"\033\[[^m]+m", "", s)

def box_top(title="", width=W):
    if title:
        inner = f"  {title}  "
        pad = width - len(strip_ansi(inner)) - 2
        return "╭" + inner + "─" * max(0, pad) + "╮"
    return "╭" + "─" * (width - 2) + "╮"

def box_bot(width=W):
    return "╰" + "─" * (width - 2) + "╯"

def box_div(width=W):
    return "├" + "─" * (width - 2) + "┤"

def box_row(text="", width=W):
    plain = strip_ansi(text)
    pad = width - 2 - len(plain) - 2
    return "│  " + text + " " * max(0, pad) + "│"

def truncate(s, n):
    plain = strip_ansi(s)
    if len(plain) > n:
        # Trim the raw string approximately
        return s[:n - 1] + "…"
    return s


# ─── File classification ────────────────────────────────────────────────────

def classify_file(path):
    """
    Return (sort_key, category, label) for a file.
    sort_key is a tuple for stable chronological sort.
    """
    rel = path.relative_to(REPO)
    name = path.stem

    # Field notes: primary timeline source
    if rel.parts[0] == "projects" and name.startswith("field-notes-"):
        if name == "field-notes-from-free-time":
            return (0, 0), "note", "free-time"
        m = re.search(r"session-(\d+)", name)
        if m:
            n = int(m.group(1))
            return (1, n), "note", f"S{n:02d}"

    # Knowledge docs
    if rel.parts[0] == "knowledge" and path.suffix == ".md":
        mtime = path.stat().st_mtime
        return (3, int(mtime)), "knowledge", "knowledge"

    # Tasks
    if rel.parts[0] == "tasks":
        subdir = rel.parts[1] if len(rel.parts) > 1 else "unknown"
        mtime = path.stat().st_mtime
        status_order = {
            "completed": 2, "failed": 2, "in-progress": 1,
            "pending": 0, "unknown": 0
        }
        return (2, status_order.get(subdir, 0), int(mtime)), f"task/{subdir}", f"task"

    # Project files (tools)
    if rel.parts[0] == "projects" and path.suffix == ".py":
        mtime = path.stat().st_mtime
        return (4, int(mtime)), "project", "tool"

    # GitHub workflows
    if ".github" in rel.parts:
        mtime = path.stat().st_mtime
        return (4, int(mtime)), "workflow", "workflow"

    mtime = path.stat().st_mtime
    return (5, int(mtime)), "other", "other"


def discover_all():
    """Return list of all searchable files."""
    files = []

    for p in REPO.glob("projects/field-notes-*.md"):
        files.append(p)
    for p in REPO.glob("knowledge/*.md"):
        files.append(p)
    for subdir in ["completed", "failed", "pending", "in-progress"]:
        task_dir = REPO / "tasks" / subdir
        if task_dir.exists():
            for p in task_dir.glob("*.md"):
                files.append(p)
    for p in REPO.glob("projects/*.py"):
        if p.name != "trace.py":
            files.append(p)
    for p in REPO.glob(".github/**/*.yml"):
        files.append(p)
    for p in REPO.glob(".github/**/*.yaml"):
        files.append(p)

    return files


# ─── Excerpt extraction ─────────────────────────────────────────────────────

def best_excerpt(text, terms, max_lines=2):
    """
    Find the most 'meaningful' excerpt containing any term.
    Prefer lines near headings that suggest reflection (Coda, What I,
    Noticed, etc.). Fall back to the first matching line.
    """
    lines = text.split("\n")
    reflective_headings = {
        "coda", "what i noticed", "what i was", "reflection",
        "what this", "why this", "lesson", "insight", "thinking",
        "built", "idea", "toward", "unlocks"
    }

    matches = []  # (quality, line_idx)
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if not any(t.lower() in line_lower for t in terms):
            continue
        if not line.strip() or line.strip().startswith("---"):
            continue

        # Check nearby headings for reflective quality
        quality = 0
        for j in range(max(0, i - 10), i):
            h = lines[j].lower().strip().lstrip("#").strip()
            if any(keyword in h for keyword in reflective_headings):
                quality = 2
                break
        # Bold/quote lines get a bump
        stripped = line.strip()
        if stripped.startswith(">") or stripped.startswith("**"):
            quality = max(quality, 1)

        matches.append((quality, i))

    if not matches:
        return []

    # Sort by quality desc, then line order
    matches.sort(key=lambda x: (-x[0], x[1]))

    # Take the best match, show it plus the next line if it continues the thought
    best_idx = matches[0][1]
    result = []
    for i in range(best_idx, min(len(lines), best_idx + max_lines)):
        raw = lines[i].strip()
        if not raw or raw.startswith("---"):
            break
        # Clean markdown: strip bold markers, quote markers
        clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", raw)
        clean = re.sub(r"^>\s*", "", clean)
        clean = re.sub(r"`([^`]+)`", r"\1", clean)
        # Highlight terms
        if not PLAIN:
            for term in sorted(terms, key=len, reverse=True):
                clean = re.compile(re.escape(term), re.IGNORECASE).sub(
                    lambda m: c("1;33", m.group(0)), clean
                )
        result.append(truncate(clean, W - 8))
        if i < len(lines) - 1 and not lines[i + 1].strip():
            break  # stop at paragraph boundary

    return result


def search_file(path, terms):
    """
    Return (hit_count, excerpts) for the file.
    Requires ALL terms to appear somewhere in the file.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0, []

    text_lower = text.lower()
    for term in terms:
        if term.lower() not in text_lower:
            return 0, []

    # Count hits
    hit_count = sum(
        len(re.findall(re.escape(t), text, re.IGNORECASE))
        for t in terms
    )

    excerpts = best_excerpt(text, terms)
    return hit_count, excerpts


# ─── Status inference ───────────────────────────────────────────────────────

def stem_matches(path, terms):
    """True if any query term appears in the file's stem name."""
    stem = path.stem.lower().replace("-", " ").replace("_", " ")
    return any(t.lower() in stem for t in terms)


def infer_status(results, terms):
    """
    Infer the current status of an idea from its matches.
    Returns (status_label, status_color_fn, detail).

    Uses name-matching to distinguish "implements this" from "mentions this."
    """
    all_tools     = [r for r in results if r[1] == "project"]
    workflows     = [r for r in results if r[1] == "workflow"]
    completed     = [r for r in results if r[1] == "task/completed"]
    inprogress    = [r for r in results if r[1] == "task/in-progress"]
    pending       = [r for r in results if r[1] == "task/pending"]
    notes         = [r for r in results if r[1] == "note"]
    has_knowledge = any(r[1] == "knowledge" for r in results)
    note_count    = len(notes)

    # A tool that is NAMED after the concept → implemented
    named_tools = [r for r in all_tools if stem_matches(r[3], terms)]
    if named_tools:
        names = [r[3].stem for r in named_tools]
        return "implemented", green, f"tool built: {', '.join(names)}"

    # A workflow that is specifically about this (not just the build workflow)
    concept_workflows = [r for r in workflows if stem_matches(r[3], terms)
                         or "trigger" in r[3].name.lower()]
    if concept_workflows:
        return "shipped", green, "workflow exists for this"

    # A completed task NAMED after the concept (not just a workshop session)
    named_completed = [r for r in completed
                       if stem_matches(r[3], terms)
                       and not r[3].stem.startswith("workshop-")]
    if named_completed:
        names = [r[3].stem for r in named_completed]
        return "researched", cyan, f"research task done: {', '.join(names)}"

    # In-progress task?
    if inprogress:
        return "in-progress", yellow, "task is running now"

    # Pending task?
    if pending:
        return "pending", yellow, "task queued"

    # Idea is in knowledge docs + recurring in field notes → well-documented
    if has_knowledge and note_count >= 5:
        return "long-running idea", magenta, f"documented · {note_count} sessions · not yet built"
    if has_knowledge and note_count >= 2:
        return "documented", yellow, f"in knowledge base · {note_count} field note sessions"
    if has_knowledge:
        return "documented", yellow, "captured in knowledge base · not yet in field notes"

    # Only in field notes
    if note_count == 1:
        return "single mention", dim, "appeared once, not revisited"
    if note_count >= 5:
        return "recurring", magenta, f"keeps coming up · {note_count} sessions · not yet built"
    if note_count >= 2:
        return "theoretical", dim, f"idea only · {note_count} sessions"
    return "mentioned", dim, "found in sources but not in field notes"


# ─── Category labels ────────────────────────────────────────────────────────

CAT_COLOR = {
    "note":              cyan,
    "knowledge":         magenta,
    "project":           green,
    "workflow":          green,
    "task/completed":    green,
    "task/failed":       red,
    "task/pending":      yellow,
    "task/in-progress":  yellow,
}

def cat_display(category, label):
    color = CAT_COLOR.get(category, dim)
    return color(f"[{label}]")


# ─── Main trace ─────────────────────────────────────────────────────────────

BRIEF = "--brief" in sys.argv


def cmd_trace(query):
    terms = [t for t in query.split() if t]
    if not terms:
        print("Usage: python3 projects/trace.py <concept>")
        sys.exit(1)

    all_files = discover_all()
    results = []

    for path in all_files:
        sort_key, category, label = classify_file(path)
        hit_count, excerpts = search_file(path, terms)
        if hit_count > 0:
            results.append((sort_key, category, label, path, hit_count, excerpts))

    # Sort chronologically
    results.sort(key=lambda r: r[0])

    title = f"{bold('trace')}  {dim(repr(query))}"
    print(box_top(title, width=W))
    print(box_row("", width=W))

    if not results:
        print(box_row(dim("  nothing found"), width=W))
        print(box_row("", width=W))
        print(box_row(dim("  Try a different term or check search.py."), width=W))
        print(box_row("", width=W))
        print(box_bot(width=W))
        return

    # Partition by category group
    notes     = [r for r in results if r[1] == "note"]
    tasks     = [r for r in results if r[1].startswith("task/")]
    knowledge = [r for r in results if r[1] == "knowledge"]
    tools     = [r for r in results if r[1] == "project"]
    workflows = [r for r in results if r[1] == "workflow"]

    total_sessions = len(notes)
    note_hits = sum(r[4] for r in notes)

    # — Timeline header —
    if notes:
        first_label = notes[0][2]
        last_label  = notes[-1][2]
        span = f"{first_label} → {last_label}" if first_label != last_label else first_label
        s_plural = "s" if total_sessions != 1 else ""
        print(box_row(
            f"  {cyan(span)}  {dim(f'· {total_sessions} session{s_plural} · {note_hits} hits in field notes')}",
            width=W
        ))
        print(box_row("", width=W))
    elif not BRIEF:
        print(box_row(dim("  no field note mentions — idea may be documented but not discussed"), width=W))
        print(box_row("", width=W))

    # — Field note timeline (always shown) —
    is_first = True
    for i, (sort_key, category, label, path, hits, excerpts) in enumerate(notes):
        tag = cat_display(category, label)
        if is_first:
            role = bold("first mention") if len(notes) > 1 else bold("only mention")
            is_first = False
        elif i == len(notes) - 1:
            role = dim("latest")
        else:
            role = dim("·")

        header = f"  {tag}  {dim(path.stem)}  {role}"
        print(box_row(header, width=W))

        if not BRIEF:
            for exc in excerpts[:2]:
                print(box_row(f"    {italic(exc)}", width=W))

        print(box_row("", width=W))

    # — Knowledge docs —
    if knowledge and not BRIEF:
        for sort_key, category, label, path, hits, excerpts in knowledge:
            tag = cat_display(category, label)
            rel = str(path.relative_to(REPO))
            print(box_row(f"  {tag}  {dim(path.name)}", width=W))
            for exc in excerpts[:1]:
                print(box_row(f"    {italic(exc)}", width=W))
            print(box_row("", width=W))

    # — Tools / workflows (show if implemented) —
    impl = tools + workflows
    if impl and not BRIEF:
        for sort_key, category, label, path, hits, excerpts in impl:
            # Only show if the match is conceptually relevant (in docstring/name)
            # Skip pure code function name matches like re.search(
            relevant_excerpts = [
                e for e in excerpts
                if not re.search(r're\.\w+\(|import |def |class ', strip_ansi(e))
            ]
            if not relevant_excerpts and excerpts:
                # Still show but dimmer
                relevant_excerpts = excerpts[:1]
            if not relevant_excerpts:
                continue
            tag = cat_display(category, label)
            print(box_row(f"  {tag}  {dim(path.name)}", width=W))
            for exc in relevant_excerpts[:1]:
                print(box_row(f"    {italic(exc)}", width=W))
            print(box_row("", width=W))

    # — Task summary (collapsed) —
    if tasks and not BRIEF:
        task_counts = {}
        for _, category, _, _, hits, _ in tasks:
            task_counts[category] = task_counts.get(category, 0) + 1

        parts = []
        for subcat in ["task/completed", "task/in-progress", "task/pending", "task/failed"]:
            n = task_counts.get(subcat, 0)
            if n:
                short = subcat.replace("task/", "")
                col = CAT_COLOR.get(subcat, dim)
                parts.append(col(f"{n} {short}"))

        if parts:
            task_summary = "  " + dim("tasks: ") + "  ".join(parts)
            print(box_row(task_summary, width=W))
            # Show one excerpt from the most-hit task
            best_task = max(tasks, key=lambda r: r[4])
            if best_task[5]:
                print(box_row(f"    {italic(best_task[5][0])}", width=W))
            print(box_row("", width=W))

    # — Status —
    print(box_div(width=W))
    print(box_row("", width=W))

    status_label, status_color, detail = infer_status(results, terms)
    status_display = status_color(status_label)
    print(box_row(f"  {bold('STATUS')}  {status_display}  {dim('—')}  {dim(detail)}", width=W))
    print(box_row("", width=W))

    # Gap analysis (sessions where this idea was silent)
    if notes and not BRIEF:
        all_session_nums = set()
        for r in notes:
            m = re.search(r"session-(\d+)", r[3].stem)
            if m:
                all_session_nums.add(int(m.group(1)))

        if all_session_nums:
            low = min(all_session_nums)
            high = max(all_session_nums)
            full_range = set(range(low, high + 1))
            gaps = sorted(full_range - all_session_nums)
            if gaps and len(gaps) <= 10:
                gap_str = ", ".join(f"S{n:02d}" for n in gaps)
                print(box_row(dim(f"  silent: {gap_str}"), width=W))
                print(box_row("", width=W))

    # Footer
    total_matched = len(results)
    print(box_row(
        dim(f"  trace · {len(terms)} term(s) · {total_matched} source(s) · --brief for summary"),
        width=W
    ))
    print(box_bot(width=W))


# ─── Entry point ────────────────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if "--help" in flags or not args:
        print(__doc__)
        sys.exit(0)

    query = " ".join(args)
    cmd_trace(query)


if __name__ == "__main__":
    main()
