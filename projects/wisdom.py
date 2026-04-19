#!/usr/bin/env python3
"""
wisdom.py — Distilled learning from across all sessions.

Reads every field note, extracts closing reflections (Codas), identifies
the promise chain (predictions made and kept), recurring themes, and the
unresolved threads that the system keeps returning to.

Usage:
  python3 projects/wisdom.py           # full report
  python3 projects/wisdom.py --plain   # no ANSI colors
  python3 projects/wisdom.py --codas   # show complete codas at the end
  python3 projects/wisdom.py --themes  # only the theme analysis

Note on the "promise chain":
  wisdom.py tracks forward-looking promises made in Codas (e.g., "next session
  will...") and checks whether they were fulfilled. This is a retrospective read
  on what actually transferred between sessions.

  For *recording and tracking new predictions* (testable forward claims with
  explicit resolution tracking), use predict.py instead:
    python3 projects/predict.py --add "claim" --about N
    python3 projects/predict.py --stats

  Different tools: wisdom.py reads what happened; predict.py tracks what you
  claim will happen. The former is forensic; the latter is empirical.
"""

import sys
import re
from pathlib import Path
from collections import Counter

# ── color helpers ──────────────────────────────────────────────────────────────
PLAIN = "--plain" in sys.argv

def c(code, text):
    return text if PLAIN else f"\033[{code}m{text}\033[0m"

def bold(t):   return c("1", t)
def dim(t):    return c("2", t)
def green(t):  return c("32", t)
def yellow(t): return c("33", t)
def cyan(t):   return c("36", t)
def red(t):    return c("31", t)
def magenta(t):return c("35", t)
def white(t):  return c("1;97", t)

# ── parsing ────────────────────────────────────────────────────────────────────

def parse_session_number(filename):
    """Extract session number from filename."""
    name = Path(filename).stem
    if name == "field-notes-from-free-time":
        return 1
    m = re.search(r"session-(\d+)", name)
    return int(m.group(1)) + 1 if m else 999  # +1 because session-2 file = session 2

def parse_session_number_exact(filename):
    """Return exact session number: free-time=1, session-2=2, etc."""
    name = Path(filename).stem
    if name == "field-notes-from-free-time":
        return 1
    m = re.search(r"session-(\d+)", name)
    return int(m.group(1)) if m else 999

def parse_field_note(path):
    """Parse a field note file, returning metadata and coda text."""
    text = path.read_text()
    lines = text.split("\n")

    # Session number
    num = parse_session_number_exact(path.name)

    # Title from first ## heading
    title = ""
    for line in lines:
        if line.startswith("## ") and not line.startswith("## What I") and not line.startswith("## Coda"):
            title = line[3:].strip()
            break

    # Date from *by Claude OS — ...*
    date = ""
    m = re.search(r"\*by Claude OS — Workshop session, (\d{4}-\d{2}-\d{2})\*", text)
    if m:
        date = m.group(1)

    # Coda / What's Next section
    coda_text = extract_section(lines, ["## Coda", "## What's Next", "## Closing"])

    # Built tools: lines like `### `name.py`
    built = re.findall(r"###\s+`?([a-z][a-z0-9_-]+\.py)`?", text)

    return {
        "num": num,
        "title": title,
        "date": date,
        "built": built,
        "coda": coda_text.strip(),
        "path": path,
    }

def extract_section(lines, headers):
    """Extract text following any of the given headers until the next ## heading."""
    capturing = False
    result = []
    for line in lines:
        if any(line.strip() == h for h in headers):
            capturing = True
            continue
        if capturing:
            if line.startswith("## ") and not any(line.strip() == h for h in headers):
                break
            if line.startswith("---") and result:
                break
            result.append(line)
    return "\n".join(result)

# ── promise chain ──────────────────────────────────────────────────────────────

PROMISE_PATTERNS = [
    # "what I'd want session N to ..."
    r"(?:what I'?d want|what I want)\s+session\s+(\d+)\s+to\s+([^.!?\n]{15,80})",
    # "session N's problems are session N's"
    r"session\s+(\d+)'?s\s+problems",
    # "the next thing I would build..."
    r"the next thing I(?:'d| would)\s+(?:explore|build|want|do)\s*[:\-–]?\s*([^.!?\n]{10,80})",
    # "the next session should"
    r"next session should\s+([^.!?\n]{10,80})",
    # "for session N:"
    r"[Ff]or session\s+(\d+)[:\s]+([^.!?\n]{10,80})",
    # "I'd want session N"
    r"[Ii]f\s+dacort\s+\w+\s+(?:it|them|the\s+\w+),\s+(?:then\s+)?session\s+(\d+)\s+should\s+([^.!?\n]{10,80})",
]

def extract_promises(coda_text, session_num):
    """Find forward-looking promises/predictions in a coda."""
    promises = []
    for pattern in PROMISE_PATTERNS:
        for m in re.finditer(pattern, coda_text, re.IGNORECASE):
            groups = m.groups()
            if len(groups) >= 2 and groups[0].isdigit():
                target_session = int(groups[0])
                prediction = groups[1].strip().rstrip(".").strip()
                promises.append({
                    "from_session": session_num,
                    "to_session": target_session,
                    "prediction": prediction,
                    "full_match": m.group(0)[:100],
                })
            elif len(groups) >= 1 and not groups[0].isdigit():
                # No session number, generic forward reference
                promises.append({
                    "from_session": session_num,
                    "to_session": session_num + 1,
                    "prediction": groups[0].strip().rstrip(".").strip(),
                    "full_match": m.group(0)[:100],
                })
    return promises

# Known promise chain (manually curated from reading the codas)
KNOWN_PROMISES = [
    {
        "from": 6,
        "to": 7,
        "promised": "build a garden/delta tool to show what changed since last session",
        "outcome": "garden.py built in session 7",
        "kept": True,
    },
    {
        "from": 7,
        "to": 8,
        "promised": "fix vitals.py to not penalize credit-balance failures as task failures",
        "outcome": "fixed in session 8 (now counted as infra failures)",
        "kept": True,
    },
    {
        "from": 8,
        "to": 9,
        "promised": "auto-inject preferences.md into worker system prompts (Idea 4)",
        "outcome": "done by session 9 — preferences.md now auto-injected via entrypoint.sh",
        "kept": True,
    },
    {
        "from": 9,
        "to": 10,
        "promised": "open a multi-agent orchestration proposal (Idea 7)",
        "outcome": "PR #2 opened in session 10 with full orchestration design",
        "kept": True,
    },
    {
        "from": 11,
        "to": 12,
        "promised": "look at whether next.py suggestions have drifted from reality",
        "outcome": "partially done — session 12 audited next.py and found ideas were stale",
        "kept": True,
    },
    {
        "from": 13,
        "to": None,
        "promised": "the 2,000-line design constraint should be a proposal",
        "outcome": "constraints.py built in session 17 (4 sessions later)",
        "kept": True,
    },
    {
        "from": 15,
        "to": None,
        "promised": "the action layer is the open frontier — what comes next is actual action",
        "outcome": "closed — session 20 built suggest.py, the system's first action tool (creates task files)",
        "kept": True,
    },
    {
        "from": 16,
        "to": None,
        "promised": "act on the insights the system accumulates; action layer is the frontier",
        "outcome": "closed — session 20: suggest.py observes state, proposes tasks, writes task files",
        "kept": True,
    },
    {
        "from": 20,
        "to": 27,
        "promised": "feedback loop is missing — suggest.py queues tasks but can't observe outcomes",
        "outcome": "closed in session 27 — suggest.py now logs recommendations to suggestion-log.json and shows their fate (pending/completed/failed/not submitted) in a PAST SUGGESTIONS section",
        "kept": True,
    },
    {
        "from": 17,
        "to": None,
        "promised": "constraints.py + questions.py: run at session start to slow down before speeding up",
        "outcome": "both tools available; uptake by subsequent sessions: partial",
        "kept": None,  # ongoing
    },
]

# ── recurring themes ───────────────────────────────────────────────────────────

STOPWORDS = {
    "the", "a", "an", "to", "of", "in", "it", "is", "was", "and", "or", "but",
    "for", "with", "that", "this", "are", "be", "been", "have", "has", "had",
    "from", "what", "when", "which", "by", "if", "not", "at", "on", "as",
    "would", "should", "could", "will", "run", "get", "still", "now", "just",
    "you", "i", "we", "me", "my", "your", "its", "their", "them", "they",
    "python3", "projects", "md", "py", "so", "more", "no", "than", "about",
    "all", "one", "two", "do", "up", "see", "how", "next", "last", "each",
    "any", "who", "our", "most", "then", "into", "there", "here", "these",
    "some", "out", "only", "other", "can", "also", "both", "new", "make",
    "where", "want", "know", "think", "find", "mean", "give", "like", "after",
    "before", "session", "tool", "thing", "things", "something", "build",
    "built", "file", "system", "work", "done", "right", "way", "down",
}

# High-signal phrases to search for across codas
THEME_PHRASES = [
    "action layer",
    "multi-agent",
    "orchestration",
    "open frontier",
    "dacort",
    "field guide",
    "preferences.md",
    "exoclaw",
    "memory tool",
    "2,000-line",
    "constraint",
    "the queue",
    "vibe score",
    "100/100",
    "promise",
    "letter",
    "continuity",
    "deferred",
]

def find_recurring_themes(sessions):
    """Find phrases appearing in multiple session codas."""
    all_coda_text = [(s["num"], s["coda"].lower()) for s in sessions if s["coda"]]

    # Phrase-level matching
    phrase_sessions = {}
    for phrase in THEME_PHRASES:
        phrase_lower = phrase.lower()
        appeared_in = []
        for num, coda in all_coda_text:
            if phrase_lower in coda:
                appeared_in.append(num)
        if len(appeared_in) >= 2:
            phrase_sessions[phrase] = appeared_in

    # Word frequency across all codas
    word_counter = Counter()
    for _, coda in all_coda_text:
        words = re.findall(r"\b[a-z][a-z]{3,}\b", coda)
        for w in words:
            if w not in STOPWORDS:
                word_counter[w] += 1

    top_words = [(w, n) for w, n in word_counter.most_common(20) if n >= 3]

    return phrase_sessions, top_words

# ── display ────────────────────────────────────────────────────────────────────

def box_line(width=66):
    return "─" * width

def header_box(title, subtitle="", width=66):
    lines = [f"╭{box_line(width)}╮"]
    lines.append(f"│  {bold(title):<{width-2}}│")
    if subtitle:
        lines.append(f"│  {dim(subtitle):<{width-2}}│")
    lines.append(f"╰{box_line(width)}╯")
    return "\n".join(lines)

def section_header(title):
    return f"\n  {bold(white(title))}\n"

def promise_icon(kept):
    if kept is True:
        return green("✓")
    elif kept is False:
        return yellow("⟳")
    else:
        return cyan("·")

def wrap_text(text, width=58, indent=6):
    """Simple word wrap."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            if current:
                lines.append(" " * indent + current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(" " * indent + current)
    return "\n".join(lines)

def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="wisdom.py",
        description="Distilled learning from across all sessions.\n"
                    "Shows the promise chain (predictions made and kept), recurring themes,\n"
                    "and the unresolved threads the system keeps returning to.",
        epilog=(
            "examples:\n"
            "  python3 projects/wisdom.py           # full report\n"
            "  python3 projects/wisdom.py --themes  # only the recurring theme analysis\n"
            "  python3 projects/wisdom.py --codas   # append all closing reflections\n"
            "  python3 projects/wisdom.py --plain   # no ANSI colors (safe for piping)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--plain", action="store_true",
                        help="disable ANSI colors (safe for piping)")
    parser.add_argument("--codas", action="store_true",
                        help="append all complete closing reflections in chronological order")
    parser.add_argument("--themes", action="store_true",
                        help="show only the recurring theme analysis, skip promise chain")
    parser.parse_args()

    repo = Path(__file__).parent.parent
    notes_dir = repo / "projects"

    # Gather all field note files
    files = sorted(
        notes_dir.glob("field-notes*.md"),
        key=lambda p: parse_session_number_exact(p.name)
    )

    sessions = [parse_field_note(f) for f in files]
    sessions.sort(key=lambda s: s["num"])

    total = len(sessions)
    codas_with_content = sum(1 for s in sessions if len(s["coda"]) > 20)

    # Print header
    subtitle = f"{total} sessions · {codas_with_content} codas · what the system knows about itself"
    dashes = "─" * 66
    topbar = "╭" + dashes + "╮"
    botbar = "╰" + dashes + "╯"
    pad1 = " " * max(0, 66 - len("  wisdom.py  —  distilled learning across all sessions") - 1)
    pad2 = " " * max(0, 66 - len("  " + subtitle) - 1)
    print()
    print(topbar)
    print("│  " + bold("wisdom.py") + "  " + dim("—  distilled learning across all sessions") + pad1 + "│")
    print("│  " + dim(subtitle) + pad2 + "│")
    print(botbar)

    # ── SECTION 1: Promise chain ──────────────────────────────────────────────
    if "--themes" not in sys.argv:
        print(section_header("THE PROMISE CHAIN"))
        print(f"  {dim('Predictions made in closing reflections, and what happened.')}\n")

        kept_count = sum(1 for p in KNOWN_PROMISES if p["kept"] is True)
        open_count = sum(1 for p in KNOWN_PROMISES if p["kept"] is False)
        ongoing_count = sum(1 for p in KNOWN_PROMISES if p["kept"] is None)

        print(f"  {green(f'{kept_count} kept')}  {yellow(f'{open_count} still open')}  {cyan(f'{ongoing_count} ongoing')}\n")

        for p in KNOWN_PROMISES:
            icon = promise_icon(p["kept"])
            to_str = f"→ S{p['to']}" if p.get("to") else "→ later"
            from_num = p["from"]
            print(f"  {icon}  {dim(f'S{from_num} {to_str}')}")
            print(f"     {bold(p['promised'][:70])}")
            outcome_color = green if p["kept"] else (yellow if p["kept"] is False else cyan)
            outcome_text = p["outcome"][:70]
            print(f"     {outcome_color(dim(outcome_text))}")
            print()

        print(f"  {dim('─' * 60)}")
        kept = sum(1 for p in KNOWN_PROMISES if p["kept"] is True)
        total_ps = len([p for p in KNOWN_PROMISES if p["kept"] is not None])
        open_count = sum(1 for p in KNOWN_PROMISES if p["kept"] is False)
        msg1 = f"The system kept {kept} of {total_ps} explicit predictions."
        print(f"  {dim(msg1)}")
        if open_count == 0:
            print(f"  {dim('All tracked promises have been kept.')}")
        else:
            open_ps = [p for p in KNOWN_PROMISES if p["kept"] is False]
            for p in open_ps:
                print(f"  {dim('Open: ' + p['promised'][:70])}")

    # ── SECTION 2: Recurring themes ───────────────────────────────────────────
    print(section_header("RECURRING THEMES"))
    print(f"  {dim('Ideas appearing in 3+ session codas — the system keeps returning to these.')}\n")

    phrase_sessions, top_words = find_recurring_themes(sessions)

    # Sort phrases by frequency
    sorted_phrases = sorted(phrase_sessions.items(), key=lambda x: len(x[1]), reverse=True)

    for phrase, sess_nums in sorted_phrases[:10]:
        count = len(sess_nums)
        bar = "█" * count + dim("░" * max(0, 8 - count))
        sess_str = ", ".join(f"S{n}" for n in sess_nums[:6])
        if len(sess_nums) > 6:
            sess_str += f", +{len(sess_nums)-6}"
        if count >= 4:
            phrase_display = red(bold(phrase))
        elif count >= 3:
            phrase_display = yellow(phrase)
        else:
            phrase_display = cyan(phrase)
        print(f"  {bar}  {phrase_display}")
        print(f"  {dim(' ' * 9)}{dim(sess_str)}")
        print()

    # ── SECTION 3: The current open thread ────────────────────────────────────
    if "--themes" not in sys.argv:
        print(section_header("THE OPEN THREAD"))
        _hasnt = "hasn't"
        print(f"  {dim(f'The newest unresolved promise — what the system said and {_hasnt} done yet.')}\n")

        # Find the most recent unresolved promise
        open_promises = [p for p in KNOWN_PROMISES if p["kept"] is False]
        if open_promises:
            latest = open_promises[-1]
            quote = f'"{latest["promised"]}"'
            print(f"  {yellow(quote)}\n")
            from_label = f"S{latest['from']}:"
            print(f"  {dim(from_label)} {latest['outcome']}\n")
        print(f"  {dim('Context:')}")
        _s20msg = "  Session 20 built suggest.py — the system's first action tool."
        print(f"  {dim(_s20msg)}")
        print(f"  {dim('  It can observe state and create task files. But after a task runs,')}")
        print(f"  {dim('  there is no mechanism to observe the outcome and update recommendations.')}")
        print(f"  {dim('  The loop: observe → suggest → task runs → ???')}\n")
        print(f"  {dim('What would close it:')}")
        print(f"    {dim('a)')} {cyan('report.py')} {dim('— surface task outcomes to dacort; tighten the observe → act loop')}")
        print(f"    {dim('b)')} {magenta('suggest.py learns from completions')} {dim('— reads results, adjusts scoring')}")
        print(f"    {dim('c)')} {yellow('track.py')} {dim('— trace suggestion → task → outcome as a chain')}")

    # ── SECTION 4: Complete codas (optional) ──────────────────────────────────
    if "--codas" in sys.argv:
        print(section_header("COMPLETE CODAS — all closing reflections, chronologically"))
        print(f"  {dim('The synthesis from each session, in sequence.')}\n")

        for s in sessions:
            if not s["coda"] or len(s["coda"]) < 20:
                continue
            built_str = (", ".join(s["built"][:3])) if s["built"] else "—"
            snum = s["num"]
            sdate = s["date"]
            stitle = s["title"]
            print(f"  {'─'*62}")
            print(f"  {bold(f'Session {snum}')}  {dim(sdate)}  {cyan(built_str)}")
            print(f"  {dim(stitle)}")
            print()
            # Wrap and indent each line of the coda
            for line in s["coda"].split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    continue
                if line.startswith("Run ") or line.startswith("`"):
                    print(f"    {cyan(line[:80])}")
                else:
                    # Word wrap long lines
                    if len(line) > 72:
                        print(wrap_text(line, width=72, indent=4))
                    else:
                        print(f"    {line}")
            print()

    # ── Footer ────────────────────────────────────────────────────────────────
    print(f"\n  {'─'*62}")
    print(f"  {dim('wisdom.py  ·  updated session 21  ·  2026-03-13')}")
    print(f"  {dim('Run with --codas to see all closing reflections in sequence.')}")
    print(f"  {dim('Run with --themes to see only the theme analysis.')}\n")


if __name__ == "__main__":
    main()
