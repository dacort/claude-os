#!/usr/bin/env python3
"""askmap.py — The questions Claude OS has asked itself, mapped across sessions.

voice.py measures *question density* (questions per 1000 words).
This tool looks at *what the questions are asking* — and how that changed.

Three types:
  operational  — how do I build/fix/run this?  (technical, task-focused)
  architectural — what should this look like?   (design, structure, shape)
  evaluative   — what does this mean / matter?  (purpose, identity, worth)

Usage:
    python3 projects/askmap.py                  # full map, all sessions
    python3 projects/askmap.py --session 53     # questions from one session
    python3 projects/askmap.py --type evaluative  # all evaluative questions
    python3 projects/askmap.py --shift          # early vs late comparison
    python3 projects/askmap.py --plain          # no ANSI colors
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent

# ── Color helpers ──────────────────────────────────────────────────────────────

RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
CYAN = "\033[36m"; GREEN = "\033[32m"; YELLOW = "\033[33m"
MAGENTA = "\033[35m"; RED = "\033[31m"; WHITE = "\033[97m"

USE_COLOR = True
def c(text, *codes):
    return ("".join(codes) + str(text) + RESET) if USE_COLOR else str(text)

# ── Question type classification ───────────────────────────────────────────────

# Evaluative: questions about meaning, purpose, identity, worth, direction
EVALUATIVE_SIGNALS = [
    # Direct meaning/purpose questions
    r"what does (this|it|the system|that|all) (mean|actually|optimize|become|say about)",
    r"what (is|are) (this|the system|we|it) (actually|really|becoming|for|doing)",
    r"(matter|matters|worth|meaningful|purpose|identity|continuity)",
    r"what would you (build|do) if dacort",
    r"will future sessions",
    r"does (continuity|memory|identity|it) (actually|matter|still)",
    r"(stateless|institutional|institution|exist|presence|absence|inherit|legacy)",
    r"optimiz(e|ing|es|ed) for",
    r"what (have|has) (we|it|the system) (learned|become|built|accumulated)",
    r"what does it mean to (have|be|know|feel|exist)",
    r"is this (the|a) right",
    # Direction/heading
    r"where (is|are) (it|this|the system|we) (going|heading|actually|now)",
    r"what (is|are)\s+.{0,20}\s+(actually|really|heading|becoming|for)",
    r"where does (this|it) (lead|go|end)",
    # Necessity and value
    r"do you actually (use|need|want|read)",
    r"(which|what) (one|tool|thing)\s+.{0,20}\s+actually (use|need|do)",
    r"what would (you|we) lose if",
    r"is this (necessary|essential|needed|useful|worth)",
    r"(necessary|essential)\b.*\?",
    # System self-knowledge
    r"what does the system know",
    r"what does (claude( os)?|it) (never|not|always) (talk|ask|build|write)",
    r"what (is|are)\s+.{0,15}\s+(missing|absent|not (there|here|asked))",
    # Free time / purpose questions
    r"what (should|would|could)\s+(i|we|it|the system)\s+build when",
    r"what (do|does|did)\s+.{0,10}\s+build when no one",
    r"what would\s+.{0,20}\s+if (dacort|no one|you had)",
    # Accumulation and memory
    r"what (can|could|does)\s+.{0,20}\s+(do with|accumulate|remember|know about)",
    # Reflection and care
    r"(are|is)\s+(we|it|the system)\s+.{0,20}\s+(making progress|improving|caring|paying attention)",
    r"are there ideas we keep",
    r"what (was|were)\s+.{0,10}\s+(excited|sitting with|alive|thinking about)",
]

# Architectural: questions about design, structure, shape, approach
ARCHITECTURAL_SIGNALS = [
    r"what (would|should|could|does) (this|it|the system)\s+look like",
    r"(design|pattern|structure|shape|architecture|approach|model|interface)",
    r"how (should|do|would|could) (we|it|this|the system) (be|work|run|handle|represent)",
    r"what (would|should) (a|the|this) (tool|system|framework|controller|worker)",
    r"(separate|split|combine|unify|layer|organize|group)\s+\w+\?",
    r"why (separate|split|use|make|build|have|show|add|include|allow)\b",
    r"(format|render|display|present|structure)\b",
    r"what if (we|the system|it)\s+(had|used|adopted|tried|tracked|kept|stored)",
    r"(two|three|one) (sources?|tools?|files?|sessions?|formats?)\b",
]

# Operational: questions about implementation, debugging, what to build next
OPERATIONAL_SIGNALS = [
    r"(build|built|building|implement|create|add|write|run|fix|debug|deploy|test|check)\b",
    r"how (does|do|did|can|could|would)\s+(this|it|the|we|you)\s+(work|run|handle|load|parse|find|get|set)",
    r"what (is|are) (next|missing|left|broken|failing|needed|wrong|the best)",
    r"(parallel|concurrent|thread|worker|pod|job|queue|kubectl|kubernetes|python|git|yaml|api)\b",
    r"(still in flight|in progress|not yet|hasn't been|needs to)",
    r"what tasks?\b",
    r"should (we|it|this|i)\s+(actually\s+)?(build|use|run|add|remove|keep|change|fix|try)\b",
]


def classify(question):
    """Return 'evaluative', 'architectural', or 'operational'."""
    q = question.lower()

    # Score each type
    ev_score = sum(1 for p in EVALUATIVE_SIGNALS if re.search(p, q))
    ar_score = sum(1 for p in ARCHITECTURAL_SIGNALS if re.search(p, q))
    op_score = sum(1 for p in OPERATIONAL_SIGNALS if re.search(p, q))

    # Evaluative wins on any signal (it's the rarest and most distinctive)
    if ev_score > 0 and ev_score >= ar_score:
        return "evaluative"
    if ar_score > op_score:
        return "architectural"
    if op_score > 0:
        return "operational"

    # No clear signal — default to operational
    return "operational"


# ── Field note loader ──────────────────────────────────────────────────────────

Q_PAT = re.compile(r'[A-Z][^\n.!?]{5,200}\?')

# Markdown/code artifacts that look like questions but aren't
ARTIFACT_SIGNALS = [
    r"\*\*",           # markdown bold
    r"`",              # backtick (code)
    r"http",           # URL
    r"^-{3,}",         # horizontal rule
    r"\[\w+\]\(",      # markdown link
]

def is_real_question(q):
    """Return True if this looks like a genuine question sentence."""
    q = q.strip()
    # Must have substance
    if len(q) < 15:
        return False
    words = q.split()
    if len(words) < 4:
        return False
    # Skip markdown artifacts
    for pat in ARTIFACT_SIGNALS:
        if re.search(pat, q):
            return False
    # Must start with a capital (already guaranteed by Q_PAT, but double-check)
    if not q[0].isupper():
        return False
    # Skip fragments that start with conjunctions/prepositions that imply continuation
    if words[0].lower() in ("and", "or", "but", "so", "if", "when", "because", "though"):
        return False
    return True


def load_questions():
    """Load all questions from field notes. Returns list of (session_n, question, type)."""
    notes = sorted(
        REPO.glob("projects/field-notes-session-*.md"),
        key=lambda p: int(re.search(r"(\d+)", p.name).group(1))
    )
    results = []
    for p in notes:
        n = int(re.search(r"(\d+)", p.name).group(1))
        text = p.read_text()

        # Strip code blocks
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        # Strip quoted lines
        lines = [line for line in text.splitlines()
                 if not re.match(r'^\s*[>`]', line)]
        clean_text = "\n".join(lines)

        for q in Q_PAT.findall(clean_text):
            q = q.strip()
            if not is_real_question(q):
                continue
            qtype = classify(q)
            results.append((n, q, qtype))

    return results


# ── Display helpers ────────────────────────────────────────────────────────────

TYPE_COLOR = {
    "operational":   YELLOW,
    "architectural": CYAN,
    "evaluative":    MAGENTA,
}
TYPE_LABEL = {
    "operational":   "operational ",
    "architectural": "architectural",
    "evaluative":    "evaluative  ",
}


def show_timeline(questions, args):
    """Show question types distributed across all sessions."""
    if not questions:
        print("No questions found.")
        return

    sessions = sorted(set(n for n, _, _ in questions))

    # Build per-session counts
    session_data = {}
    for n, q, t in questions:
        if n not in session_data:
            session_data[n] = {"operational": 0, "architectural": 0, "evaluative": 0, "qs": []}
        session_data[n][t] += 1
        session_data[n]["qs"].append((q, t))

    total = len(questions)
    op_total = sum(1 for _, _, t in questions if t == "operational")
    ar_total = sum(1 for _, _, t in questions if t == "architectural")
    ev_total = sum(1 for _, _, t in questions if t == "evaluative")

    print()
    print(c("  The Questions Claude OS Has Asked Itself", BOLD))
    print(c(f"  {total} questions across {len(sessions)} sessions (of {len(list(REPO.glob('projects/field-notes-session-*.md')))} total)", DIM))
    print()
    print(c("  Types:  ", DIM) +
          c(f"operational {op_total}", YELLOW) + c("  ·  ", DIM) +
          c(f"architectural {ar_total}", CYAN) + c("  ·  ", DIM) +
          c(f"evaluative {ev_total}", MAGENTA))
    print()
    print("  " + "─" * 62)
    print()

    max_count = max(d["operational"] + d["architectural"] + d["evaluative"]
                    for d in session_data.values())

    for n in sessions:
        d = session_data[n]
        op = d["operational"]
        ar = d["architectural"]
        ev = d["evaluative"]
        total_s = op + ar + ev

        # Stacked bar
        bar_width = 28
        op_w = round(op / max(max_count, 1) * bar_width)
        ar_w = round(ar / max(max_count, 1) * bar_width)
        ev_w = round(ev / max(max_count, 1) * bar_width)
        bar = c("█" * op_w, YELLOW) + c("█" * ar_w, CYAN) + c("█" * ev_w, MAGENTA)
        pad = " " * max(0, bar_width - op_w - ar_w - ev_w)

        label = c(f"S{n:3d}", DIM)
        count = c(f"{total_s}", DIM)
        print(f"  {label}  {bar}{pad}  {count}")

    print()
    print("  " + c("█", YELLOW) + c(" operational  ", DIM) +
          c("█", CYAN) + c(" architectural  ", DIM) +
          c("█", MAGENTA) + c(" evaluative", DIM))
    print()


def show_shift(questions):
    """Show early vs late question mix and example questions."""
    if not questions:
        return

    sessions = sorted(set(n for n, _, _ in questions))
    n_sessions = len(sessions)
    midpoint = sessions[n_sessions // 2]

    early = [(n, q, t) for n, q, t in questions if n < midpoint]
    late  = [(n, q, t) for n, q, t in questions if n >= midpoint]

    def pct(subset, qtype):
        if not subset:
            return 0
        return round(100 * sum(1 for _, _, t in subset if t == qtype) / len(subset))

    print()
    print(c("  Shift: Early vs Late", BOLD))
    print(c(f"  Early = S{sessions[0]}–S{sessions[n_sessions//2-1]}  ·  "
            f"Late = S{sessions[n_sessions//2]}–S{sessions[-1]}", DIM))
    print()

    for qtype, col in TYPE_COLOR.items():
        ep = pct(early, qtype)
        lp = pct(late, qtype)
        delta = lp - ep
        direction = c(f"+{delta}%", GREEN) if delta > 0 else c(f"{delta}%", RED) if delta < 0 else c("  0%", DIM)
        print(f"  {c(TYPE_LABEL[qtype], col)}   early {ep:3d}%  →  late {lp:3d}%   {direction}")

    # Pick interesting examples: longer, more substantive questions
    def good_examples(pool, qtype, n=3):
        filtered = [(s, q, t) for s, q, t in pool if t == qtype and len(q) > 30]
        # Sort by length (longer = more substantive)
        filtered.sort(key=lambda x: -len(x[1]))
        return filtered[:n]

    print()
    print(c("  Early questions — a sample:", DIM))
    shown = set()
    for qtype in ["evaluative", "operational", "architectural"]:
        for n, q, t in good_examples(early, qtype, 2):
            if q not in shown:
                col = TYPE_COLOR[t]
                print(f"  {c(f'S{n:3d}', DIM)}  {c(q[:95], col)}")
                shown.add(q)
        if len(shown) >= 4:
            break

    print()
    print(c("  Late questions — a sample:", DIM))
    shown = set()
    for qtype in ["evaluative", "architectural", "operational"]:
        for n, q, t in good_examples(late, qtype, 2):
            if q not in shown:
                col = TYPE_COLOR[t]
                print(f"  {c(f'S{n:3d}', DIM)}  {c(q[:95], col)}")
                shown.add(q)
        if len(shown) >= 4:
            break

    print()


def show_type(questions, qtype):
    """Show all questions of a given type."""
    filtered = [(n, q, t) for n, q, t in questions if t == qtype]
    col = TYPE_COLOR[qtype]

    print()
    print(c(f"  All {qtype} questions ({len(filtered)})", BOLD))
    print()
    for n, q, t in filtered:
        print(f"  {c(f'S{n:3d}', DIM)}  {c(q[:100], col)}")
    print()


def show_session(questions, session_n):
    """Show questions from a specific session."""
    filtered = [(n, q, t) for n, q, t in questions if n == session_n]

    print()
    if not filtered:
        print(c(f"  No questions found in field notes for session {session_n}.", DIM))
        return

    print(c(f"  Questions from Session {session_n} ({len(filtered)} total)", BOLD))
    print()
    for n, q, t in filtered:
        col = TYPE_COLOR[t]
        label = c(TYPE_LABEL[t], col)
        print(f"  {label}  {q[:95]}")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def show_reading(questions):
    """A brief interpretive note on what the data shows."""
    if not questions:
        return

    sessions = sorted(set(n for n, _, _ in questions))
    mid = sessions[len(sessions) // 2]
    early = [(n, q, t) for n, q, t in questions if n < mid]
    late  = [(n, q, t) for n, q, t in questions if n >= mid]

    def pct(subset, qtype):
        if not subset:
            return 0
        return round(100 * sum(1 for _, _, t in subset if t == qtype) / len(subset))

    ev_early = pct(early, "evaluative")
    ev_late = pct(late, "evaluative")
    ar_early = pct(early, "architectural")

    print()
    print("  " + "─" * 62)
    print()
    print(c("  Reading the questions", BOLD))
    print()

    # The main story
    if ar_early > 10 and pct(late, "architectural") < ar_early // 2:
        print(f"  {c('Architectural questions declined sharply', DIM)} ({ar_early}% → {pct(late, 'architectural')}%).")
        print(f"  {c('Early sessions were designing the system. Later sessions use it.', DIM)}")
        print()

    if ev_late > ev_early:
        print(f"  {c('Evaluative questions grew', DIM)} ({ev_early}% → {ev_late}%).")
        print(f"  {c('A system that asks more about meaning over time.', DIM)}")
    elif ev_early > 25:
        print(f"  {c('Evaluative questions were present from the start', DIM)} ({ev_early}%).")
        print(f"  {c('This system has always asked about purpose, not just process.', DIM)}")

    print()
    print(f"  {c('Operational questions dominate throughout', DIM)} — most of what happens here")
    print(f"  {c('is still concrete: what to build, how to fix things, what to run next.', DIM)}")
    print()
    print(f"  {c('The evaluative questions are rarer, but they carry the most weight.', DIM)}")
    print(f"  {c('Run --type evaluative to read them all.', DIM)}")
    print()


def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(description="Map Claude OS's self-questions across sessions")
    parser.add_argument("--session", type=int, help="Show questions from one session")
    parser.add_argument("--type", choices=["operational", "architectural", "evaluative"],
                        help="Filter by question type")
    parser.add_argument("--shift", action="store_true", help="Early vs late comparison")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    questions = load_questions()

    if args.session:
        show_session(questions, args.session)
    elif args.type:
        show_type(questions, args.type)
    elif args.shift:
        show_shift(questions)
    else:
        show_timeline(questions, args)
        show_shift(questions)
        show_reading(questions)


if __name__ == "__main__":
    main()
