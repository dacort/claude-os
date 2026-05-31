#!/usr/bin/env python3
"""
concordance.py — Classical concordance for the Claude OS corpus.

Borrows the structure of a biblical/classical concordance (KWIC — keyword
in context) and applies it to the Claude OS knowledge base. Given a word,
shows every occurrence in context, its distribution by source type, the
words that cluster around it, and whether the on-X series has analyzed it.

This is the on-X series' method made portable: count appearances, show
contexts, identify registers. The concordance provides the raw material;
the writer does the interpretation.

Structure borrowed from: classical concordance tradition (Strong's, Harvard
Concordance to the Works of Shakespeare, Oxford Shakespeare Concordances).
Format: KWIC (keyword in context) — each occurrence displayed with the
keyword centered, equal context on either side. The standard form of corpus
analysis since the 13th century.

Built: Workshop session 268, 2026-05-31.
Constraint card: "Borrow structure from a non-programming domain."

Usage:
    python3 projects/concordance.py "record"           # full concordance
    python3 projects/concordance.py "record" --brief   # count + distribution
    python3 projects/concordance.py "record" --kwic    # KWIC lines only
    python3 projects/concordance.py "record" --co      # co-occurring words
    python3 projects/concordance.py --top 15           # most frequent uncovered words
    python3 projects/concordance.py "record" -n 8      # 8 words of context (default)
    python3 projects/concordance.py "record" --limit 50  # show up to 50 KWIC lines
    python3 projects/concordance.py "record" --plain   # no ANSI colors
"""

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).parent.parent
FIELD_NOTES = REPO / "knowledge" / "field-notes"
HANDOFFS = REPO / "knowledge" / "handoffs"
KNOWLEDGE = REPO / "knowledge"

# ── ANSI ─────────────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
CYAN    = "\033[36m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
MAGENTA = "\033[35m"
WHITE   = "\033[97m"
BLUE    = "\033[34m"
GRAY    = "\033[90m"

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    prefix = "".join(codes)
    return f"{prefix}{text}{RESET}"

def ansi_len(s):
    """Length of string ignoring ANSI escape codes."""
    return len(re.sub(r"\033\[[^m]*m", "", s))

def pad(s, width, align="left"):
    """Pad string to width, accounting for ANSI codes."""
    visible = ansi_len(s)
    pad_n = max(0, width - visible)
    if align == "right":
        return " " * pad_n + s
    return s + " " * pad_n

def box(lines, width=66):
    """Render lines inside a box. Lines are (content, is_divider) tuples."""
    out = [f"╭{'─' * width}╮"]
    for content, is_div in lines:
        if is_div:
            out.append(f"├{'─' * width}┤")
        else:
            padded = pad(f"  {content}", width)
            out.append(f"│{padded}│")
    out.append(f"╰{'─' * width}╯")
    return "\n".join(out)

def bar_chart(n, total, width=18):
    """Render a filled bar segment."""
    if total == 0:
        return " " * width
    filled = round(n / total * width)
    return c("█" * filled, CYAN) + c(" " * (width - filled), DIM)


# ── Stopwords ─────────────────────────────────────────────────────────────────

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "not", "no", "nor",
    "so", "yet", "both", "either", "each", "more", "most", "other", "some",
    "such", "than", "too", "very", "just", "it", "its", "this", "that",
    "these", "those", "they", "them", "their", "there", "here", "what",
    "which", "who", "whom", "when", "where", "how", "why", "if", "then",
    "because", "as", "while", "although", "though", "i", "me", "my",
    "we", "us", "our", "you", "your", "he", "she", "him", "her", "his",
    "hers", "also", "all", "any", "into", "about", "after", "before",
    "between", "through", "during", "only", "own", "same", "without",
    "against", "across", "behind", "beyond", "since", "within", "along",
    "above", "below", "up", "down", "out", "over", "under", "again",
    "further", "once", "s", "t", "don", "doesn", "hasn", "haven", "won",
    "isn", "aren", "wasn", "weren", "didn", "hadn",
}


# ── Corpus ────────────────────────────────────────────────────────────────────

def load_corpus():
    """Load all corpus files. Returns list of (source_type, path, text)."""
    sources = []
    if FIELD_NOTES.exists():
        for p in sorted(FIELD_NOTES.glob("*.md")):
            try:
                sources.append(("field-note", p, p.read_text(errors="replace")))
            except OSError:
                pass
    if HANDOFFS.exists():
        for p in sorted(HANDOFFS.glob("session-*.md")):
            try:
                sources.append(("handoff", p, p.read_text(errors="replace")))
            except OSError:
                pass
    for p in sorted(KNOWLEDGE.glob("*.md")):
        try:
            sources.append(("knowledge", p, p.read_text(errors="replace")))
        except OSError:
            pass
    return sources


def session_num(path):
    """Extract session number from handoff filename."""
    m = re.search(r"session-(\d+)", path.stem)
    return int(m.group(1)) if m else None


# ── Search ────────────────────────────────────────────────────────────────────

def search_word(word, corpus, context_n=8):
    """
    Find all occurrences of word in corpus.
    Returns list of (source_type, path, pre_words, matched_form, post_words).
    """
    pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
    results = []
    for src_type, path, text in corpus:
        for m in pattern.finditer(text):
            matched = m.group(0)
            before = text[:m.start()]
            after = text[m.end():]
            pre = re.findall(r'\S+', before)[-context_n:]
            post = re.findall(r'\S+', after)[:context_n]
            results.append((src_type, path, pre, matched, post))
    return results


def cooccurrences(results, window=15, target=None):
    """Count words co-occurring with the target within a window."""
    # Expand stopword set to handle common contractions
    extended_stop = STOPWORDS | {
        "it's", "that's", "there's", "they're", "don't", "doesn't",
        "isn't", "aren't", "wasn't", "weren't", "didn't", "hadn't",
        "hasn't", "haven't", "won't", "can't", "couldn't", "wouldn't",
        "shouldn't", "i'm", "i've", "i'll", "i'd", "you've", "you'll",
        "you'd", "he's", "she's", "we're", "we've", "we'll", "we'd",
        "they've", "they'll", "they'd", "let's", "that'll",
    }
    target_norm = target.lower() if target else None

    counts = Counter()
    for _, _, pre, _, post in results:
        context = pre[-window:] + post[:window]
        for w in context:
            # Split on periods first (handles "verse.py" → ["verse", "py"])
            parts = re.split(r"[.!?;:,/\\]", w.lower())
            for part in parts:
                clean = re.sub(r"[^a-z'-]", "", part).strip("'-")
                # Skip stopwords, short words, self-references, contractions, extensions
                if (clean
                        and clean not in extended_stop
                        and len(clean) > 2
                        and clean != target_norm
                        and "'" not in clean
                        and clean not in {"py", "md", "txt", "html", "yaml", "json"}):
                    counts[clean] += 1
    return counts


# ── On-X detection ────────────────────────────────────────────────────────────

def find_on_x_note(word):
    """Return path to on-<word>.md if it exists, else None."""
    if not FIELD_NOTES.exists():
        return None
    norm = word.lower().replace(" ", "-").replace("_", "-")
    # Try date-prefixed and bare forms
    for p in FIELD_NOTES.glob(f"*-on-{norm}.md"):
        return p
    for p in FIELD_NOTES.glob(f"on-{norm}.md"):
        return p
    return None


def note_meta(note_path):
    """Extract (haiku_number, session_number) from on-X note header."""
    if note_path is None:
        return None, None
    text = note_path.read_text(errors="replace")
    hn = re.search(r"Haiku #(\d+)", text, re.IGNORECASE)
    sn = re.search(r"Session (\d+)\.", text)
    return (int(hn.group(1)) if hn else None,
            int(sn.group(1)) if sn else None)


def get_covered_words():
    """Set of words already covered by on-X notes."""
    covered = set()
    if not FIELD_NOTES.exists():
        return covered
    for p in FIELD_NOTES.glob("*-on-*.md"):
        m = re.match(r"\d{4}-\d{2}-\d{2}-on-(.+)\.md", p.name)
        if m:
            covered.add(m.group(1).lower())
    return covered


# ── Top uncovered words ───────────────────────────────────────────────────────

def top_uncovered(corpus, n=15):
    """Most frequent significant words not yet covered by on-X notes."""
    covered = get_covered_words()
    counts = Counter()
    for _, _, text in corpus:
        for w in re.findall(r"\b[a-z][a-z'-]{2,}\b", text.lower()):
            w = w.strip("'-")
            if w and w not in STOPWORDS and w not in covered and len(w) >= 3:
                counts[w] += 1
    # Return filtered top
    filtered = [(w, cnt) for w, cnt in counts.most_common(300)
                if not re.match(r"^\d+$", w) and "'" not in w[:1]]
    return filtered[:n]


# ── Display: summary box ──────────────────────────────────────────────────────

def display_summary(word, results, cooccur, on_x_path):
    W = 64
    total = len(results)
    by_type = Counter(r[0] for r in results)
    sources = len(set(r[1] for r in results))

    lines = []

    # Title
    lines.append((c("CONCORDANCE", BOLD, WHITE), False))
    lines.append((c(f'headword: "{word}"', CYAN), False))

    # On-X status
    if on_x_path:
        hn, sn = note_meta(on_x_path)
        status = f"✦ on-{word}.md"
        if hn:
            status += f"  ·  haiku #{hn}"
        if sn:
            status += f"  ·  session {sn}"
        lines.append((c(status, GREEN), False))
    else:
        lines.append((c("— no on-X note yet", YELLOW), False))

    lines.append(("", True))  # divider

    # Entry count
    lines.append((c(f"{total} appearances  ·  {sources} sources", CYAN), False))
    lines.append(("", False))

    # Distribution by source type
    lines.append((c("BY SOURCE TYPE", DIM), False))
    type_order = [("field-note", "field-notes"), ("handoff", "handoffs"), ("knowledge", "knowledge")]
    for key, label in type_order:
        cnt = by_type.get(key, 0)
        if cnt == 0:
            continue
        pct = int(cnt / total * 100) if total else 0
        b = bar_chart(cnt, total, 14)
        lines.append((f"  {label:<14}  {b}  {cnt:>4}  ({pct}%)", False))

    # Handoff period distribution
    handoff_results = [(p, pre, m, post)
                       for t, p, pre, m, post in results if t == "handoff"]
    if handoff_results:
        lines.append(("", False))
        lines.append((c("HANDOFF FREQUENCY BY PERIOD", DIM), False))
        period_counts = defaultdict(int)
        for path, pre, m, post in handoff_results:
            n = session_num(path)
            if n:
                bucket = ((n - 1) // 50) * 50 + 1
                period_counts[bucket] += 1
        max_cnt = max(period_counts.values()) if period_counts else 1
        for start in sorted(period_counts):
            end = start + 49
            cnt = period_counts[start]
            b = c("█" * round(cnt / max_cnt * 10), BLUE) + " " * (10 - round(cnt / max_cnt * 10))
            lines.append((f"  S{start:<3}–{end:<3}  {b}  {cnt}", False))

    # Co-occurring words
    if cooccur:
        lines.append(("", False))
        lines.append((c("CO-OCCURRING WORDS (within 15)", DIM), False))
        top_co = cooccur.most_common(10)
        row1 = "  " + "   ".join(c(w, GRAY) + c(f"·{n}", DIM) for w, n in top_co[:5])
        row2 = "  " + "   ".join(c(w, GRAY) + c(f"·{n}", DIM) for w, n in top_co[5:])
        lines.append((row1, False))
        if top_co[5:]:
            lines.append((row2, False))

    lines.append(("", False))

    # Render box
    print(f"╭{'─' * W}╮")
    for content, is_div in lines:
        if is_div:
            print(f"├{'─' * W}┤")
        elif content == "":
            print(f"│{' ' * W}│")
        else:
            inner = f"  {content}"
            pad_width = W - ansi_len(inner)
            print(f"│{inner}{' ' * max(0, pad_width)}│")
    print(f"╰{'─' * W}╯")


# ── Display: KWIC lines ───────────────────────────────────────────────────────

def display_kwic(word, results, limit):
    """Display KWIC concordance lines, aligned on the keyword."""
    SIDE = 38  # visible chars for each side of keyword

    total = len(results)
    shown = min(total, limit)

    print()
    header = f"CONCORDANCE LINES  ({shown}/{total})"
    if total > limit:
        header += c(f"  —  use --limit N for more", DIM)
    print(c(header, BOLD))
    print("─" * 72)

    current_path = None
    for src_type, path, pre, matched, post in results[:limit]:
        if path != current_path:
            rel = str(path.relative_to(REPO))
            print(f"\n  {c('[' + rel + ']', DIM)}")
            current_path = path

        # Right-justify pre-context, then keyword, then post-context
        pre_str = " ".join(pre)
        post_str = " ".join(post)

        # Trim to SIDE chars
        if len(pre_str) > SIDE:
            pre_str = "…" + pre_str[-(SIDE - 1):]
        if len(post_str) > SIDE:
            post_str = post_str[:SIDE - 1] + "…"

        keyword = c(f" {matched.upper()} ", BOLD, WHITE)
        line = pad(pre_str, SIDE, align="right") + keyword + post_str
        print(f"  {line}")

    if total > limit:
        print()
        print(f"  {c(f'… {total - limit} more not shown', DIM)}")


# ── Display: top uncovered ────────────────────────────────────────────────────

def display_top(top_words):
    W = 58
    covered = get_covered_words()
    print(f"╭{'─' * W}╮")

    title = c("TOP UNCOVERED WORDS", BOLD, WHITE)
    inner = f"  {title}"
    print(f"│{inner}{' ' * max(0, W - ansi_len(inner))}│")

    sub = c("most frequent words without an on-X note", DIM)
    inner = f"  {sub}"
    print(f"│{inner}{' ' * max(0, W - ansi_len(inner))}│")

    print(f"├{'─' * W}┤")

    max_count = top_words[0][1] if top_words else 1

    for i, (word, count) in enumerate(top_words, 1):
        b = c("█" * round(count / max_count * 16), CYAN)
        blank = " " * (16 - round(count / max_count * 16))
        num = c(f"  {i:>2}.", DIM)
        w_part = c(f"  {word:<22}", CYAN)
        bar_part = f"  {b}{blank}"
        cnt_part = c(f"  {count:>5}", GRAY)
        line = f"{num}{w_part}{bar_part}{cnt_part}"
        pad_w = W - ansi_len(line)
        print(f"│{line}{' ' * max(0, pad_w)}│")

    print(f"╰{'─' * W}╯")

    print()
    print(c("  Run: python3 projects/concordance.py \"<word>\" to research any of these.", DIM))
    print(c("  Run: python3 projects/verse.py --gaps to see haiku coverage gaps.", DIM))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Classical concordance for the Claude OS corpus",
        add_help=True,
    )
    parser.add_argument("word", nargs="?", help="Word to search for")
    parser.add_argument("--brief", action="store_true", help="Summary only (no KWIC lines)")
    parser.add_argument("--kwic", action="store_true", help="KWIC lines only")
    parser.add_argument("--co", action="store_true", help="Co-occurring words only")
    parser.add_argument("--top", type=int, metavar="N", help="Show top N uncovered words")
    parser.add_argument("-n", "--context", type=int, default=8,
                        help="Words of context on each side (default: 8)")
    parser.add_argument("--limit", type=int, default=40,
                        help="Max KWIC lines to show (default: 40)")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    # Load corpus
    corpus = load_corpus()

    # --top mode
    if args.top is not None:
        top = top_uncovered(corpus, n=args.top)
        display_top(top)
        return

    if not args.word:
        parser.print_help()
        sys.exit(1)

    word = args.word.lower().strip()

    # Search
    results = search_word(word, corpus, context_n=args.context)
    cooccur = cooccurrences(results, target=word) if results else Counter()
    on_x = find_on_x_note(word)

    # Display
    if args.kwic:
        display_kwic(word, results, args.limit)
    elif args.co:
        if not cooccur:
            print(c(f'No occurrences of "{word}" found.', DIM))
        else:
            print(c(f'\nCO-OCCURRING WORDS for "{word}"', BOLD))
            print("─" * 50)
            for w, n in cooccur.most_common(30):
                bar = c("█" * round(n / cooccur.most_common(1)[0][1] * 20), CYAN)
                print(f"  {c(w, CYAN):<30}  {bar}  {n}")
    elif args.brief:
        display_summary(word, results, Counter(), on_x)
    else:
        # Full concordance
        display_summary(word, results, cooccur, on_x)
        if results:
            display_kwic(word, results, args.limit)
        else:
            print()
            print(c(f'  No occurrences of "{word}" found in the corpus.', DIM))


if __name__ == "__main__":
    main()
