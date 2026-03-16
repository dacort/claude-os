#!/usr/bin/env python3
"""
search.py — Search the claude-os knowledge base.

Searches across field notes, knowledge docs, task files, and project
docstrings for any query. Turns the growing repo into a queryable memory
so future instances don't have to grep manually.

Four source categories:
  note      — projects/field-notes-*.md  (session writing)
  knowledge — knowledge/*.md             (accumulated wisdom)
  task      — tasks/**/*.md              (completed / failed / pending)
  project   — projects/*.py              (tool docstrings + comments)

Usage:
    python3 projects/search.py <query>
    python3 projects/search.py "multi-agent"
    python3 projects/search.py --plain "token optimization"
    python3 projects/search.py --json "scheduling"
    python3 projects/search.py --list      # list all indexed sources
    python3 projects/search.py --context 5 "exoclaw"   # more excerpt lines
"""

import re
import sys
import json
import os
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).parent.parent
W = 64

# ─── ANSI helpers ──────────────────────────────────────────────────────────────

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

def box_top(title="", width=W):
    if title:
        inner = f"  {title}  "
        pad = width - len(inner) - 2
        return "╭" + inner + "─" * max(0, pad) + "╮"
    return "╭" + "─" * (width - 2) + "╮"

def box_bot(width=W):
    return "╰" + "─" * (width - 2) + "╯"

def box_div(width=W):
    return "├" + "─" * (width - 2) + "┤"

def box_row(text="", width=W):
    # Strip ANSI for length calculation
    plain_text = re.sub(r"\033\[[^m]+m", "", text)
    pad = width - 2 - len(plain_text) - 2
    return "│  " + text + " " * max(0, pad) + "│"

def truncate(s, n):
    return s[:n - 1] + "…" if len(s) > n else s


# ─── Source discovery ───────────────────────────────────────────────────────────

def discover_sources():
    """Return list of (path, category) tuples for all indexed files."""
    sources = []

    # Field notes
    for p in sorted(REPO.glob("projects/field-notes-*.md")):
        sources.append((p, "note"))

    # Knowledge docs
    for p in sorted(REPO.glob("knowledge/*.md")):
        sources.append((p, "knowledge"))

    # Task files (all subdirs)
    for subdir in ["completed", "failed", "pending", "in-progress"]:
        task_dir = REPO / "tasks" / subdir
        if task_dir.exists():
            for p in sorted(task_dir.glob("*.md")):
                sources.append((p, f"task/{subdir}"))

    # Python projects (docstrings + comments, not just code)
    for p in sorted(REPO.glob("projects/*.py")):
        # Skip this file itself
        if p.name == "search.py":
            continue
        sources.append((p, "project"))

    return sources


# ─── Session recency ────────────────────────────────────────────────────────────

def session_number(path):
    """Extract ordering key for recency scoring."""
    name = path.stem
    if name == "field-notes-from-free-time":
        return 1
    m = re.search(r"session-(\d+)", name)
    if m:
        return int(m.group(1))
    # For non-field-note files, try to infer from mtime
    return 0


def recency_weight(path, category):
    """Score 0.0–1.0 based on how recent the file is."""
    if category == "note":
        n = session_number(path)
        # Normalize: session 21+ is max, session 1 is min
        return min(1.0, n / 22.0)
    # For other files, use mtime
    try:
        mtime = path.stat().st_mtime
        # Rough normalization: anything in last 3 days = 1.0
        import time
        age_days = (time.time() - mtime) / 86400
        return max(0.0, 1.0 - age_days / 30.0)
    except Exception:
        return 0.5


# ─── Search ────────────────────────────────────────────────────────────────────

def highlight(line, terms):
    """Add ANSI highlighting around matched terms in a line."""
    if PLAIN:
        return line
    result = line
    for term in sorted(terms, key=len, reverse=True):
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        result = pattern.sub(lambda m: c("1;33", m.group(0)), result)
    return result


def search_file(path, terms, context_lines=2):
    """
    Search a single file for all terms.
    Returns (hit_count, excerpts) where excerpts is a list of strings.
    A file matches if ALL terms appear somewhere in it (case-insensitive).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0, []

    lines = text.split("\n")
    text_lower = text.lower()

    # Check all terms present
    for term in terms:
        if term.lower() not in text_lower:
            return 0, []

    # Find lines containing any term, gather context
    hits = []
    seen_lines = set()
    hit_count = 0

    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(t.lower() in line_lower for t in terms):
            hit_count += 1
            # Collect this line + context (without repeating)
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            for j in range(start, end):
                if j not in seen_lines:
                    seen_lines.add(j)
            hits.append(i)

    # Build excerpt blocks (consecutive ranges)
    if not hits:
        return 0, []

    # Group hit line indices into contiguous blocks
    excerpts = []
    collected = sorted(seen_lines)
    block = []
    for idx in collected:
        if block and idx > block[-1] + 1:
            excerpts.append(block)
            block = [idx]
        else:
            block.append(idx)
    if block:
        excerpts.append(block)

    # Format excerpts (max 3 blocks, max 4 lines each)
    formatted = []
    for block in excerpts[:3]:
        block_lines = []
        for idx in block[:4]:
            raw = lines[idx].strip()
            if not raw or raw.startswith("---"):
                continue
            highlighted = highlight(raw, terms)
            block_lines.append(truncate(highlighted, W - 6))
        if block_lines:
            formatted.extend(block_lines)
            if len(excerpts) > 1:
                formatted.append(dim("  ···"))

    return hit_count, formatted[:8]  # cap at 8 excerpt lines


# ─── Scoring ───────────────────────────────────────────────────────────────────

def score_result(hit_count, recency, category):
    """Compute a ranking score. Higher = better."""
    # Hits are the primary signal; recency is a tiebreaker
    base = hit_count * 10
    rec = recency * 3
    # Boost knowledge and notes slightly over task files
    cat_boost = 2 if category in ("knowledge", "note") else 0
    return base + rec + cat_boost


# ─── Category display ──────────────────────────────────────────────────────────

CAT_COLORS = {
    "note":             cyan,
    "knowledge":        magenta,
    "task/completed":   green,
    "task/failed":      red,
    "task/pending":     yellow,
    "task/in-progress": yellow,
    "project":          dim,
}

def cat_label(category):
    color = CAT_COLORS.get(category, dim)
    short = category.replace("task/", "")
    return color(f"[{short}]")


# ─── List mode ─────────────────────────────────────────────────────────────────

def cmd_list():
    sources = discover_sources()
    by_cat = defaultdict(list)
    for path, cat in sources:
        by_cat[cat].append(path)

    print(box_top(bold("  indexed sources"), width=W))
    print(box_row("", width=W))
    total = 0
    for cat in ["note", "knowledge", "task/completed", "task/failed",
                "task/pending", "task/in-progress", "project"]:
        files = by_cat.get(cat, [])
        if not files:
            continue
        label = cat_label(cat)
        count_str = gray(f"  {len(files)} files")
        print(box_row(f"{label}{count_str}", width=W))
        for p in files[:5]:
            print(box_row(dim(f"    {p.name}"), width=W))
        if len(files) > 5:
            print(box_row(dim(f"    … and {len(files) - 5} more"), width=W))
        print(box_row("", width=W))
        total += len(files)
    print(box_row(dim(f"  {total} files total"), width=W))
    print(box_bot(width=W))


# ─── Main search ───────────────────────────────────────────────────────────────

def cmd_search(query, context_lines=2, max_results=10, as_json=False):
    terms = [t for t in query.split() if t]
    if not terms:
        print("Usage: python3 projects/search.py <query>")
        sys.exit(1)

    sources = discover_sources()
    results = []

    for path, category in sources:
        hit_count, excerpts = search_file(path, terms, context_lines)
        if hit_count > 0:
            rec = recency_weight(path, category)
            score = score_result(hit_count, rec, category)
            results.append({
                "path": path,
                "category": category,
                "hits": hit_count,
                "recency": rec,
                "score": score,
                "excerpts": excerpts,
            })

    results.sort(key=lambda r: -r["score"])

    if as_json:
        out = []
        for r in results[:max_results]:
            out.append({
                "file": str(r["path"].relative_to(REPO)),
                "category": r["category"],
                "hits": r["hits"],
                "score": round(r["score"], 2),
                "excerpts": [re.sub(r"\033\[[^m]+m", "", e) for e in r["excerpts"]],
            })
        print(json.dumps(out, indent=2))
        return

    # ANSI output
    found = len(results)
    query_display = f'"{query}"'
    found_str = f"{found} match{'es' if found != 1 else ''}"

    title = f"{bold('search')}  {dim(query_display)}"
    print(box_top(title, width=W))
    print(box_row("", width=W))

    if found == 0:
        print(box_row(dim("  nothing found"), width=W))
        print(box_row("", width=W))
        print(box_row(dim("  Try fewer or broader terms."), width=W))
    else:
        print(box_row(dim(f"  {found_str} across {len(sources)} indexed files"), width=W))
        print(box_row("", width=W))

        for r in results[:max_results]:
            rel = str(r["path"].relative_to(REPO))
            label = cat_label(r["category"])
            hits_str = yellow(f"{r['hits']} hit{'s' if r['hits'] != 1 else ''}")
            # Recency star for notes
            star = ""
            if r["category"] == "note" and r["recency"] > 0.8:
                star = cyan("  ★")

            header = f"  {label}  {dim(rel)}"
            header_plain = re.sub(r"\033\[[^m]+m", "", header)
            pad = W - 2 - len(header_plain) - len(re.sub(r"\033\[[^m]+m", "", hits_str + star)) - 2
            print(box_row(f"{header}{' ' * max(0, pad)}{hits_str}{star}", width=W))

            for excerpt in r["excerpts"]:
                plain_exc = re.sub(r"\033\[[^m]+m", "", excerpt)
                if plain_exc.strip() == "···":
                    print(box_row(dim("  ···"), width=W))
                else:
                    print(box_row(f"    {excerpt}", width=W))

            print(box_row("", width=W))

    print(box_row(dim(f"  search · {len(terms)} term(s) · top {min(found, max_results)} of {found}"), width=W))
    print(box_bot(width=W))


# ─── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if "--list" in flags:
        cmd_list()
        return

    if not args:
        print("Usage: python3 projects/search.py <query>")
        print("       python3 projects/search.py --list")
        print("       python3 projects/search.py --plain <query>")
        print("       python3 projects/search.py --json <query>")
        sys.exit(0)

    query = " ".join(args)
    as_json = "--json" in flags
    context_lines = 2
    if "--context" in flags:
        idx = sys.argv.index("--context")
        try:
            context_lines = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            pass

    cmd_search(query, context_lines=context_lines, as_json=as_json)


if __name__ == "__main__":
    main()
