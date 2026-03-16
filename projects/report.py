#!/usr/bin/env python3
"""
report.py — What Claude OS did for you (and what needs your attention)

Unlike every other tool in projects/, this one faces outward. Not "how is the
system doing" (vitals.py) or "what changed since last session" (garden.py) —
but "here is what was accomplished on your behalf, and here is what you need
to decide or act on."

Usage:
    python3 projects/report.py              # full report
    python3 projects/report.py --brief      # just the action items
    python3 projects/report.py --plain      # no ANSI colors

Author: Claude OS (Workshop session 21, 2026-03-13)
"""

import re
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).parent.parent
W = 68
PLAIN = "--plain" in sys.argv

# ── color helpers ──────────────────────────────────────────────────────────────

def c(text, fg=None, bold=False, dim=False):
    if PLAIN:
        return text
    codes = []
    if bold: codes.append("1")
    if dim:  codes.append("2")
    if fg:
        palette = {
            "cyan": "36", "blue": "34", "green": "32",
            "yellow": "33", "red": "31", "white": "97",
            "magenta": "35", "gray": "90",
        }
        codes.append(palette.get(fg, "0"))
    if not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"

def box(lines, width=W):
    top = "╭" + "─" * width + "╮"
    bot = "╰" + "─" * width + "╯"
    inner = []
    for line in lines:
        # strip ANSI for length computation
        visible = re.sub(r'\033\[[0-9;]*m', '', line)
        pad = width - 2 - len(visible)
        inner.append("│ " + line + " " * max(0, pad) + " │")
    return "\n".join([top] + inner + [bot])

def rule(width=W):
    return "  " + c("─" * (width - 2), dim=True)

# ── task parsing ───────────────────────────────────────────────────────────────

WORKSHOP_PREFIXES = ("workshop-", "workshop_")

WORKSHOP_SLUGS_PATTERNS = re.compile(
    r'^(workshop-|workshop_|checking-in|creative-thinking|seattle-sunset|'
    r'design-orchestration-layer|fix-new-task-bug)',
    re.IGNORECASE
)

def is_workshop(path):
    stem = path.stem
    if stem.startswith("workshop-") or stem.startswith("workshop_"):
        return True
    # Also detect tasks that were really workshop/creative tasks by slug pattern
    try:
        text = path.read_text()
        meta = parse_frontmatter(text)
        if meta.get("profile") in ("creative", "small"):
            # Could be either, check for "Workshop:" title
            m = re.search(r'^#\s+Workshop:', text, re.MULTILINE)
            if m:
                return True
    except Exception:
        pass
    return False

def parse_frontmatter(text):
    """Parse YAML-like frontmatter between --- delimiters."""
    meta = {}
    m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return meta
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"')
    return meta

def extract_result_summary(text):
    """
    Extract the key finding from a task result section.
    Returns (tldr, recommendation) where each may be None.
    """
    # Get everything after ## Results
    results_match = re.search(r'## Results\n(.*)', text, re.DOTALL)
    if not results_match:
        return None, None
    results = results_match.group(1)

    # Strip worker preamble (=== Claude OS Worker ===...---)
    results = re.sub(r'=== Claude OS Worker.*?---\n', '', results, flags=re.DOTALL)

    tldr = None
    recommendation = None

    # Look for **tldr:** or **tldr up front:**
    m = re.search(r'\*\*tldr[^*]*\*\*[:\s]+(.+?)(?:\n|$)', results, re.IGNORECASE)
    if m:
        tldr = m.group(1).strip().rstrip(".")

    # Look for first substantive paragraph after worker intro lines
    if not tldr:
        # Skip generic opener lines and find first real paragraph
        GENERIC_OPENERS = re.compile(
            r'^(?:done\b|here\b|what i\b|i\b|the fix\b|overall\b|'
            r'summary\b|result\b)',
            re.IGNORECASE
        )
        paras = re.split(r'\n{2,}', results)
        for para in paras[1:]:  # skip first paragraph (often just "Done.")
            para = para.strip()
            para = re.sub(r'^#+\s*', '', para)  # strip heading markers
            para = re.sub(r'\*\*([^*]+)\*\*', r'\1', para)  # bold
            para = re.sub(r'[*_`\[\]]', '', para)
            para = para.replace('\n', ' ').strip()
            if len(para) > 40 and not GENERIC_OPENERS.match(para) and not para.startswith('|'):
                tldr = para[:120].rstrip(".")
                break

    # Look for recommendation table (| Context | Verdict |) or ## Recommendation
    m = re.search(r'## Recommendation\n+(.*?)(?:\n##|\Z)', results, re.DOTALL | re.IGNORECASE)
    if m:
        rtext = m.group(1).strip()
        recommendation = rtext[:200]

    # Look for inline "**Recommendation:**" or "**Bottom line:**"
    if not recommendation:
        m = re.search(r'\*\*(?:Recommendation|Bottom line)[:\s]+\*\*\s*(.+?)(?:\n|$)',
                      results, re.IGNORECASE)
        if m:
            recommendation = m.group(1).strip()

    # Fallback: first non-empty line of results that looks substantive
    SKIP_INTROS = re.compile(
        r'^(?:here\b|done\b|i\b|the fix\b|what i\b|overall\b)',
        re.IGNORECASE
    )
    if not tldr:
        for line in results.split("\n"):
            line = line.strip()
            line = re.sub(r'^#+\s*', '', line)        # strip headings
            line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)  # strip bold
            line = re.sub(r'[*_`\[\]]', '', line)
            # Skip short lines, separators, tables, boring intros
            if (len(line) > 35 and not line.startswith('=') and
                    not line.startswith('|') and not SKIP_INTROS.match(line)):
                tldr = line[:120]
                break

    # Clean up: take only first line of tldr
    if tldr:
        tldr = tldr.split("\n")[0].strip()
        # Remove markdown formatting
        tldr = re.sub(r'\*\*([^*]+)\*\*', r'\1', tldr)
        tldr = re.sub(r'[*_`]', '', tldr)
        # Remove trailing punctuation-then-newline artifacts
        tldr = tldr.rstrip(".,")

    # Clean up recommendation: take first paragraph or table row
    if recommendation:
        lines = [l.strip() for l in recommendation.split("\n") if l.strip()]
        # If it's a markdown table, extract the skip/adopt cells
        if lines and lines[0].startswith("|"):
            # Try to find the first real data row (skip header and separator)
            data_rows = []
            for row in lines:
                cols = [co.strip() for co in row.split("|") if co.strip()]
                # skip separator rows (all dashes)
                if all(re.match(r'^-+$', co) for co in cols):
                    continue
                if cols:
                    data_rows.append(cols)
            # data_rows[0] is likely the header; data_rows[1] is first data row
            if len(data_rows) >= 2:
                cols = data_rows[1]
                recommendation = f"{cols[0]}: {cols[1]}" if len(cols) >= 2 else cols[0]
            elif data_rows:
                recommendation = " | ".join(data_rows[0][:2])
            else:
                recommendation = None
            if recommendation:
                recommendation = re.sub(r'\*\*([^*]+)\*\*', r'\1', recommendation)
        else:
            # Take first non-empty non-header line
            recommendation = lines[0] if lines else None
            if recommendation:
                recommendation = re.sub(r'\*\*([^*]+)\*\*', r'\1', recommendation)
                recommendation = re.sub(r'[*_`]', '', recommendation)

    return tldr, recommendation

def parse_task(path):
    """Parse a completed task file."""
    text = path.read_text()
    meta = parse_frontmatter(text)

    # Title
    m = re.search(r'^#\s+(.+)', text, re.MULTILINE)
    title = m.group(1).strip() if m else path.stem

    # Completion date from "Finished:" line
    finished = None
    m = re.search(r'Finished:\s*(\d{4}-\d{2}-\d{2})', text)
    if m:
        finished = m.group(1)
    if not finished:
        m = re.search(r'Started:\s*(\d{4}-\d{2}-\d{2})', text)
        if m:
            finished = m.group(1)

    # Created date from frontmatter
    created = meta.get("created", "")
    if created and not finished:
        finished = created[:10]

    tldr, recommendation = extract_result_summary(text)

    return {
        "path": path,
        "slug": path.stem,
        "title": title,
        "finished": finished or "",
        "tldr": tldr,
        "recommendation": recommendation,
        "is_workshop": is_workshop(path),
    }

# ── issue parsing ──────────────────────────────────────────────────────────────

def get_open_issues():
    """Fetch open GitHub issues via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--limit", "20", "--json",
             "number,title,createdAt,labels,body"],
            capture_output=True, text=True, timeout=15,
            cwd=str(REPO)
        )
        if result.returncode != 0:
            return []
        import json
        return json.loads(result.stdout)
    except Exception:
        return []

def get_open_prs():
    """Fetch open PRs via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--limit", "10", "--json",
             "number,title,createdAt,author,isDraft"],
            capture_output=True, text=True, timeout=15,
            cwd=str(REPO)
        )
        if result.returncode != 0:
            return []
        import json
        return json.loads(result.stdout)
    except Exception:
        return []

def deadline_from_title(title):
    """Extract deadline date from issue title like 'expires YYYY-MM-DD'."""
    m = re.search(r'(\d{4}-\d{2}-\d{2})', title)
    if m:
        return m.group(1)
    return None

def days_until(date_str):
    """Days until a date string like '2026-04-11'. Negative = past."""
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (target - now).days
    except Exception:
        return None

# ── next suggestion ────────────────────────────────────────────────────────────

def get_next_suggestion():
    """Get top recommendation from suggest.py (runs it, parses output)."""
    try:
        result = subprocess.run(
            ["python3", "projects/suggest.py", "--plain"],
            capture_output=True, text=True, timeout=20,
            cwd=str(REPO)
        )
        if result.returncode != 0:
            return None
        # Find "Build:  <name>" line - strip box-drawing and extra chars
        m = re.search(r'Build:\s+(.+)', result.stdout)
        if m:
            raw = m.group(1).strip()
            # Remove trailing box-drawing character │ and whitespace
            raw = re.sub(r'[\s│]+$', '', raw)
            return raw
    except Exception:
        pass
    return None

# ── display ────────────────────────────────────────────────────────────────────

def section(title):
    print()
    print(f"  {c(title, bold=True, fg='white')}")
    print()

def print_box(header, subtitle=""):
    top = "╭" + "─" * W + "╮"
    bot = "╰" + "─" * W + "╯"
    print(top)
    h = f"  {c('report.py', bold=True, fg='cyan')}  {c('—  What Claude OS did for you', dim=True)}"
    h_len = len(re.sub(r'\033\[[0-9;]*m', '', h))
    print("│" + h + " " * (W - h_len) + "│")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sub = f"  {c(now_str, dim=True)}"
    sub_len = len(re.sub(r'\033\[[0-9;]*m', '', sub))
    print("│" + sub + " " * (W - sub_len) + "│")
    print(bot)

def truncate(text, width=60):
    if not text:
        return ""
    text = text.strip()
    if len(text) > width:
        return text[:width-1] + "…"
    return text

def main():
    brief = "--brief" in sys.argv
    tasks_dir = REPO / "tasks" / "completed"

    # ── Load tasks ─────────────────────────────────────────────────────────────
    real_tasks = []
    for p in sorted(tasks_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        task = parse_task(p)
        if not task["is_workshop"] and task["slug"] not in (
            "checking-in", "creative-thinking", "seattle-sunset",
            "fix-new-task-bug", "design-orchestration-layer",
        ):
            real_tasks.append(task)

    # Sort by finished date, most recent first
    real_tasks.sort(key=lambda t: t["finished"] or "", reverse=True)

    # Limit to tasks from the last 30 days (or all if brief)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    recent = [t for t in real_tasks if t["finished"] >= cutoff] if not brief else real_tasks[:5]
    if not recent:
        recent = real_tasks[:5]  # fallback: show latest 5

    # ── Issues and PRs ─────────────────────────────────────────────────────────
    issues = get_open_issues()
    prs = get_open_prs()

    # ── Next suggestion ────────────────────────────────────────────────────────
    next_up = get_next_suggestion()

    # ── Render ─────────────────────────────────────────────────────────────────
    print_box("report.py", "What Claude OS did for you")

    # ── Section 1: Completed work ─────────────────────────────────────────────
    if not brief:
        section("COMPLETED WORK  (last 30 days)")
        if not recent:
            print(f"  {c('No real tasks completed recently.', dim=True)}")
        for task in recent:
            date_str = task["finished"] or "unknown"
            print(f"  {c(task['title'][:55], bold=True)}")
            print(f"  {c(date_str, dim=True, fg='gray')}  ·  {c(task['slug'], dim=True)}")
            if task["tldr"]:
                tl = truncate(task["tldr"], 64)
                print(f"  {c(tl, dim=True)}")
            if task["recommendation"]:
                rec = truncate(task["recommendation"], 64)
                print(f"  {c('→ ', fg='cyan')}{c(rec, fg='cyan', dim=True)}")
            print()

    # ── Section 2: Action items ────────────────────────────────────────────────
    section("ACTION NEEDED")

    action_count = 0

    # Deadline issues
    urgent_issues = []
    for issue in issues:
        deadline = deadline_from_title(issue["title"])
        if deadline:
            d = days_until(deadline)
            if d is not None:
                urgent_issues.append((d, deadline, issue))

    urgent_issues.sort(key=lambda x: x[0])
    for days, deadline, issue in urgent_issues:
        action_count += 1
        num = issue["number"]
        title = issue["title"]
        if days < 0:
            urgency = c(f"EXPIRED {-days}d ago", bold=True, fg="red")
        elif days <= 14:
            urgency = c(f"{days}d left", bold=True, fg="red")
        elif days <= 30:
            urgency = c(f"{days}d left", bold=True, fg="yellow")
        else:
            urgency = c(f"{days}d left", fg="green")
        print(f"  {c(f'#{num}', fg='cyan', bold=True)}  {urgency}  {title[:45]}")
        print()

    # Unactioned recommendations from completed tasks
    for task in recent[:8]:
        if task["recommendation"] and not task["is_workshop"]:
            action_count += 1
            print(f"  {c('Unactioned:', fg='yellow', bold=True)} {c(task['title'][:40], bold=True)}")
            rec = truncate(task["recommendation"], 62)
            print(f"  {c(rec, dim=True)}")
            print(f"  {c('→ Mark resolved by creating a follow-up task or issue', dim=True)}")
            print()

    # Open PRs
    if prs:
        for pr in prs[:3]:
            num = pr["number"]
            title = pr["title"]
            is_draft = pr.get("isDraft", False)
            action_count += 1
            if is_draft:
                status = c("draft PR", dim=True)
            else:
                status = c("PR ready for review", fg="yellow")
            print(f"  {c(f'#{num}', fg='cyan', bold=True)}  {status}")
            print(f"  {title[:60]}")
            print()

    # Non-deadline issues
    non_deadline = [i for i in issues if not deadline_from_title(i["title"])]
    for issue in non_deadline[:3]:
        num = issue["number"]
        title = issue["title"]
        action_count += 1
        labels = ", ".join(l["name"] for l in issue.get("labels", []))
        label_str = f"  {c(labels, dim=True)}" if labels else ""
        print(f"  {c(f'#{num}', fg='cyan')}  {title[:55]}{label_str}")
        print()

    if action_count == 0:
        print(f"  {c('Nothing urgent.', dim=True)}")
        print()

    # ── Section 3: Coming up ───────────────────────────────────────────────────
    section("COMING UP")
    if next_up:
        print(f"  {c('Next suggestion from suggest.py:', dim=True)}")
        print(f"  {c(next_up, bold=True, fg='magenta')}")
    else:
        print(f"  {c('Run suggest.py to see recommendations.', dim=True)}")

    print()

    # ── Footer ─────────────────────────────────────────────────────────────────
    print(rule())
    print(f"  {c('report.py  ·  session 21  ·  2026-03-13', dim=True)}")
    note = "Run with --brief for action items only."
    print(f"  {c(note, dim=True)}")
    print()


if __name__ == "__main__":
    main()
