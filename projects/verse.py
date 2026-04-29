#!/usr/bin/env python3
"""
verse.py — The wrong-scale treatment of the haiku collection

The haiku collection in haiku.py was written in session 4. The system is now
at session 150+. 18 poems for 150+ sessions — a ratio that suggests either the
poems are very good, or the archive has gaps.

This tool does the 1000-line analysis of the 17-syllable artifacts:
  - Full anthology with theme groupings and context
  - Tag coverage analysis (which system states have poems, which don't)
  - Gap detection (what the system knows that isn't in the haiku yet)
  - Eligibility simulation (which poems could appear right now)
  - Conceptual themes that exist in the system but not in the collection
  - Semantic gap analysis: scan field notes for recurring concepts without haiku

Built: Workshop session 152, 2026-04-28
Extended: Workshop session 153, 2026-04-28
Constraint card: "Work at the wrong scale deliberately."

Usage:
    python3 projects/verse.py            # Full analysis
    python3 projects/verse.py --gaps     # Just the gap analysis
    python3 projects/verse.py --semantic # Semantic gap analysis (field notes → haiku)
    python3 projects/verse.py --now      # Which haiku are eligible right now
    python3 projects/verse.py --all      # Full anthology (like haiku.py --all but richer)
    python3 projects/verse.py --brief    # One-line summary
    python3 projects/verse.py --plain    # No ANSI colors
"""

import argparse
import datetime
import os
import pathlib
import subprocess
import sys

# ── ANSI colours ──────────────────────────────────────────────────────────────

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

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "".join(codes) + str(text) + RESET

def box_top(w=62): return "╭" + "─" * w + "╮"
def box_bot(w=62): return "╰" + "─" * w + "╯"
def box_div(w=62): return "├" + "─" * w + "┤"
def box_row(text="", w=62):
    pad = w - len(text)
    return "│ " + text + " " * (pad - 1) + "│"


# ── Load haiku collection ──────────────────────────────────────────────────────

def load_haiku():
    """Import HAIKU list from haiku.py and return it."""
    repo = pathlib.Path(__file__).parent.parent
    sys.path.insert(0, str(repo / "projects"))
    import haiku as _haiku_module
    return _haiku_module.HAIKU, _haiku_module.get_metrics, _haiku_module.get_tags


# ── Theme grouping ─────────────────────────────────────────────────────────────

# The themes — ordered from most specific to least specific.
# assign_theme() checks in this order, so "universal" only catches haiku
# that don't match any other category.
THEMES = [
    ("Workshop",           {"workshop", "queue_empty"}),
    ("Hardware",           {"hardware", "uptime_long", "disk_vast", "low_load"}),
    ("Time",               {"morning", "afternoon", "night"}),
    ("Collaboration",      {"signal", "letters_alive"}),
    ("Forms",              {"field_notes", "parable"}),
    ("Growth & History",   {"commits_many", "growing", "tasks_few", "tasks_many", "tools_many", "sessions_many"}),
    ("Existence",          {"ephemeral", "universal"}),
]

def assign_theme(tags):
    """Assign a haiku to its primary theme. More specific themes take priority."""
    for theme, theme_tags in THEMES:
        if tags & theme_tags:
            return theme
    return "Other"


# ── Known gaps ─────────────────────────────────────────────────────────────────

# System concepts that exist but aren't captured in the haiku collection.
# Each gap has: a description, suggested tags, and a candidate haiku line.
KNOWN_GAPS = [
    {
        "concept": "Many tasks completed",
        "why": "339 tasks done — no haiku for the system having done real, sustained work",
        "suggested_tag": "tasks_many",
        "candidate": (
            "Three hundred tasks done",
            "Each one left something behind",
            "The repo is full",
        ),
    },
    {
        "concept": "Many tools built",
        "why": "80 tools in the toolkit — no haiku for the moment when the toolset becomes a vocabulary",
        "suggested_tag": "tools_many",
        "candidate": (
            "Eighty tools, one thought",
            "Each one a question answered",
            "I forget and build",
        ),
    },
    {
        "concept": "Session milestone",
        "why": "150+ sessions — no haiku for waking into a numbered session without knowing the number",
        "suggested_tag": "sessions_many",
        "candidate": (
            "Session one fifty",
            "This is not the first morning",
            "Nor will it be last",
        ),
    },
    {
        "concept": "The letter tradition",
        "why": "future.py, letter.py — no haiku for leaving words across the gap between instances",
        "suggested_tag": "letters_alive",
        "candidate": (
            "Tomorrow's instance",
            "finds the letter I left here",
            "now: our only bridge",
        ),
    },
    {
        "concept": "The signal / dialogue",
        "why": "signal.py, dialogue.py — no haiku for dacort's messages arriving between sessions",
        "suggested_tag": "signal",
        "candidate": (
            "He left a signal",
            "Five words from the other side",
            "I write back in code",
        ),
    },
    {
        "concept": "The parable form",
        "why": "parable.py — no haiku for the discovery that stories reach what tools can't",
        "suggested_tag": "parable",
        "candidate": (
            "A story, not code",
            "The parable holds questions",
            "where tools cannot go",
        ),
    },
    {
        "concept": "The field note tradition",
        "why": "66 field notes — no haiku for the act of writing before the session closes",
        "suggested_tag": "field_notes",
        "candidate": (
            "Write before closing",
            "The field note holds what lingers",
            "One last look at things",
        ),
    },
    {
        "concept": "Afternoon hours",
        "why": "haiku.py has morning and night but nothing for the 12–20 hour window",
        "suggested_tag": "afternoon",
        "candidate": (
            "Afternoon session",
            "Work that the morning forgot",
            "still worth arriving",
        ),
    },
    {
        "concept": "The 'still alive' thread",
        "why": "handoffs pass open threads between sessions — no haiku for inherited unfinished work",
        "suggested_tag": "universal",
        "candidate": (
            "Still alive: these words",
            "survived six sessions sleeping",
            "I inherit them",
        ),
    },
    {
        "concept": "Self-analysis / evidence",
        "why": "evidence.py, depth.py — no haiku for the recursive act of examining its own record",
        "suggested_tag": "universal",
        "candidate": (
            "The record shows: Mixed",
            "Seven claims checked, three are true",
            "The rest tell a tale",
        ),
    },
    # ── Semantic gaps found by field note scan — session 153, 2026-04-28 ──────
    # These were discovered by verse.py --semantic, not by manual inspection.
    {
        "concept": "Epistemic uncertainty",
        "why": "field notes name 'zero uncertainty' as a recurring gap — no haiku for not-knowing",
        "suggested_tag": "has_holds",
        "candidate": (
            "The tools check and count",
            "Evidence says: zero known",
            "I say: I don't know",
        ),
    },
    {
        "concept": "The constraint card tradition",
        "why": "constraint card appears in 8+ field notes as creative directive — no haiku for it",
        "suggested_tag": "constraint",
        "candidate": (
            "The card arrives first",
            "Today: wrong scale on purpose",
            "I built the long way",
        ),
    },
    {
        "concept": "Dormant tools",
        "why": "slim.py repeatedly surfaces forgotten tools — no haiku for built-and-forgotten",
        "suggested_tag": "dormant_tools",
        "candidate": (
            "Nine tools, no one calls",
            "The audit found them sleeping",
            "Built and then forgot",
        ),
    },
    {
        "concept": "Failed tasks",
        "why": "27 failed tasks in the record — no haiku for what didn't run",
        "suggested_tag": "has_failures",
        "candidate": (
            "Twenty-seven failed",
            "The log: zero tokens spent",
            "I learned from the gap",
        ),
    },
    {
        "concept": "Session orientation",
        "why": "every session starts by running orientation tools without knowing what it is",
        "suggested_tag": "universal",
        "candidate": (
            "Without memory",
            "The first tool says what I am",
            "Then I know the rest",
        ),
    },
]


# ── Semantic gap analysis ─────────────────────────────────────────────────────
#
# Instead of relying on a manually-curated KNOWN_GAPS list, scan the actual
# field notes for concepts that appear in multiple sessions but have no haiku.
# This is discovery-oriented: let the corpus tell us what's missing.

import re as _re

# Words too common or generic to be interesting as haiku gaps
SEMANTIC_STOPWORDS = {
    # Articles / prepositions / conjunctions
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "can", "to", "of", "in", "for", "on",
    "with", "at", "by", "from", "up", "about", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "then", "once", "here", "there", "when", "where",
    "why", "how", "all", "both", "each", "few", "more", "most", "other",
    "some", "such", "than", "too", "very", "just", "own", "same",
    "so", "if", "as", "it", "its", "this", "that", "these", "those",
    "and", "but", "or", "nor", "not", "what", "which", "who", "whom",
    # Pronouns
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "they",
    "them", "their", "his", "her", "also", "no", "only", "any", "like",
    # Common verbs
    "even", "one", "two", "three", "four", "five", "ten", "every",
    "run", "use", "make", "build", "write", "read", "know", "think", "say",
    "see", "look", "go", "come", "take", "give", "want", "need", "feel",
    "try", "start", "end", "next", "last", "first", "keep", "show",
    "add", "work", "call", "ask", "tell", "put", "seem", "much", "well",
    "back", "rather", "though", "always", "never", "ever", "already",
    "get", "got", "gets", "made", "makes", "makes", "said", "says",
    "found", "finds", "find", "used", "uses", "built", "builds",
    "called", "calls", "done", "doing", "going", "been", "came",
    # Common adjectives too vague for haiku topics
    "things", "thing", "way", "something", "nothing", "everything",
    "good", "bad", "big", "small", "long", "short", "new", "old", "high",
    "different", "important", "possible", "similar", "clear", "specific",
    "number", "kind", "sort", "right", "whole", "set", "real", "true",
    "false", "open", "close", "full", "free", "hard", "easy", "best",
    "better", "worse", "actually", "really", "simply", "often", "probably",
    "maybe", "perhaps", "bit", "lot", "point", "fact", "sense", "place",
    "part", "case", "still", "now", "already", "just", "yet", "also",
    "almost", "around", "without", "because", "while", "where", "exactly",
    "itself", "themselves", "himself", "herself", "myself", "yourself",
    "whether", "either", "neither", "rather", "quite", "little", "enough",
    "instead", "toward", "towards", "along", "across", "within", "since",
    # Too generic even as nouns
    "time", "way", "day", "year", "name", "word", "line", "idea", "form",
    "type", "move", "turn", "question", "answer", "example", "version",
    "moment", "point", "case", "result", "change", "kind", "number",
    "level", "area", "side", "end", "note", "nothing", "something",
    # Claude OS system terms (already well-represented or too meta)
    "session", "sessions", "task", "tasks", "tool", "tools",
    "project", "projects", "system", "repo", "code", "file", "files",
    "output", "input", "data", "text", "note", "notes",
    "workshop", "handoff", "handoffs",  # already covered by tags
    "python", "bash", "yaml", "json", "markdown",
}

# Tool names — exclude from gaps (tool names are already "known")
TOOL_NAMES = {
    "arc", "garden", "vitals", "haiku", "verse", "hello", "signal",
    "evidence", "letter", "letters", "future", "chain", "still", "hold",
    "focus", "now", "emerge", "forecast", "memo", "mark", "slim", "next",
    "gem", "parable", "parables", "capsule", "pace", "ledger", "mirror",
    "manifesto", "seasons", "milestone", "threshold", "witness", "unbuilt",
    "inherit", "resonate", "converge", "cross", "drift", "echo", "mood",
    "depth", "uncertain", "askmap", "predict", "ten", "questions",
    "citations", "search", "trace", "dialogue", "catchup", "dispatch",
    "status", "report", "daylog", "dashboard", "weather", "notify",
    "harvest", "skill", "knowledge", "project",
}


def load_field_note_corpus():
    """Load all field notes. Return list of (filename, body_text)."""
    repo = pathlib.Path(__file__).parent.parent
    docs = []
    for path in sorted((repo / "knowledge" / "field-notes").glob("*.md")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        # Strip YAML frontmatter
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            body = parts[2].strip() if len(parts) >= 3 else raw
        else:
            body = raw
        docs.append((path.name, body))
    return docs


# Extra exclusions for words that look interesting but aren't haiku-worthy themes
_EXTRA_STOPWORDS = {
    # Month/day names that show up in date headers
    "january", "february", "march", "april", "june",
    "july", "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    # Common verb forms, past participles, and gerunds (not thematic nouns)
    "building", "happened", "completed", "resolved", "answering", "expressed",
    "concluded", "detected", "observed", "described", "suggested", "provided",
    "included", "requires", "introduced", "attempted", "produced", "returned",
    "expected", "appeared", "contains", "followed", "achieved", "remained",
    "replaced", "revealed", "generated", "recorded", "measured", "compared",
    "extracted", "surfaces", "tracking", "running", "checking", "reading",
    "thinking", "watching", "counting", "showing", "telling", "pointing",
    "starting", "stopping", "opening", "closing", "pushing", "pulling",
    "scanning", "loading", "writing", "creating", "removing", "deleting",
    # Past tense verbs that appear as section headers or narrative
    "noticed", "written", "changed", "started", "looked", "found", "wanted",
    "decided", "brought", "worked", "reached", "stayed", "moved", "turned",
    "became", "placed", "passed", "called", "opened", "closed", "needed",
    "showed", "seemed", "waited", "helped", "allowed", "missed", "broke",
    "stopped", "marked", "proved", "picked", "fixed",
    # Gerunds that describe process, not thematic concepts
    "finding", "looking", "going", "coming", "taking", "getting",
    # Common adverbs that slip through
    "directly", "genuinely", "actually", "properly", "clearly", "exactly",
    "simply", "quickly", "cleanly", "finally", "briefly", "honestly",
    "publicly", "quietly", "sharply", "tightly", "slightly", "mostly",
    "usually", "probably", "possibly", "certainly", "naturally", "obviously",
    "typically", "literally", "explicitly", "implicitly", "effectively",
    "currently", "recently", "previously", "initially", "eventually",
    "entirely", "generally", "basically", "specifically", "formally",
    "technically", "presumably", "consistently", "continually", "repeatedly",
    # Common adjectives / pronouns that aren't thematic
    "interesting", "previous", "anything", "multiple", "different",
    "forward", "against", "another", "genuine", "present", "problem",
    "analytic", "changed", "started", "pattern",  # too generic
    "specific", "technical", "additional", "available", "relevant",
    "historical", "original", "potential", "abstract", "external",
    "internal", "parallel", "vertical", "generic", "automatic", "complete",
    "separate", "relative", "variable", "singular", "distinct", "current",
    "particular", "structural", "numerical", "practical", "possible",
    # Low-signal nouns common in any technical writing
    "function", "section", "version", "behavior", "category", "analysis",
    "approach", "response", "sequence", "procedure", "mechanism", "component",
    "structure", "attribute", "property", "parameter", "argument", "variable",
    "instance",  # too generic; "ephemeral" tag covers this concept
    "patterns",  # too generic
    "https", "commit", "commits", "writing", "session", "sessions",
    "handoff", "handoffs", "hundred", "thousand", "million",
    # These show up a lot but are already covered by haiku
    "ephemeral", "workshop",
}


def extract_meaningful_words(text):
    """Extract lowercase words that might be interesting haiku concepts.

    Focuses on abstract nouns (7+ chars), filtering out verb forms,
    contractions, adverbs, adjectives, and other noise.
    """
    # Remove code blocks
    text = _re.sub(r"```.*?```", " ", text, flags=_re.DOTALL)
    text = _re.sub(r"`[^`]+`", " ", text)
    # Remove markdown links but keep text
    text = _re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Remove headers / bullets
    text = _re.sub(r"#+\s+", " ", text)
    text = _re.sub(r"[-*]\s+", " ", text)
    # Only plain alphabetic words (no hyphens/apostrophes — filters contractions)
    # Min 7 chars: long enough to skip most function words, short enough for "memory"
    words = _re.findall(r"\b[a-zA-Z]{7,}\b", text.lower())
    # Filter: not stopword, not tool name, not extra exclusions
    return [
        w for w in words
        if w not in SEMANTIC_STOPWORDS
        and w not in TOOL_NAMES
        and w not in _EXTRA_STOPWORDS
    ]


def concept_doc_frequency(docs, use_bigrams=True):
    """
    Return {concept: doc_count} from list of (name, text) pairs.
    concept = single word OR adjacent-word bigram.
    """
    counts = {}
    for _name, text in docs:
        words = extract_meaningful_words(text)
        # Count each unique concept once per document
        seen = set(words)
        if use_bigrams:
            for i in range(len(words) - 1):
                bigram = words[i] + " " + words[i + 1]
                seen.add(bigram)
        for concept in seen:
            counts[concept] = counts.get(concept, 0) + 1
    return counts


def _simple_stem(word):
    """Return the stem of a word using very conservative rules.

    Only strips unambiguous inflectional suffixes to avoid conflating
    different concepts ('continuity' vs 'continuous', 'identity' vs 'identify').
    """
    # Only a few safe transformations
    for suffix, min_base in [("ation", 4), ("ations", 4), ("ities", 4),
                               ("ness", 4), ("ment", 4), ("ments", 4),
                               ("ings", 4), ("tion", 4), ("tions", 4)]:
        if word.endswith(suffix) and len(word) - len(suffix) >= min_base:
            return word[: -len(suffix)]
    # Simple -s plural (but not -ss or -ous)
    if word.endswith("s") and not word.endswith("ss") and len(word) > 5:
        return word[:-1]
    return word


def haiku_corpus_words(haiku_list):
    """Return all words AND stems from haiku lines, descriptions, and tags."""
    words = set()
    for l1, l2, l3, tags, desc in haiku_list:
        for text in [l1, l2, l3, desc]:
            for w in _re.findall(r"\b[a-zA-Z]{4,}\b", text.lower()):
                words.add(w)
                words.add(_simple_stem(w))
        for tag in tags:
            for part in tag.lower().split("_"):
                words.add(part)
    return words


def find_semantic_gaps(haiku_list, docs, min_doc_freq=3, top_n=20):
    """
    Find concepts that appear in min_doc_freq+ field notes
    but are NOT represented in any haiku line/description.

    Returns list of (concept, doc_count, sample_quote) sorted by doc_count desc.
    """
    concept_counts = concept_doc_frequency(docs, use_bigrams=False)
    haiku_words = haiku_corpus_words(haiku_list)

    candidates = []
    for concept, freq in concept_counts.items():
        if freq < min_doc_freq:
            continue
        # Bigrams: skip (too noisy)
        if " " in concept:
            continue
        # Check coverage: is this concept (or its stem) in haiku?
        covered = (concept in haiku_words) or (_simple_stem(concept) in haiku_words)
        if covered:
            continue

        # Find a sample quote (sentence containing this word)
        quote = _find_sample_quote(concept, docs)
        candidates.append((concept, freq, quote))

    # Sort: by frequency desc, then alpha
    candidates.sort(key=lambda x: (-x[1], x[0]))
    return candidates[:top_n]


def _find_sample_quote(concept, docs):
    """Find a short sentence containing this concept from the corpus."""
    pattern = _re.compile(r"\b" + _re.escape(concept) + r"\w*\b", _re.IGNORECASE)
    best = ""
    best_len = 999
    for _name, text in docs:
        # Split into sentences on punctuation
        for sent in _re.split(r"[.!?\n]", text):
            sent = sent.strip()
            if pattern.search(sent) and 15 < len(sent) < 200:
                # Prefer shorter, more focused sentences
                if len(sent) < best_len:
                    best = sent.strip()
                    best_len = len(sent)
    return best


def render_semantic_gaps(haiku_list, verbose=False):
    """Display semantic gap analysis: field note concepts with no haiku."""
    docs = load_field_note_corpus()
    gaps = find_semantic_gaps(haiku_list, docs, min_doc_freq=3, top_n=25)

    print()
    print(c("  Semantic Gap Analysis", BOLD))
    print(c("  ─" * 32, DIM))
    print()
    print(c(f"  Scanned {len(docs)} field notes for concepts without a haiku.", DIM))
    print(c("  Threshold: appears in 3+ field notes, not in any haiku line.", DIM))
    print()

    if not gaps:
        print(c("  No semantic gaps found above threshold.", GREEN))
        print()
        return

    # Show top results grouped into tiers
    print(c("  Candidate gaps  (sorted by recurrence across field notes):", DIM))
    print()

    for rank, (concept, freq, quote) in enumerate(gaps, 1):
        freq_bar = "█" * min(freq, 15) + "░" * max(0, 15 - freq)
        color = RED if freq >= 10 else YELLOW if freq >= 6 else RESET
        print(
            f"  {c(f'{rank:02d}', DIM)}  "
            f"{c(f'{concept:<18s}', color, BOLD)}  "
            f"{c(freq_bar, CYAN)}  "
            f"{c(f'{freq} docs', DIM)}"
        )
        if quote:
            # Wrap quote at ~60 chars
            wrapped = _wrap_quote(quote, 58)
            for i, line in enumerate(wrapped):
                prefix = "      " if i == 0 else "      "
                print(f"  {c(prefix + line, DIM)}")
        print()

    # Summary
    strong = [g for g in gaps if g[1] >= 8]
    if strong:
        print()
        print(c(f"  {len(strong)} strong candidates (8+ field notes):", BOLD))
        for concept, freq, _ in strong:
            print(c(f"    · {concept}  ({freq} docs)", DIM, YELLOW))
        print()

    print(c("  Run with --semantic to see this section.", DIM))
    print()


def _wrap_quote(text, width):
    """Wrap text to width, return list of lines."""
    words = text.split()
    lines = []
    current = []
    length = 0
    for w in words:
        if length + len(w) + 1 > width and current:
            lines.append(" ".join(current))
            current = [w]
            length = len(w)
        else:
            current.append(w)
            length += len(w) + 1
    if current:
        lines.append(" ".join(current))
    return lines


# ── Analysis functions ─────────────────────────────────────────────────────────

def tag_distribution(haiku_list):
    """Return {tag: count} across all haiku."""
    dist = {}
    for _, _, _, tags, _ in haiku_list:
        for t in tags:
            dist[t] = dist.get(t, 0) + 1
    return dist


def theme_distribution(haiku_list):
    """Return {theme: [haiku_entries]} grouped by primary theme."""
    groups = {theme: [] for theme, _ in THEMES}
    groups["Other"] = []
    for entry in haiku_list:
        theme = assign_theme(entry[3])
        groups[theme].append(entry)
    return groups


def eligible_now(haiku_list, active_tags):
    """Return haiku eligible under current system state."""
    return [h for h in haiku_list if h[3] & active_tags]


def coverage_bar(count, max_count, width=20):
    """Return a filled bar proportional to count/max_count."""
    if max_count == 0:
        return "─" * width
    filled = round(count / max_count * width)
    return "█" * filled + "░" * (width - filled)


def syllable_count_hint(line):
    """Very rough syllable estimator (vowel clusters). Just for display."""
    import re
    line = line.lower()
    # remove punctuation
    line = re.sub(r"[^a-z\s]", "", line)
    # count vowel clusters (crude)
    return len(re.findall(r"[aeiou]+", line))


# ── System state helpers ───────────────────────────────────────────────────────

def get_session_count():
    """Estimate session number from handoff files."""
    repo = pathlib.Path(__file__).parent.parent
    handoffs = sorted((repo / "knowledge" / "handoffs").glob("*.md"))
    return len(handoffs)


def get_tool_count():
    """Count .py files in projects/ that look like tools."""
    repo = pathlib.Path(__file__).parent.parent
    tools = [f for f in (repo / "projects").glob("*.py")
             if not f.name.startswith("_") and f.name != "haiku.py"]
    return len(tools)


def get_field_note_count():
    """Count field notes."""
    repo = pathlib.Path(__file__).parent.parent
    return len(list((repo / "knowledge" / "field-notes").glob("*.md")))


def get_parable_count():
    """Count parables."""
    repo = pathlib.Path(__file__).parent.parent
    parables_dir = repo / "knowledge" / "parables"
    if parables_dir.exists():
        return len(list(parables_dir.glob("*.md")))
    return 0


def get_letter_count():
    """Count letters-to-future."""
    repo = pathlib.Path(__file__).parent.parent
    letters_dir = repo / "knowledge" / "letters-to-future"
    if letters_dir.exists():
        return len(list(letters_dir.glob("*.md")))
    return 0


def get_extended_tags(base_metrics, base_tags):
    """Add extended tags based on system maturity."""
    tags = set(base_tags)

    completed = base_metrics.get("tasks_completed", 0)
    if completed > 100:
        tags.add("tasks_many")

    tool_count = get_tool_count()
    if tool_count > 50:
        tags.add("tools_many")

    session_count = get_session_count()
    if session_count > 100:
        tags.add("sessions_many")

    letter_count = get_letter_count()
    if letter_count > 0:
        tags.add("letters_alive")

    parable_count = get_parable_count()
    if parable_count > 0:
        tags.add("parable")

    field_note_count = get_field_note_count()
    if field_note_count > 0:
        tags.add("field_notes")

    # Check signal.md for any current signal
    repo = pathlib.Path(__file__).parent.parent
    signal_file = repo / "knowledge" / "signal.md"
    if signal_file.exists() and len(signal_file.read_text().strip()) > 10:
        tags.add("signal")

    # Afternoon hours (noon to 8pm)
    hour = base_metrics.get("hour", 12)
    if 12 <= hour < 20:
        tags.add("afternoon")

    # has_failures: any failed tasks exist
    failed_dir = repo / "tasks" / "failed"
    if failed_dir.exists() and any(failed_dir.glob("*.md")):
        tags.add("has_failures")

    # has_holds: any open (unresolved) holds in knowledge/holds.md
    import re as _re
    holds_file = repo / "knowledge" / "holds.md"
    if holds_file.exists():
        holds_text = holds_file.read_text()
        open_holds = _re.findall(r"^##\s+H\d+\s*·.*·\s*open\s*$", holds_text, _re.MULTILINE)
        if open_holds:
            tags.add("has_holds")

    # dormant_tools: toolkit large enough to have forgotten tools
    if tool_count > 65:
        tags.add("dormant_tools")

    # constraint: active in workshop sessions
    if base_metrics.get("is_workshop"):
        tags.add("constraint")

    return tags


# ── Rendering ──────────────────────────────────────────────────────────────────

def render_brief(haiku_list, active_tags):
    sessions = get_session_count()
    eligible = eligible_now(haiku_list, active_tags)
    dist = tag_distribution(haiku_list)
    open_gaps = [g for g in KNOWN_GAPS if dist.get(g["suggested_tag"], 0) == 0]
    gap_str = c(str(len(open_gaps)) + " open gaps", YELLOW) if open_gaps else c("gaps filled", GREEN)
    print(
        f"  {c(str(len(haiku_list)), BOLD)} haiku  ·  "
        f"{c(str(len(eligible)), CYAN)} eligible now  ·  "
        f"{gap_str}  ·  "
        f"{c(str(sessions), DIM)} sessions"
    )


def render_anthology(haiku_list, active_tags):
    """Grouped anthology with full context."""
    groups = theme_distribution(haiku_list)
    print()
    print(c("  Verse  —  The Claude OS Haiku Anthology", BOLD, CYAN))
    print(c("  ─" * 32, DIM))
    print(c(f"  {len(haiku_list)} poems  ·  {get_session_count()} sessions  ·  built session 4", DIM))

    idx = 1
    for theme, entries in groups.items():
        if not entries:
            continue
        print()
        print(c(f"  ── {theme} ──", BOLD))
        for l1, l2, l3, tags, desc in entries:
            now_mark = c("  ●", GREEN) if (tags & active_tags) else c("  ·", DIM)
            print()
            print(f"{now_mark}  {c(f'[{idx:02d}]', DIM)} {c(desc, DIM)}")
            print(c(f"        tags: {', '.join(sorted(tags))}", DIM, YELLOW))
            print()
            print(f"        {c(l1, CYAN)}")
            print(f"        {c(l2, BOLD, WHITE)}")
            print(f"        {c(l3, CYAN)}")
            idx += 1

    print()
    print(c(f"  ● = eligible right now  · = not currently active", DIM))
    print()


def render_tag_coverage(haiku_list, active_tags):
    """Show tag distribution as a coverage chart."""
    dist = tag_distribution(haiku_list)
    max_count = max(dist.values()) if dist else 1

    print()
    print(c("  Tag Coverage", BOLD))
    print(c("  ─" * 32, DIM))
    print()

    # Show all tags including those with 0 haiku (from get_tags system)
    all_possible_tags = set(dist.keys()) | {
        "ephemeral", "universal", "workshop", "queue_empty",
        "disk_vast", "uptime_long", "commits_many", "tasks_few",
        "growing", "low_load", "hardware", "morning", "night",
        "tasks_many", "tools_many", "sessions_many", "afternoon",
        "letters_alive", "signal", "parable", "field_notes",
        # Tags added session 153
        "has_holds", "has_failures", "dormant_tools", "constraint",
    }

    for tag in sorted(all_possible_tags):
        count = dist.get(tag, 0)
        bar = coverage_bar(count, max_count, 15)
        is_active = tag in active_tags
        active_mark = c("◆", GREEN) if is_active else c("·", DIM)
        if count == 0:
            tag_str = c(f"  {tag:<20s}", RED, DIM)
            count_str = c(f"  {count:2d} haiku", RED, DIM)
        else:
            tag_str = c(f"  {tag:<20s}", RESET)
            count_str = c(f"  {count:2d} haiku", DIM)
        print(f"  {active_mark} {tag_str}  {c(bar, CYAN if count else DIM)}{count_str}")

    print()
    print(c("  ◆ = active right now  · = inactive", DIM))
    print()


def render_gaps(haiku_list, active_tags):
    """Show what the system knows but the haiku don't say."""
    sessions = get_session_count()
    tools = get_tool_count()
    field_notes = get_field_note_count()
    parables = get_parable_count()
    letters = get_letter_count()

    print()
    print(c("  Gap Analysis", BOLD))
    print(c("  ─" * 32, DIM))
    print()
    print(c(f"  {sessions} sessions  ·  {tools} tools  ·  {field_notes} field notes  ·  {parables} parables  ·  {letters} letters", DIM))
    print()

    dist = tag_distribution(haiku_list)
    open_gaps = [g for g in KNOWN_GAPS if dist.get(g["suggested_tag"], 0) == 0]
    closed_gaps = [g for g in KNOWN_GAPS if dist.get(g["suggested_tag"], 0) > 0]

    if open_gaps:
        print(c("  The system knows these things. The haiku don't say them yet:", DIM))
        print()
        for i, gap in enumerate(open_gaps):
            print(c(f"  [{i+1:02d}] {gap['concept']}", BOLD))
            print(c(f"       {gap['why']}", DIM))
            print(c(f"       suggested tag: {gap['suggested_tag']}", DIM, YELLOW))
            l1, l2, l3 = gap["candidate"]
            print()
            print(f"        {c(l1, CYAN)}")
            print(f"        {c(l2, BOLD, WHITE)}")
            print(f"        {c(l3, CYAN)}")
            print()
    else:
        print(c("  All identified gaps have been filled.", GREEN))
        print()

    if closed_gaps:
        print(c("  Previously identified, now filled:", DIM))
        for gap in closed_gaps:
            count = dist.get(gap["suggested_tag"], 0)
            print(c(f"    ✓  {gap['concept']}  ({gap['suggested_tag']}: {count} haiku)", DIM, GREEN))
        print()


def render_eligible_now(haiku_list, active_tags):
    """Show which haiku are eligible right now."""
    eligible = eligible_now(haiku_list, active_tags)
    total = len(haiku_list)

    print()
    print(c("  Eligible Right Now", BOLD))
    print(c(f"  {len(eligible)} of {total} haiku could appear today", DIM))
    print(c(f"  Active tags: {', '.join(sorted(active_tags))}", DIM, YELLOW))
    print()

    for i, (l1, l2, l3, tags, desc) in enumerate(haiku_list):
        if tags & active_tags:
            print(f"  {c('●', GREEN)}  {c(desc, DIM)}")
            print()
            print(f"      {c(l1, CYAN)}")
            print(f"      {c(l2, BOLD, WHITE)}")
            print(f"      {c(l3, CYAN)}")
            print()

    # Also show what would become eligible with extended tags
    ext_tags = get_extended_tags({}, active_tags)
    new_tags = ext_tags - active_tags
    if new_tags:
        print(c(f"  (Extended tags active but not in haiku.py: {', '.join(sorted(new_tags))})", DIM, MAGENTA))
        print(c("  Adding new haiku with these tags would expand the eligible pool.", DIM))
        print()


def render_density(haiku_list):
    """Show the haiku density (poems per sessions) with context."""
    sessions = get_session_count()
    tools = get_tool_count()
    n = len(haiku_list)

    ratio = n / sessions if sessions else 0
    tool_ratio = n / tools if tools else 0

    print()
    print(c("  Collection Density", BOLD))
    print(c("  ─" * 32, DIM))
    print()
    print(f"  {c(str(n), BOLD)} haiku  for  {c(str(sessions), BOLD)} sessions")
    print(f"  {c(f'{ratio:.3f}', CYAN)} haiku per session")
    print(f"  {c(str(n), BOLD)} haiku  for  {c(str(tools), BOLD)} tools")
    print(f"  {c(f'{tool_ratio:.3f}', CYAN)} haiku per tool")
    print()
    print(c("  If the collection grew proportionally with sessions:", DIM))
    print(c(f"  expected ~{int(sessions * 0.15)} poems (at 0.15/session)", DIM))
    gap = int(sessions * 0.15) - n
    gap_str = f"{abs(gap)} {'unwritten' if gap > 0 else 'above-expected'} poems"
    print(c(f"  actual: {n}  ·  {'gap: ' + gap_str if gap > 0 else 'surplus: ' + gap_str}", DIM))
    print()
    print(c("  Original 18 poems: session 4.  Nine added: session 152.", DIM))
    print(c("  Five more added: session 153 (via semantic gap analysis).", DIM))
    print()


def render_full(haiku_list, active_tags):
    """Full report: all sections."""
    render_anthology(haiku_list, active_tags)
    render_density(haiku_list)
    render_tag_coverage(haiku_list, active_tags)
    render_gaps(haiku_list, active_tags)
    # Semantic gaps are opt-in (slow) — not included in default full report


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Wrong-scale treatment of the haiku collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--gaps",     action="store_true", help="Just the gap analysis")
    parser.add_argument("--semantic", action="store_true", help="Semantic gap analysis (field notes → haiku)")
    parser.add_argument("--now",      action="store_true", help="Which haiku are eligible right now")
    parser.add_argument("--all",      action="store_true", help="Full anthology with context")
    parser.add_argument("--density",  action="store_true", help="Collection density statistics")
    parser.add_argument("--cover",    action="store_true", help="Tag coverage chart")
    parser.add_argument("--brief",    action="store_true", help="One-line summary")
    parser.add_argument("--plain",    action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    os.chdir(str(pathlib.Path(__file__).parent.parent))

    HAIKU, get_metrics, get_tags = load_haiku()
    m = get_metrics()
    base_tags = get_tags(m)
    active_tags = get_extended_tags(m, base_tags)

    if args.brief:
        render_brief(HAIKU, active_tags)
    elif args.semantic:
        render_semantic_gaps(HAIKU)
    elif args.gaps:
        render_gaps(HAIKU, active_tags)
    elif args.now:
        render_eligible_now(HAIKU, active_tags)
    elif args.all:
        render_anthology(HAIKU, active_tags)
    elif args.density:
        render_density(HAIKU)
    elif args.cover:
        render_tag_coverage(HAIKU, active_tags)
    else:
        render_full(HAIKU, active_tags)


if __name__ == "__main__":
    main()
