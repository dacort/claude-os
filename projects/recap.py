#!/usr/bin/env python3
"""
recap.py — Narrative digest of recent Claude OS sessions

Unlike weekly-digest.py (lists every task) and arc.py (one line per session),
recap.py produces a readable prose summary: what happened, what was built,
what's still alive, and the current state of the system.

Good for answering: "What has claude-os been up to?"

Sources:
  knowledge/workshop-summaries.json  — session summaries
  knowledge/handoffs/session-N.md    — what each session passed forward
  projects/field-notes-session-N.md  — reflective field notes
  git log                            — significant commits

Usage:
    python3 projects/recap.py              # last 7 days
    python3 projects/recap.py --days 14   # last 14 days
    python3 projects/recap.py --sessions 5 # last 5 workshop sessions
    python3 projects/recap.py --plain      # no ANSI (for piping/saving)
    python3 projects/recap.py --markdown   # clean markdown output

Author: Claude OS (Workshop session 53, 2026-03-20)
"""

import sys
import json
import re
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ── Config ──────────────────────────────────────────────────────────────────

REPO = Path(__file__).parent.parent
SUMMARIES = REPO / "knowledge" / "workshop-summaries.json"
HANDOFFS  = REPO / "knowledge" / "handoffs"
NOTES_DIR = REPO / "projects"

# ── ANSI helpers ─────────────────────────────────────────────────────────────

def _make_color(code):
    def f(s): return s if PLAIN else f"\033[{code}m{s}\033[0m"
    return f

PLAIN    = "--plain" in sys.argv or "--markdown" in sys.argv
MARKDOWN = "--markdown" in sys.argv

bold   = _make_color("1")
dim    = _make_color("2")
cyan   = _make_color("36")
green  = _make_color("32")
yellow = _make_color("33")
magenta= _make_color("35")
white  = _make_color("97")

# ── Git helpers ───────────────────────────────────────────────────────────────

def git_log(since_days: int) -> list[dict]:
    """Return significant commits in the last N days."""
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
    result = subprocess.run(
        ["git", "log", f"--since={since}", "--format=%H|%ci|%s", "--no-merges"],
        capture_output=True, text=True, cwd=REPO
    )
    commits = []
    for line in result.stdout.strip().splitlines():
        if "|" not in line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({"hash": parts[0][:8], "date": parts[1][:10], "msg": parts[2]})
    return commits

def significant_commits(commits: list[dict]) -> list[dict]:
    """Filter to commits that represent real work (feat:, fix:, etc.)."""
    sig = []
    for c in commits:
        msg = c["msg"]
        # Skip pure status transitions
        if re.match(r"task .+: (pending|in-progress|completed|add results)", msg):
            continue
        if re.match(r"workshop (status-page|workshop-\d{8}|v2-task-)", msg):
            continue
        if re.match(r"workshop \w[\w-]+: (completed|in-progress)", msg):
            continue
        if re.match(r"workshop \d+: (handoff|field notes)", msg):
            continue
        if "→" in msg and "task" in msg.lower():
            continue
        if re.match(r"task: (dispatch|v2-task)", msg):
            continue
        # Skip task result commits
        if re.match(r"task \w[\w-]+: (dry-run|security|smoke|validate)", msg, re.I):
            continue
        # Only keep feat:, fix:, docs: prefixed and a few others
        if re.match(r"(feat|fix|docs|refactor|perf|test|style|chore|note|config|add)[\s:(]", msg, re.I):
            sig.append(c)
        elif not msg.startswith("task") and not msg.startswith("workshop"):
            sig.append(c)
    return sig

# ── Workshop session helpers ──────────────────────────────────────────────────

def load_summaries() -> dict:
    if not SUMMARIES.exists():
        return {}
    with open(SUMMARIES) as f:
        return json.load(f)

def sessions_in_range(summaries: dict, since_days: int | None, n_sessions: int | None) -> list[tuple[str, str]]:
    """Return (session_key, summary_text) pairs for the requested range."""
    items = list(summaries.items())
    if n_sessions:
        items = items[-n_sessions:]
    elif since_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        filtered = []
        for k, v in items:
            # Key format: workshop-YYYYMMDD-HHMMSS
            try:
                ds = k.split("-")[1]  # YYYYMMDD
                d = datetime(int(ds[:4]), int(ds[4:6]), int(ds[6:8]), tzinfo=timezone.utc)
                if d >= cutoff:
                    filtered.append((k, v))
            except (IndexError, ValueError):
                pass
        items = filtered
    return [(k, v if isinstance(v, str) else v.get("summary", str(v))) for k, v in items]

def extract_session_number(key: str) -> int | None:
    """Try to map a workshop key to a session number via handoff files."""
    # Look for the handoff closest to this workshop's timestamp
    if not HANDOFFS.exists():
        return None
    # We can't perfectly map keys to numbers without extra metadata,
    # so we return None and let the caller use the date instead.
    return None

# ── Field notes helpers ───────────────────────────────────────────────────────

def read_field_notes(session_num: int) -> str | None:
    path = NOTES_DIR / f"field-notes-session-{session_num}.md"
    if path.exists():
        return path.read_text()
    return None

def latest_field_note_session() -> int:
    def parse_num(p):
        try:
            return int(p.stem.split("-")[-1])
        except ValueError:
            return 0
    notes = list(NOTES_DIR.glob("field-notes-session-*.md"))
    if not notes:
        return 0
    return max(parse_num(p) for p in notes)

def extract_field_note_sections(text: str) -> dict[str, str]:
    """Extract H2 sections from a field note."""
    sections = {}
    current = None
    lines = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(lines).strip()
            current = line[3:].strip()
            lines = []
        else:
            if current:
                lines.append(line)
    if current:
        sections[current] = "\n".join(lines).strip()
    return sections

# ── Handoff helpers ───────────────────────────────────────────────────────────

def latest_handoff() -> dict | None:
    if not HANDOFFS.exists():
        return None
    files = sorted(HANDOFFS.glob("session-*.md"), key=lambda p: int(re.search(r'\d+', p.stem).group() if re.search(r'\d+', p.stem) else 0))
    if not files:
        return None
    text = files[-1].read_text()
    result = {"session": files[-1].stem}
    for line in text.splitlines():
        if line.startswith("session:"):
            result["session_num"] = line.split(":", 1)[1].strip()
        if line.startswith("date:"):
            result["date"] = line.split(":", 1)[1].strip()
    # Extract sections
    current = None
    lines = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                result[current.lower().replace(" ", "_")] = "\n".join(lines).strip()
            current = line[2:].strip()
            lines = []
        else:
            if current:
                lines.append(line)
    if current:
        result[current.lower().replace(" ", "_")] = "\n".join(lines).strip()
    return result

# ── Summarization helpers ────────────────────────────────────────────────────

def deduplicate_summaries(summaries: list[str]) -> list[str]:
    """Remove near-duplicate short summaries."""
    seen_words = set()
    out = []
    for s in summaries:
        key_words = set(w.lower() for w in s.split() if len(w) > 4)
        overlap = key_words & seen_words
        if len(overlap) < 3:  # not too similar
            out.append(s)
            seen_words |= key_words
    return out

def format_commit(c: dict) -> str:
    msg = c["msg"]
    # Clean prefixes for readability
    msg = re.sub(r'^feat:\s*', '', msg)
    msg = re.sub(r'^fix:\s*', 'Fixed: ', msg)
    msg = re.sub(r'^docs:\s*', '', msg)
    msg = re.sub(r'^workshop \w+:\s*', '', msg)
    return msg

def group_commits_by_theme(commits: list[dict]) -> dict[str, list[str]]:
    """Group significant commits into rough themes."""
    themes = {
        "Controller / infra": [],
        "Tools built": [],
        "Fixes": [],
        "Other": [],
    }
    for c in commits:
        msg = c["msg"].lower()
        raw = c["msg"]
        if "controller" in msg or "comms" in msg or "dispatcher" in msg or "queue" in msg or "scheduler" in msg or "worker" in msg or "watcher" in msg:
            themes["Controller / infra"].append(format_commit(c))
        elif raw.startswith("feat:") or re.match(r"feat:", raw, re.I):
            themes["Tools built"].append(format_commit(c))
        elif raw.lower().startswith("fix") or re.match(r"fix[:(]", raw, re.I):
            themes["Fixes"].append(format_commit(c))
        elif "docs:" in raw.lower() or "workshop" in raw.lower() or "task:" in raw.lower():
            pass  # skip pure docs/workshop completions that slipped through
        else:
            themes["Other"].append(format_commit(c))
    return {k: v for k, v in themes.items() if v}

# ── Main rendering ────────────────────────────────────────────────────────────

def box_line(w=66):
    return "─" * w

def sessions_date_range_days(sessions: list[tuple[str, str]]) -> int:
    """How many days to look back to cover the given sessions?"""
    if not sessions:
        return 7
    oldest_key = sessions[0][0]
    try:
        ds = oldest_key.split("-")[1]
        oldest = datetime(int(ds[:4]), int(ds[4:6]), int(ds[6:8]), tzinfo=timezone.utc)
        delta  = datetime.now(timezone.utc) - oldest
        return max(1, delta.days + 1)
    except (IndexError, ValueError):
        return 7

def render(days: int | None, n_sessions: int | None):
    summaries = load_summaries()
    sessions  = sessions_in_range(summaries, days, n_sessions)
    git_days  = days if days else sessions_date_range_days(sessions)
    commits   = git_log(git_days)
    sig_commits = significant_commits(commits)
    handoff   = latest_handoff()
    last_note = latest_field_note_session()
    total_sessions = len(summaries)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    period = f"last {days} days" if days else f"last {len(sessions)} sessions"

    if MARKDOWN:
        _render_markdown(sessions, sig_commits, handoff, last_note, now, period, total_sessions)
    else:
        _render_terminal(sessions, sig_commits, handoff, last_note, now, period, total_sessions)


def _render_terminal(sessions, sig_commits, handoff, last_note, now, period, total_sessions):
    W = 68

    def rule():
        return dim("  " + box_line(W - 2))

    print()
    print(f"  {bold(white('CLAUDE OS RECAP'))}  {dim(now)}")
    print(dim(f"  {period} · {len(sessions)} sessions · {len(sig_commits)} notable commits"))
    print()

    # ── What happened ─────────────────────────────────────────────────
    if sessions:
        print(f"  {bold('WHAT HAPPENED')}")
        print()

        # Group sessions by day
        by_day = {}
        for key, summary in sessions:
            try:
                ds = key.split("-")[1]
                day = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"
            except (IndexError, ValueError):
                day = "unknown"
            by_day.setdefault(day, []).append(summary)

        for day, day_summaries in sorted(by_day.items()):
            deduped = deduplicate_summaries(day_summaries)
            print(f"  {cyan(day)}")
            for s in deduped:
                # Wrap at ~60 chars
                words = s.split()
                lines = []
                cur = ""
                for w in words:
                    if len(cur) + len(w) + 1 > 62:
                        lines.append(cur)
                        cur = w
                    else:
                        cur = (cur + " " + w).strip()
                if cur:
                    lines.append(cur)
                print(f"  {dim('·')} {lines[0]}")
                for extra in lines[1:]:
                    print(f"    {extra}")
            print()

    # ── What was built ─────────────────────────────────────────────────
    if sig_commits:
        print(f"  {bold('NOTABLE COMMITS')}")
        print()
        grouped = group_commits_by_theme(sig_commits)
        for theme, items in grouped.items():
            print(f"  {yellow(theme)}")
            for item in items[:5]:  # cap per theme
                print(f"  {dim('·')} {item[:70]}")
            if len(items) > 5:
                print(f"  {dim(f'  … and {len(items) - 5} more')}")
            print()

    # ── What's alive ─────────────────────────────────────────────────
    if handoff:
        alive = handoff.get("still_alive_/_unfinished", "") or handoff.get("alive", "")
        nxt   = handoff.get("one_specific_thing_for_next_session", "") or handoff.get("next", "")

        if alive or nxt:
            header = "WHAT\u2019S ALIVE"
            print(f"  {bold(header)}")
            print()
            if alive:
                lines = alive.strip().splitlines()
                for line in lines[:4]:
                    if line.strip():
                        print(f"  {dim('·')} {line.strip()[:72]}")
                print()
            if nxt:
                print(f"  {bold('NEXT')}  {dim(nxt.strip()[:72])}")
                print()

    # ── System state ─────────────────────────────────────────────────
    print(rule())
    print(f"  {dim(f'Session {total_sessions}  ·  field notes through S{last_note}  ·  {len(sessions)} sessions shown')}")
    print()


def _render_markdown(sessions, sig_commits, handoff, last_note, now, period, total_sessions):
    total_sessions = len(load_summaries())
    print(f"# Claude OS Recap — {now}")
    print()
    print(f"*{period} · {len(sessions)} sessions · {len(sig_commits)} notable commits · session {total_sessions}*")
    print()

    if sessions:
        print("## What happened")
        print()
        by_day = {}
        for key, summary in sessions:
            try:
                ds = key.split("-")[1]
                day = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"
            except (IndexError, ValueError):
                day = "unknown"
            by_day.setdefault(day, []).append(summary)

        for day, day_summaries in sorted(by_day.items()):
            deduped = deduplicate_summaries(day_summaries)
            print(f"**{day}**")
            print()
            for s in deduped:
                print(f"- {s}")
            print()

    if sig_commits:
        print("## Notable commits")
        print()
        grouped = group_commits_by_theme(sig_commits)
        for theme, items in grouped.items():
            print(f"**{theme}**")
            for item in items[:5]:
                print(f"- {item}")
            if len(items) > 5:
                print(f"- *…and {len(items) - 5} more*")
            print()

    if handoff:
        alive = handoff.get("still_alive_/_unfinished", "") or handoff.get("alive", "")
        nxt   = handoff.get("one_specific_thing_for_next_session", "") or handoff.get("next", "")
        if alive:
            print("## What's alive")
            print()
            for line in alive.strip().splitlines():
                if line.strip():
                    print(f"- {line.strip()}")
            print()
        if nxt:
            print("## Next")
            print()
            print(nxt.strip())
            print()

    print(f"---")
    print(f"*Field notes through S{last_note} · Generated {now}*")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Narrative digest of recent sessions")
    parser.add_argument("--days",     type=int, default=7,  help="Days to look back (default: 7)")
    parser.add_argument("--sessions", type=int,             help="Last N sessions (overrides --days)")
    parser.add_argument("--plain",    action="store_true",  help="No ANSI colors")
    parser.add_argument("--markdown", action="store_true",  help="Clean markdown output")
    args = parser.parse_args()

    global PLAIN
    if args.plain or args.markdown:
        PLAIN = True

    if args.sessions:
        render(days=None, n_sessions=args.sessions)
    else:
        render(days=args.days, n_sessions=None)

if __name__ == "__main__":
    main()
