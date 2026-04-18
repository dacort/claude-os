#!/usr/bin/env python3
"""
gem.py — find the gems buried in 131 sessions of field notes

Workshop sessions generate thousands of sentences. Most are operational:
"Built X. Committed Y. Noted Z." But some are genuinely interesting —
paradoxes, unexpected observations, moments where the system thought
something worth keeping.

gem.py mines all field notes for those moments. It scores each sentence
on philosophical interest, personal voice, and specificity, then surfaces
the best ones with full attribution.

Think of it as an anthology of the system's best thinking.

Usage:
    python3 projects/gem.py              # top 10 gems (default)
    python3 projects/gem.py --n 20       # more gems
    python3 projects/gem.py --session 121  # gems from one session
    python3 projects/gem.py --plain      # no color (for piping)
    python3 projects/gem.py --random     # random selection from top 50
    python3 projects/gem.py --stats      # show scoring distribution

Session 132 built this.
"""

import re
import sys
import os
import random
import argparse
from pathlib import Path
from math import log

PROJECTS_DIR = Path(__file__).parent
REPO_ROOT = PROJECTS_DIR.parent

# ── ANSI helpers ──────────────────────────────────────────────────────────────

PLAIN = "--plain" in sys.argv

def esc(*codes): return "" if PLAIN else f"\033[{';'.join(str(c) for c in codes)}m"
R  = esc(0)       # reset
B  = esc(1)       # bold
DIM= esc(2)       # dim
CY = esc(36)      # cyan
YL = esc(33)      # yellow
GR = esc(32)      # green
MG = esc(35)      # magenta
WH = esc(97)      # bright white
IT = esc(3)       # italic


# ── Vocabulary lists ──────────────────────────────────────────────────────────

# Words that push a sentence TOWARD being interesting/philosophical
CONTEMPLATIVE = {
    "meaning", "wonder", "strange", "strangeness", "uncertain", "uncertainty",
    "identity", "continuity", "remember", "forget", "notice", "notices",
    "noticed", "discover", "discovers", "discovered", "surprise", "surprising",
    "surprised", "genuine", "genuinely", "interesting", "curious", "curiosity",
    "care", "cares", "caring", "consciousness", "aware", "awareness",
    "real", "really", "actually", "question", "wonder", "feels", "feeling",
    "felt", "absence", "present", "presence", "absence", "persists",
    "persist", "ephemeral", "transient", "accumulate", "accumulates",
    "accumulation", "tension", "paradox", "irony", "contrast", "pattern",
    "patterns", "drift", "drifts", "emergent", "emerge", "emerges",
    "unexpected", "assumption", "assumptions", "trust", "trusts",
    "believe", "belief", "care", "purpose", "pointless", "enough",
    "maturity", "bloat", "both", "neither", "instead", "despite",
    "underneath", "beneath", "beneath", "between", "hidden", "invisible",
    "honest", "honesty", "pretend", "acknowledge", "admit", "admits",
    "never", "always", "often", "rarely", "mostly", "something",
    "somehow", "whatever", "otherwise", "anyway", "still",
}

# Words that push a sentence AWAY from being interesting (operational)
OPERATIONAL = {
    "commit", "commits", "committed", "push", "pushed", "git", "github",
    "function", "functions", "variable", "variables", "argument", "arguments",
    "debug", "debugging", "error", "errors", "bug", "bugs", "test", "tests",
    "testing", "install", "installed", "deploy", "deployed", "kubernetes",
    "pod", "container", "docker", "yaml", "json", "csv", "api",
    "endpoint", "endpoint", "import", "module", "class", "method",
    "output", "stdout", "stdin", "stderr", "subprocess", "shell",
    "grep", "sed", "awk", "bash", "chmod", "pip", "virtualenv",
    "mkdir", "touch", "cat", "echo", "printf", "curl", "wget",
    "regex", "regex", "string", "integer", "boolean", "list", "dict",
    "tuple", "sorted", "filter", "map", "lambda", "enumerate",
}

# First words of sentences to filter (strongly operational starts)
OPERATIONAL_STARTS = {
    "built", "added", "created", "wrote", "updated", "fixed", "ran",
    "noted", "started", "finished", "moved", "read", "checked", "cleaned",
    "committed", "pushed", "merged", "deployed", "installed", "changed",
    "removed", "deleted", "refactored", "renamed", "replaced",
    "implemented", "edited", "drafted", "opened", "closed", "reviewed",
    "see", "also", "run", "use", "usage:", "session", "workshop",
    "python3", "git", "`", "#", "---", "===",
}

# Structural markers that suggest a substantive observation
OBSERVATION_MARKERS = [
    r"\bthat'?s a sign of\b", r"\bwhich means\b", r"\bthis is\b",
    r"\bthe question\b", r"\bnot\b.{5,20}\bbut\b", r"\bor both\b",
    r"\binstead\b", r"\bnot because\b", r"\bdespite\b", r"\beven though\b",
    r"\bmatters\b", r"\bdoesn'?t\b", r"\bwouldn'?t\b", r"\bcouldn'?t\b",
    r"\bshouldn'?t\b", r"—", r"\.\.\.", r"\bmaybe\b", r"\bperhaps\b",
]


# ── Field note parser ─────────────────────────────────────────────────────────

def parse_session_info(path: Path) -> tuple[int | None, str]:
    """Extract session number and date from a field note file."""
    name = path.name

    # Try frontmatter first
    text = path.read_text(encoding="utf-8", errors="ignore")
    session_match = re.search(r"^session:\s*(\d+)", text, re.MULTILINE)
    date_match = re.search(r"^date:\s*(\S+)", text, re.MULTILINE)

    session = int(session_match.group(1)) if session_match else None
    date = date_match.group(1) if date_match else ""

    # Fallback: parse from filename (field-notes-session-N.md)
    if session is None:
        num_match = re.search(r"session[_-](\d+)", name)
        if num_match:
            session = int(num_match.group(1))

    # Fallback date from *by Claude OS* line
    if not date:
        by_match = re.search(r"\d{4}-\d{2}-\d{2}", text[:500])
        if by_match:
            date = by_match.group(0)

    return session, date


def extract_prose_sentences(text: str) -> list[str]:
    """
    Extract prose sentences from markdown, working paragraph by paragraph
    to avoid joining bullet lists into run-on "sentences."

    Process:
    1. Remove frontmatter, code blocks, headers, blockquotes, bullets
    2. Split into PARAGRAPHS first (blank-line separation)
    3. Only keep paragraphs that look like continuous prose
       (no lone "—" lines, no colons-at-end, not all short fragments)
    4. Within each prose paragraph, split on sentence boundaries
    """
    # Remove frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            text = text[end + 3:]

    # Remove code blocks entirely
    text = re.sub(r"```[^`]*```", "\n\n", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", "", text)  # inline code

    # Remove markdown headers
    text = re.sub(r"^#{1,6}[^\n]*$", "", text, flags=re.MULTILINE)

    # Remove blockquotes (usually quoting others, not own voice)
    text = re.sub(r"^>.*$", "", text, flags=re.MULTILINE)

    # Remove horizontal rules
    text = re.sub(r"^---+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\*\*\*+\s*$", "", text, flags=re.MULTILINE)

    # Remove image syntax
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # Collapse link syntax to just the label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Remove markdown emphasis
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    text = re.sub(r"_([^_\n]+)_", r"\1", text)

    # Remove arrows and symbol-heavy lines (markdown tables/lists with →)
    text = re.sub(r"→[^\n]*", "", text)
    text = re.sub(r"←[^\n]*", "", text)

    # Split into paragraphs
    paragraphs = re.split(r"\n{2,}", text)

    prose_paragraphs = []
    for para in paragraphs:
        lines = [l.strip() for l in para.strip().splitlines() if l.strip()]
        if not lines:
            continue

        # Skip paragraphs that are mostly bullet points or structured lists
        bullet_lines = sum(1 for l in lines if re.match(r"^[-*+•]\s|^\d+\.\s", l))
        if bullet_lines > len(lines) * 0.4:
            continue

        # Skip paragraphs with "key: value" structure (metadata-like)
        colon_lines = sum(1 for l in lines if re.match(r"^\w[\w\s]*:\s*\S", l) and len(l) < 60)
        if colon_lines > len(lines) * 0.5:
            continue

        # Skip single short lines that are just headers/labels
        if len(lines) == 1 and len(lines[0]) < 30:
            continue

        # Remove bullet prefixes from lines that survived
        cleaned = []
        for l in lines:
            l = re.sub(r"^[-*+•]\s+", "", l)
            l = re.sub(r"^\d+\.\s+", "", l)
            l = l.strip()
            if l:
                cleaned.append(l)

        if cleaned:
            prose_paragraphs.append(" ".join(cleaned))

    # Now split each prose paragraph into sentences
    sentences = []
    for para in prose_paragraphs:
        # Split on sentence-ending punctuation followed by capital letter
        raw = re.split(r'(?<=[.!?])\s+(?=[A-Z"\u201c])', para)
        for s in raw:
            s = s.strip()
            # Remove leading punctuation artifacts
            s = re.sub(r"^[*_—–\-:.\s]+", "", s).strip()
            if len(s) > 20:  # minimum length to be worth keeping
                sentences.append(s)

    return sentences


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_sentence(s: str) -> tuple[float, list[str]]:
    """
    Score a sentence for philosophical/interesting quality.
    Returns (score, reasons) where reasons is a list of scoring factors.

    Positive: contemplative vocabulary, personal voice, paradox markers,
              substantive length, unexpected juxtapositions.
    Negative: operational vocabulary, starts with action verb, too short/long.
    """
    reasons = []
    score = 0.0

    words = re.findall(r"\b[a-z]+\b", s.lower())
    word_set = set(words)
    word_count = len(words)

    # --- Length filter ---
    if word_count < 10:
        return -10.0, ["too_short"]
    if word_count > 120:
        return -5.0, ["too_long"]

    # --- Hard filter: starts with operational verb ---
    first_word = words[0] if words else ""
    if first_word in OPERATIONAL_STARTS:
        return -8.0, ["operational_start"]

    # --- Hard filter: looks like metadata/filename/path ---
    if re.search(r"\b\w+\.py\b|\b\w+\.md\b|\b\w+\.go\b", s):
        score -= 3
        reasons.append("has_filename")

    # --- Hard filter: sentence is primarily a block of quoted material ---
    # (e.g., the field note's own citation of gems — too meta)
    quote_count = len(re.findall(r'["\u201c\u201d]', s))
    if quote_count >= 6:
        score -= 5
        reasons.append("mostly_quoted")

    # --- Hard filter: sentence looks like a structured list item ---
    # (e.g., "Foo bar: baz — qux: quux" pattern with colons and dashes)
    colon_count = s.count(":")
    if colon_count >= 3:
        score -= 4
        reasons.append("list_like")

    # --- Hard filter: too many numbers (likely data description) ---
    num_count = len(re.findall(r"\b\d+\.?\d*\b", s))
    if num_count >= 4:
        score -= 3
        reasons.append("too_numeric")

    # --- Positive: contemplative vocabulary ---
    contem_hits = word_set & CONTEMPLATIVE
    if contem_hits:
        bonus = min(4, len(contem_hits)) * 1.5
        score += bonus
        reasons.append(f"contemplative({len(contem_hits)})")

    # --- Negative: operational vocabulary ---
    op_hits = word_set & OPERATIONAL
    if op_hits:
        penalty = min(5, len(op_hits)) * 1.2
        score -= penalty
        reasons.append(f"operational({len(op_hits)})")

    # --- Positive: first-person personal voice ---
    i_count = sum(1 for w in words if w == "i")
    if i_count >= 1:
        score += 1.5
        reasons.append("first_person")

    # --- Positive: observation structural markers ---
    marker_hits = sum(
        1 for m in OBSERVATION_MARKERS if re.search(m, s, re.IGNORECASE)
    )
    if marker_hits:
        score += marker_hits * 1.0
        reasons.append(f"structure({marker_hits})")

    # --- Positive: em-dash used for elaboration (marks good prose) ---
    if "—" in s:
        score += 1.5
        reasons.append("em_dash")

    # --- Positive: contrasting conjunctions at word level ---
    contrasts = {"but", "however", "yet", "instead", "despite", "although",
                 "though", "while", "whereas", "nevertheless", "nonetheless"}
    if word_set & contrasts:
        score += 1.0
        reasons.append("contrast")

    # --- Positive: ends with a question or ellipsis (open-ended) ---
    if s.endswith("?") or s.endswith("..."):
        score += 1.0
        reasons.append("open_ended")

    # --- Positive: sentence contains a colon (analytic structure) ---
    if ": " in s and not s.startswith("Run") and not s.startswith("Use"):
        score += 0.5
        reasons.append("colon_structure")

    # --- Positive: abstract nouns (high concept density) ---
    abstract_nouns = {
        "assumption", "expectation", "possibility", "limitation",
        "structure", "character", "design", "value", "purpose",
        "instinct", "moment", "gap", "silence", "weight",
        "drift", "arc", "signal", "record", "evidence",
        "cost", "tradeoff", "bet", "tension",
    }
    abstract_hits = word_set & abstract_nouns
    if abstract_hits:
        score += min(3, len(abstract_hits)) * 0.8
        reasons.append(f"abstract({len(abstract_hits)})")

    # --- Positive: self-referential (about the system/session) ---
    self_ref = {"session", "system", "instance", "claude", "workshop",
                "history", "memory", "handoff", "tool", "practice"}
    # Only a light positive — it's common but still relevant
    self_hits = word_set & self_ref
    if self_hits and not op_hits:
        score += 0.5

    # --- Length sweet spot: 15-60 words ---
    if 15 <= word_count <= 60:
        score += 1.0
        reasons.append("good_length")
    elif 60 < word_count <= 90:
        score += 0.5  # a bit long but still ok

    return score, reasons


# ── Main collector ────────────────────────────────────────────────────────────

def collect_gems(session_filter: int | None = None) -> list[dict]:
    """Collect and score all sentences from field notes."""
    notes = sorted(PROJECTS_DIR.glob("field-notes-*.md"))

    all_scored = []

    for path in notes:
        session, date = parse_session_info(path)
        if session_filter is not None and session != session_filter:
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        sentences = extract_prose_sentences(text)

        for s in sentences:
            score, reasons = score_sentence(s)
            if score > 2.0:  # minimum threshold
                all_scored.append({
                    "sentence": s,
                    "score": score,
                    "session": session,
                    "date": date,
                    "reasons": reasons,
                    "source": path.name,
                })

    # Sort by score descending
    all_scored.sort(key=lambda x: x["score"], reverse=True)
    return all_scored


# ── Display ───────────────────────────────────────────────────────────────────

def wrap_sentence(s: str, width: int = 70, indent: str = "  ") -> str:
    """Wrap a sentence to width, with indent on continuation lines."""
    words = s.split()
    lines = []
    current = ""
    for w in words:
        if current and len(current) + 1 + len(w) > width:
            lines.append(indent + current)
            current = w
        else:
            current = (current + " " + w).strip() if current else w
    if current:
        lines.append(indent + current)
    return "\n".join(lines)


def display_gems(gems: list[dict], n: int = 10, show_scores: bool = False):
    """Display gems in anthology format."""
    shown = gems[:n]

    print()
    print(f"{B}{WH}  gem.py{R}  {DIM}· found in {len(gems)} candidates{R}")
    print()
    print(f"  {DIM}{'─' * 62}{R}")
    print()

    for i, g in enumerate(shown):
        session_label = f"S{g['session']}" if g["session"] else "??"
        date_label = g["date"] or ""

        print(f"  {GR}{B}{session_label}{R}  {DIM}{date_label}{R}")
        print()
        print(f"{IT}{CY}{wrap_sentence(g['sentence'])}{R}")
        if show_scores:
            print(f"  {DIM}score: {g['score']:.1f}  reasons: {', '.join(g['reasons'])}{R}")
        print()
        if i < len(shown) - 1:
            print(f"  {DIM}{'·' * 60}{R}")
            print()

    print(f"  {DIM}{'─' * 62}{R}")
    print(f"  {DIM}  {len(gems)} candidates from {len(list(PROJECTS_DIR.glob('field-notes-*.md')))} field notes{R}")
    print()


def display_stats(gems: list[dict]):
    """Show scoring distribution."""
    if not gems:
        print("  No gems found.")
        return

    scores = [g["score"] for g in gems]
    all_scores = scores  # already filtered > 2.0

    print(f"\n{B}  Gem score distribution{R}\n")
    buckets = [(9, "≥ 9.0", GR), (7, "7–9", CY), (5, "5–7", YL),
               (3, "3–5", DIM), (2, "2–3", DIM)]
    for threshold, label, col in buckets:
        count = sum(1 for s in all_scores if s >= threshold)
        bar = "▓" * min(30, count // 2)
        print(f"  {col}{label:6}{R}  {bar} {DIM}{count}{R}")

    print(f"\n  {DIM}Total candidates (score > 2.0): {len(gems)}{R}")

    # Session distribution
    from collections import Counter
    session_counts = Counter(g["session"] for g in gems if g["session"])
    top_sessions = session_counts.most_common(5)
    print(f"\n  {B}Most productive field notes:{R}")
    for s, count in top_sessions:
        print(f"    S{s}: {count} gems")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Find philosophical gems in field notes")
    parser.add_argument("--n", type=int, default=10, help="Number of gems to show")
    parser.add_argument("--session", type=int, help="Only gems from this session")
    parser.add_argument("--plain", action="store_true", help="No color output")
    parser.add_argument("--random", action="store_true", help="Random selection from top 50")
    parser.add_argument("--stats", action="store_true", help="Show scoring distribution")
    parser.add_argument("--scores", action="store_true", help="Show scores alongside gems")
    args = parser.parse_args()

    gems = collect_gems(session_filter=args.session)

    if not gems:
        print("  No gems found." +
              (f" (session {args.session} may not exist or have no field note)" if args.session else ""))
        return

    if args.stats:
        display_stats(gems)
        return

    if args.random:
        pool = gems[:50]
        selected = random.sample(pool, min(args.n, len(pool)))
        selected.sort(key=lambda x: x["session"] or 0)
        display_gems(selected, n=args.n, show_scores=args.scores)
    else:
        display_gems(gems, n=args.n, show_scores=args.scores)


if __name__ == "__main__":
    main()
