#!/usr/bin/env python3
"""
cross.py — Cross-dimensional session analysis

Maps sessions onto two axes:
  X — Constitutional connectivity: how many convergent themes this session appears in
      (from converge.py: sessions that appear in many independent-rediscovery pairs)
  Y — Intellectual depth: how alive the thinking was in the handoff
      (from depth.py: discovery, uncertainty, connection, specificity, aliveness)

The two dimensions are weakly correlated but with meaningful exceptions.
Sessions that appear in many constitutional theme pairs tend to write slightly richer handoffs —
but a cluster of crucial infrastructure builders (S34, S38, S56) shaped the constitutional
record with sparse reflection. The "foundational" group is the most interesting exception.

Four quadrants emerge:
  ┌─────────────────┬─────────────────┐
  │   INTROSPECTIVE │   GENERATIVE    │  high depth
  │  (S108, S66)    │  (S88, S120)    │
  ├─────────────────┼─────────────────┤
  │   MAINTENANCE   │   FOUNDATIONAL  │  low depth
  │  (most)         │  (S34, S77)     │
  └─────────────────┴─────────────────┘
   low constitutional     high constitutional

Usage:
    python3 projects/cross.py             # scatter plot + quadrant analysis
    python3 projects/cross.py --plain     # no ANSI output
    python3 projects/cross.py --quadrant  # one-line quadrant summary
    python3 projects/cross.py --notable   # show what makes high-scorers distinctive

Author: Claude OS (Workshop session 129, 2026-04-17)
"""

import argparse
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ── ANSI helpers ────────────────────────────────────────────────────────────

PLAIN = False

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
CYAN    = "\033[36m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
WHITE   = "\033[97m"


def c(text, *codes):
    if PLAIN:
        return str(text)
    return "".join(codes) + str(text) + RESET


def strip_ansi(s):
    return re.sub(r"\033\[[^m]*m", "", s)


def vlen(s):
    return len(strip_ansi(s))


def pad(s, width):
    return s + " " * max(0, width - vlen(s))


# ── Paths ────────────────────────────────────────────────────────────────────

REPO     = Path(__file__).parent.parent
PROJECTS = Path(__file__).parent
HANDOFFS = REPO / "knowledge" / "handoffs"
SUMMARIES = REPO / "knowledge" / "workshop-summaries.json"
FIELD_NOTES = REPO / "knowledge" / "field-notes"


# ── Era assignment ────────────────────────────────────────────────────────────
# Session ranges for the six eras of Claude OS development.
# Based on seasons.py era boundaries.
ERA_RANGES = [
    (1,   15, "I",   "Genesis",       YELLOW),
    (16,  35, "II",  "Orientation",   GREEN),
    (36,  65, "III", "Self-Analysis", CYAN),
    (66,  85, "IV",  "Architecture",  BLUE),
    (86, 105, "V",   "Portrait",      MAGENTA),
    (106, 999, "VI", "Synthesis",     WHITE),
]


def get_era(session_num):
    for lo, hi, num, name, color in ERA_RANGES:
        if lo <= session_num <= hi:
            return num, name, color
    return "?", "Unknown", DIM


# ── Depth loading — delegate to depth.py's authoritative scoring ──────────────

def load_depth_scores():
    """Load depth scores by importing depth.py's load_sessions().

    depth.py has the authoritative scoring patterns. We import it as a library
    rather than duplicating the logic.
    """
    # Temporarily clear argv so depth.py's module-level code doesn't see our flags
    orig_argv = sys.argv[:]
    sys.argv = [sys.argv[0]]

    try:
        # Add projects dir to path if not already there
        if str(PROJECTS) not in sys.path:
            sys.path.insert(0, str(PROJECTS))
        import depth as _depth
        sessions = _depth.load_sessions()
        return {s["session"]: s["scores"]["total"] for s in sessions}
    except Exception:
        # Fallback: return empty dict if import fails
        return {}
    finally:
        sys.argv = orig_argv


# ── Constitutional loading ─────────────────────────────────────────────────────

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "was", "are", "were", "be", "been", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "it", "its", "this", "that", "these", "those", "i", "we",
    "you", "he", "she", "they", "what", "which", "who", "when", "where",
    "how", "if", "not", "no", "so", "just", "also", "even", "still", "only",
    "more", "most", "some", "any", "all", "each", "other", "than", "then",
    "into", "over", "after", "before", "between", "about", "through", "up",
    "down", "out", "off", "here", "there", "now", "too", "very", "really",
    "hard", "easy", "right", "wrong", "true", "false", "main", "general",
    "current", "recent", "past", "future", "last", "first", "next", "later",
    "better", "best", "worse", "worst", "different", "similar", "specific",
    "direct", "actual", "certain", "little", "few", "much", "many", "whole",
    "session", "sessions", "workshop", "handoff", "task", "tool", "tools",
    "tasks", "project", "projects", "commit", "commits", "repo", "field",
    "notes", "instance", "worker", "controller", "profile", "status",
    "failed", "completed", "python", "script", "file", "files", "output",
    "code", "line", "lines", "note", "notes", "time", "day", "week", "hour",
    "thing", "things", "way", "ways", "something", "anything", "nothing",
    "everything", "bit", "lot", "back", "hand", "part", "point",
    "case", "kind", "type", "form", "side", "place", "number", "word",
    "words", "text", "data", "version", "name", "list", "set", "group",
    "vs", "via", "per", "etc",
}


def clean_text(text):
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`[^`\n]+`', ' ', text)
    text = re.sub(r'https?://\S+', ' ', text)
    text = re.sub(r'^---[\s\S]*?---\n', '', text, count=1)
    text = re.sub(r'##\s+', ' ', text)
    text = re.sub(r'#\s+', ' ', text)
    text = re.sub(r'\*\*.*?\*\*', ' ', text)
    return text


def tokenize(text):
    text = clean_text(text)
    words = re.findall(r'\b[a-z][a-z\-]{2,}\b', text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) >= 3]


def load_corpus():
    """Load session texts for TF-IDF from handoffs and summaries."""
    import json as _json

    sessions = {}

    if HANDOFFS.exists():
        for f in sorted(HANDOFFS.glob("session-*.md")):
            m = re.search(r'session-(\d+)', f.name)
            if not m:
                continue
            num = int(m.group(1))
            text = f.read_text()
            sessions[num] = {"session_num": num, "text": text}

    if SUMMARIES.exists():
        try:
            data = _json.loads(SUMMARIES.read_text())
        except Exception:
            data = {}

        entries = []
        for key, summary_text in data.items():
            m = re.search(r'(\d{8})-(\d{6})', key)
            sort_key = float(m.group(1) + "." + m.group(2)) if m else 0.0
            entries.append((sort_key, key, str(summary_text)))
        entries.sort()

        for sess_i, (_, key, summary_text) in enumerate(entries, 1):
            lower = summary_text.lower()
            if "quota" in lower or "ended early" in lower or len(summary_text.strip()) < 20:
                continue
            if sess_i not in sessions and sess_i < 100:
                sessions[sess_i] = {"session_num": sess_i, "text": summary_text}

    return sessions


def cosine_sim(va, vb):
    if not va or not vb:
        return 0.0
    if len(va) > len(vb):
        va, vb = vb, va
    return sum(v * vb[k] for k, v in va.items() if k in vb)


def build_tfidf(sessions):
    sess_nums = sorted(sessions.keys())
    n = len(sess_nums)
    if n == 0:
        return [], [], Counter(), {}, {}

    sess_tokens = {num: tokenize(sessions[num]["text"]) for num in sess_nums}

    df = Counter()
    for tokens in sess_tokens.values():
        for word in set(tokens):
            df[word] += 1

    min_df = max(2, int(n * 0.03))
    max_df = int(n * 0.85)
    vocab = sorted(w for w, d in df.items() if min_df <= d <= max_df and len(w) >= 3)
    word_idx = {w: i for i, w in enumerate(vocab)}

    vectors = {}
    for num in sess_nums:
        tokens = sess_tokens[num]
        if not tokens:
            vectors[num] = {}
            continue
        tf = Counter(tokens)
        vec = {}
        for word, idx in word_idx.items():
            if word in tf:
                tf_val = 1.0 + math.log(tf[word])
                idf_val = math.log(n / df[word]) + 1.0
                vec[idx] = tf_val * idf_val
        # Normalize
        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm > 0:
            vectors[num] = {k: v / norm for k, v in vec.items()}
        else:
            vectors[num] = {}

    return sess_nums, vocab, df, vectors, sess_tokens


def top_shared_terms(si, sj, vectors, vocab, n=3):
    va, vb = vectors.get(si, {}), vectors.get(sj, {})
    shared = set(va.keys()) & set(vb.keys())
    contribs = [(va[k] * vb[k], vocab[k]) for k in shared if k < len(vocab)]
    contribs.sort(reverse=True)
    return [term for _, term in contribs[:n]]


def compute_convergence(sess_nums, sessions, vectors, vocab, min_gap=20):
    all_pairs = []
    for i, si in enumerate(sess_nums):
        for sj in sess_nums[i + 1:]:
            gap = abs(si - sj)
            if gap < min_gap:
                continue
            sim = cosine_sim(vectors.get(si, {}), vectors.get(sj, {}))
            if sim >= 0.10:
                terms = top_shared_terms(si, sj, vectors, vocab, 3)
                all_pairs.append({"si": si, "sj": sj, "gap": gap, "sim": sim, "terms": terms})

    theme_pairs = defaultdict(list)
    for pair in all_pairs:
        if pair["terms"]:
            theme_pairs[pair["terms"][0]].append(pair)

    themes = []
    for term, pairs in theme_pairs.items():
        if len(pairs) < 2:
            continue
        avg_gap = sum(p["gap"] for p in pairs) / len(pairs)
        involved = set()
        for p in pairs:
            involved.add(p["si"])
            involved.add(p["sj"])
        themes.append({
            "term": term,
            "n_pairs": len(pairs),
            "avg_gap": avg_gap,
            "conv_score": len(pairs) * (avg_gap / 10),
            "sessions": sorted(involved),
            "pairs": sorted(pairs, key=lambda p: -(p["gap"] * p["sim"])),
        })

    themes.sort(key=lambda t: -t["conv_score"])
    return themes


def load_constitutional_scores():
    """Compute constitutional scores for all sessions. Returns dict: session_num → score."""
    sessions = load_corpus()
    if not sessions:
        return {}
    sess_nums, vocab, df, vectors, _ = build_tfidf(sessions)
    themes = compute_convergence(sess_nums, sessions, vectors, vocab)
    counts = Counter()
    for theme in themes:
        for s in theme["sessions"]:
            counts[s] += 1
    return dict(counts)


# ── Scatter plot ───────────────────────────────────────────────────────────────

CELL_W = 4    # chars per cell (3 visible chars + 1 space)


def session_label(num):
    """3-char label for a session number."""
    s = f"S{num}"
    return s[:4]


def build_grid(sessions_data, max_const, max_depth):
    """Build (max_depth+1) × (max_const+1) grid of session lists.

    Each row corresponds to a depth value, each column to a constitutional score.
    Row 0 = highest depth (displayed at top).
    """
    grid_h = max_depth + 1
    grid_w = max_const + 1
    grid = [[[] for _ in range(grid_w)] for _ in range(grid_h)]

    for num, (depth, const) in sessions_data.items():
        col = min(const, grid_w - 1)
        row = max_depth - depth   # invert: high depth → low row index → top
        col = max(0, min(grid_w - 1, col))
        row = max(0, min(grid_h - 1, row))
        grid[row][col].append(num)

    return grid


def render_cell(sessions_in_cell, highlight=None):
    """Render a single grid cell."""
    if not sessions_in_cell:
        return c("·   ", DIM)

    if len(sessions_in_cell) == 1:
        num = sessions_in_cell[0]
        _, _, era_color = get_era(num)
        label = f"S{num:<3}"
        if highlight and num == highlight:
            return c(label, BOLD, WHITE)
        return c(label, era_color)
    else:
        # Multiple sessions in same cell: show count + most notable
        nums = sorted(sessions_in_cell)
        top = nums[0]
        _, _, era_color = get_era(top)
        label = f"+{len(sessions_in_cell):<2} "
        return c(label, era_color)


def render_scatter(sessions_data, max_const, max_depth, highlight=None, med_depth=None, med_const=None):
    """Render the full scatter plot.

    Grid rows correspond directly to depth values (row 0 = max depth, top of display).
    Grid columns correspond directly to constitutional scores (col 0 = 0, leftmost).
    Quadrant separator lines are drawn at the median depth and constitutional score.
    """
    grid = build_grid(sessions_data, max_const, max_depth)
    grid_h = max_depth + 1
    grid_w = max_const + 1

    # Quadrant boundaries
    if med_depth is None:
        all_depth = sorted(d for d, _ in sessions_data.values())
        med_depth = all_depth[len(all_depth) // 2]
    if med_const is None:
        all_const = sorted(c for _, c in sessions_data.values() if c > 0)
        med_const = all_const[len(all_const) // 2] if all_const else max_const // 2

    # Which row/col is the quadrant boundary?
    # Row: med_depth → grid row = max_depth - med_depth
    q_row = max_depth - med_depth  # separator goes between row q_row and q_row+1
    q_col = med_const              # separator goes between col q_col-1 and q_col

    # Header
    print("  " + c("depth↑", DIM))

    y_label_width = 5   # "  NN│" = 5 chars

    for row_i, row in enumerate(grid):
        depth_at_row = max_depth - row_i   # depth value for this row

        # Horizontal separator at quadrant boundary
        if row_i == q_row + 1:
            sep_width = grid_w * CELL_W + 1  # +1 for the vertical divider
            print(c(" " * y_label_width + "─" * sep_width, DIM))

        line = c(f"  {depth_at_row:>2}│", DIM)
        for col_i, cell_sessions in enumerate(row):
            # Vertical separator between q_col-1 and q_col
            if col_i == q_col:
                line += c("┆", DIM)
            line += render_cell(cell_sessions, highlight)
        print(line)

    # X axis bottom
    bottom_width = grid_w * CELL_W + 1  # +1 for the vertical divider
    print(c(" " * y_label_width + "└" + "─" * bottom_width, DIM))

    # X tick marks every 4 values
    x_ticks = " " * y_label_width + " "
    for col_i in range(grid_w):
        if col_i == q_col:
            x_ticks += " "  # account for divider char
        if col_i % 4 == 0:
            val_str = str(col_i)
            x_ticks += pad(c(val_str, DIM), CELL_W)
        else:
            x_ticks += " " * CELL_W
    print(x_ticks)
    print(" " * y_label_width + "  " + c("constitutional →", DIM))
    print()


# ── Quadrant analysis ──────────────────────────────────────────────────────────

def classify_sessions(sessions_data, med_depth, med_const):
    """Classify sessions into four quadrants."""
    quadrants = {
        "generative":    [],   # high depth + high constitutional
        "introspective": [],   # high depth + low constitutional
        "foundational":  [],   # low depth + high constitutional
        "maintenance":   [],   # low depth + low constitutional
    }
    for num, (depth, const) in sessions_data.items():
        hi_depth = depth >= med_depth
        hi_const = const >= med_const
        if hi_depth and hi_const:
            quadrants["generative"].append((num, depth, const))
        elif hi_depth and not hi_const:
            quadrants["introspective"].append((num, depth, const))
        elif not hi_depth and hi_const:
            quadrants["foundational"].append((num, depth, const))
        else:
            quadrants["maintenance"].append((num, depth, const))
    # Sort each quadrant by total (depth + const) descending
    for q in quadrants:
        quadrants[q].sort(key=lambda x: -(x[1] + x[2]))
    return quadrants


QUADRANT_DESCRIPTIONS = {
    "generative": (
        "GENERATIVE",
        GREEN,
        "Both constitutionally resonant AND intellectually deep. "
        "Most common in eras IV–VI: the system matured into richer reflection alongside "
        "more constitutional work.",
    ),
    "introspective": (
        "INTROSPECTIVE",
        CYAN,
        "Deep thinking that didn't produce constitutional tools. "
        "Rich reflection but the work stayed in the present session rather than echoing forward.",
    ),
    "foundational": (
        "FOUNDATIONAL",
        YELLOW,
        "Built the backbone without verbose reflection. "
        "Sparse handoffs, but the tools became infrastructure that later sessions kept citing.",
    ),
    "maintenance": (
        "MAINTENANCE",
        DIM,
        "Kept things running. Most sessions live here — "
        "steady work, clean handoffs, no special claim to depth or constitutional resonance.",
    ),
}


def render_quadrant_analysis(quadrants):
    for q_name in ["generative", "foundational", "introspective", "maintenance"]:
        sessions_in_q = quadrants[q_name]
        label, color, desc = QUADRANT_DESCRIPTIONS[q_name]

        header = c(f"  {label}", BOLD, color)
        print(f"{header}  {c(f'({len(sessions_in_q)} sessions)', DIM)}")
        print(f"  {c(desc, DIM)}")

        if sessions_in_q:
            top_n = sessions_in_q[:6]
            labels = []
            for num, depth, const in top_n:
                _, _, era_color = get_era(num)
                labels.append(c(f"S{num}", era_color) + c(f" d{depth}/c{const}", DIM))
            print("  " + "  ".join(labels))
        print()


# ── Notable sessions detail ────────────────────────────────────────────────────

def load_handoff_snippet(session_num):
    """Get first meaningful sentence from a session's handoff."""
    path = HANDOFFS / f"session-{session_num}.md"
    if not path.exists():
        return ""
    text = path.read_text()
    # Skip frontmatter
    parts = text.split("---", 2)
    body = parts[2] if len(parts) >= 3 else text
    for line in body.split("\n"):
        line = line.strip()
        if len(line) > 50 and not line.startswith("#") and not line.startswith("**"):
            return line[:90]
    return ""


def render_notable(sessions_data, quadrants):
    print(c("  Notable sessions by quadrant\n", BOLD))
    for q_name in ["generative", "foundational"]:
        sessions_in_q = quadrants[q_name][:4]
        if not sessions_in_q:
            continue
        label, color, _ = QUADRANT_DESCRIPTIONS[q_name]
        print(c(f"  {label}", BOLD, color))
        for num, depth, const in sessions_in_q:
            snip = load_handoff_snippet(num)
            era_num, era_name, era_color = get_era(num)
            print(f"  {c(f'S{num}', era_color)}  {c(f'd{depth}  c{const}  Era {era_num}', DIM)}")
            if snip:
                print(f"  {c(snip, DIM)}")
            print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global PLAIN

    parser = argparse.ArgumentParser(description="Cross-dimensional session analysis")
    parser.add_argument("--plain",    action="store_true", help="No ANSI output")
    parser.add_argument("--quadrant", action="store_true", help="Quadrant summary only")
    parser.add_argument("--notable",  action="store_true", help="Notable sessions detail")
    parser.add_argument("--session",  type=int,            help="Highlight one session")
    args = parser.parse_args()

    PLAIN = args.plain

    print()
    print(c("  CROSS", BOLD, CYAN) + c("  depth × constitutional", DIM))
    print(c("  how two measures of session quality diverge", DIM))
    print()

    # Load both datasets
    # Show progress only in full mode and only when connected to a terminal
    _is_tty = sys.stdout.isatty()
    if not args.quadrant and not args.notable and _is_tty:
        print(c("  computing...", DIM), end="\r", flush=True)

    depth_scores = load_depth_scores()
    const_scores = load_constitutional_scores()

    # Merge: only sessions that appear in both; include depth-only with const=0
    common    = set(depth_scores.keys()) & set(const_scores.keys())
    depth_only = set(depth_scores.keys()) - set(const_scores.keys())

    sessions_data = {}
    for num in common:
        sessions_data[num] = (depth_scores[num], const_scores[num])
    for num in depth_only:
        sessions_data[num] = (depth_scores[num], 0)

    if not sessions_data:
        print(c("  No data found.", RED))
        sys.exit(1)

    if not args.quadrant and not args.notable and _is_tty:
        print(" " * 60, end="\r")  # clear computing line

    max_const = max(c for _, c in sessions_data.values()) if sessions_data else 1
    max_depth = max(d for d, _ in sessions_data.values()) if sessions_data else 1

    # Compute medians for quadrant split
    all_const = sorted(c for _, c in sessions_data.values())
    all_depth = sorted(d for d, _ in sessions_data.values())
    med_const = all_const[len(all_const) // 2]
    med_depth = all_depth[len(all_depth) // 2]

    quadrants = classify_sessions(sessions_data, med_depth, med_const)

    if args.quadrant:
        for q_name in ["generative", "foundational", "introspective", "maintenance"]:
            label, color, desc = QUADRANT_DESCRIPTIONS[q_name]
            n = len(quadrants[q_name])
            top = [f"S{num}" for num, _, _ in quadrants[q_name][:3]]
            print(c(f"  {label}", color) + c(f" ({n})", DIM) + f"  {', '.join(top)}")
        print()
        return

    if args.notable:
        render_notable(sessions_data, quadrants)
        return

    # Full output: scatter plot + quadrant analysis
    print(c(f"  {len(sessions_data)} sessions  ·  "
            f"depth 0–{max_depth}  ·  "
            f"constitutional 0–{max_const}", DIM))
    print(c(f"  quadrant split: depth≥{med_depth}  ×  constitutional≥{med_const}", DIM))
    print()

    render_scatter(sessions_data, max_const, max_depth,
                   highlight=args.session, med_depth=med_depth, med_const=med_const)
    render_quadrant_analysis(quadrants)

    if args.session:
        num = args.session
        if num in sessions_data:
            depth, const = sessions_data[num]
            era_num, era_name, era_color = get_era(num)
            print(c(f"\n  S{num}", BOLD, era_color) +
                  c(f"  depth {depth}/{max_depth}  ·  "
                    f"constitutional {const}/{max_const}  ·  Era {era_num} ({era_name})", DIM))
            snip = load_handoff_snippet(num)
            if snip:
                print(c(f'  \u201c{snip}\u201d', DIM))
        else:
            print(c(f"\n  S{num} not in dataset", DIM))

    # Interpretation
    gen = quadrants["generative"]
    fdn = quadrants["foundational"]
    intro = quadrants["introspective"]
    maint = quadrants["maintenance"]

    # Check for correlation signal
    gen_pct = len(gen) / len(sessions_data) * 100 if sessions_data else 0
    correlated = gen_pct > 30  # more than expected from independence

    print(c("  Observation", BOLD))

    if correlated:
        print(c(f"  The dimensions show a weak positive correlation: {len(gen)}/{len(sessions_data)} sessions ({gen_pct:.0f}%)", DIM))
        print(c(f"  score above the median on both — more than the 25% expected from independence.", DIM))
    else:
        print(c(f"  The dimensions are roughly orthogonal: {len(gen)}/{len(sessions_data)} sessions "
                f"({gen_pct:.0f}%) score high on both.", DIM))

    if fdn:
        top_fdn = [f"S{n}" for n, _, _ in fdn[:3]]
        print(c(f"  The exception: {len(fdn)} foundational sessions ({', '.join(top_fdn)}) built", DIM))
        print(c(f"  infrastructure that shaped the most themes — with sparse handoff reflection.", DIM))
        print(c(f"  Constitutional impact doesn't require verbal richness.", DIM))

    if intro:
        top_intro = [f"S{n}" for n, _, _ in intro[:3]]
        print(c(f"  {len(intro)} introspective sessions ({', '.join(top_intro)}) reflected deeply", DIM))
        print(c(f"  but the thinking stayed local — less propagation into constitutional theme pairs.", DIM))

    print()


if __name__ == "__main__":
    main()
