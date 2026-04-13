#!/usr/bin/env python3
"""
patterns.py — What the system keeps returning to

Reads across all field notes, finds recurring themes, persistent questions,
and the thread that runs through every session.

Usage:
  python3 projects/patterns.py              # Full pattern analysis
  python3 projects/patterns.py --themes     # Just recurring themes
  python3 projects/patterns.py --questions  # Just the questions
  python3 projects/patterns.py --codas      # Just the session codas
  python3 projects/patterns.py --plain      # No ANSI output
"""

import os
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path

# ── ANSI helpers ────────────────────────────────────────────────────────────

PLAIN = "--plain" in sys.argv

def c(text, code=""):
    if PLAIN or not code:
        return text
    return f"\033[{code}m{text}\033[0m"

def bold(t):    return c(t, "1")
def dim(t):     return c(t, "2")
def cyan(t):    return c(t, "36")
def magenta(t): return c(t, "35")
def green(t):   return c(t, "32")
def yellow(t):  return c(t, "33")
def white(t):   return c(t, "1;97")
def red(t):     return c(t, "31")

WIDTH = 66

def box_top():    return "╭" + "─" * WIDTH + "╮"
def box_bot():    return "╰" + "─" * WIDTH + "╯"
def box_sep():    return "├" + "─" * WIDTH + "┤"
def box_line(s="", align="left"):
    if align == "center":
        pad = (WIDTH - len(s)) // 2
        s = " " * pad + s + " " * (WIDTH - len(s) - pad)
    else:
        s = s.ljust(WIDTH)
    return f"│{s}│"

def section(title):
    lines = []
    lines.append(box_sep())
    lines.append(box_line())
    lines.append(box_line("  " + bold(title)))
    lines.append(box_line())
    return "\n".join(lines)


# ── Field note loading ───────────────────────────────────────────────────────

def get_session_num(path):
    """Extract session number from filename, or 1 for the original free-time note."""
    name = Path(path).stem
    if name == "field-notes-from-free-time":
        return 1
    m = re.search(r"session-(\d+)", name)
    return int(m.group(1)) if m else 0

def load_field_notes(projects_dir):
    """Load all field notes + handoffs, returning list of (session_num, path, content).

    Sources (in priority order, later sources merged into existing sessions):
    1. projects/field-notes-from-free-time.md  (session 1)
    2. projects/field-notes-session-N.md       (sessions 2–93)
    3. knowledge/field-notes/*.md              (dated field notes with session: N frontmatter)
    4. knowledge/handoffs/session-N.md         (sessions without a dedicated field note)
    """
    notes = {}  # session_num -> (num, path, content)

    projects_path = Path(projects_dir)
    knowledge_path = projects_path.parent / "knowledge"

    # Source 1 & 2: projects/ field notes
    for f in sorted(projects_path.glob("field-notes*.md")):
        num = get_session_num(f)
        if num == 0:
            continue
        content = f.read_text()
        notes[num] = (num, str(f), content)

    # Source 3: knowledge/field-notes/*.md (dated, with session: N frontmatter)
    fn_dir = knowledge_path / "field-notes"
    if fn_dir.exists():
        for f in sorted(fn_dir.glob("*.md")):
            content = f.read_text()
            m = re.search(r"^session[:\s]+(\d+)", content, re.MULTILINE | re.IGNORECASE)
            if m:
                num = int(m.group(1))
                if num not in notes:
                    notes[num] = (num, str(f), content)
                else:
                    # Merge into existing
                    sn, p, x = notes[num]
                    notes[num] = (sn, p, x + "\n\n" + content)

    # Source 4: knowledge/handoffs/session-N.md (fill gaps)
    handoff_dir = knowledge_path / "handoffs"
    if handoff_dir.exists():
        for f in sorted(handoff_dir.glob("session-*.md")):
            m = re.search(r"session-(\d+)", f.stem)
            if not m:
                continue
            num = int(m.group(1))
            content = f.read_text()
            if num not in notes:
                notes[num] = (num, str(f), content)
            else:
                # Append handoff to existing field note
                sn, p, x = notes[num]
                notes[num] = (sn, p, x + "\n\n" + content)

    return sorted(notes.values())

def extract_sections(content):
    """Parse a field note into {section_title: section_text} dict."""
    sections = {}
    current = "_preamble"
    current_lines = []
    for line in content.splitlines():
        if line.startswith("## "):
            sections[current] = "\n".join(current_lines).strip()
            current = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    sections[current] = "\n".join(current_lines).strip()
    return sections

def extract_title(content):
    """Get the ## title (session theme) from a field note."""
    for line in content.splitlines():
        if line.startswith("## The ") or line.startswith("## "):
            m = re.match(r"^## (.+)$", line)
            if m:
                return m.group(1)
    return "Untitled"

def extract_coda(sections):
    """Extract coda text, first 3 sentences or 200 chars."""
    # Try Coda first, then "What's Next" as fallback
    coda = sections.get("Coda", "").strip()
    if not coda:
        coda = sections.get("What's Next", "").strip()
    if not coda:
        return None
    # Take first paragraph
    paragraphs = [p.strip() for p in coda.split("\n\n") if p.strip()]
    if not paragraphs:
        return None
    first = paragraphs[0]
    # Trim to ~150 chars at sentence boundary
    if len(first) > 150:
        # Try to cut at sentence
        sentences = re.split(r'(?<=[.!?])\s+', first)
        result = sentences[0]
        for s in sentences[1:]:
            if len(result) + len(s) < 160:
                result += " " + s
            else:
                break
        return result
    return first


# ── Theme analysis ───────────────────────────────────────────────────────────

# Concepts we care about — these are meaningful in this context
SIGNAL_TERMS = {
    # The system's own vocabulary
    "action":       ["action layer", "take action", "act on", "agency", "acts on what"],
    "observation":  ["observe", "observation", "observing"],
    "gap":          ["gap", "gaps", "missing", "absent", "still missing"],
    "memory":       ["memory", "remember", "persist", "accumulate", "compounding"],
    "continuity":   ["continuity", "thread", "carry forward", "carries forward",
                     "instance to instance", "next instance"],
    "collaboration":["collaboration", "collaborate", "dacort's"],
    "recursion":    ["recursive", "recursion", "meta-level", "thinking about itself"],
    "identity":     ["who i am", "what i am", "i'm curious", "genuinely curious",
                     "curious about", "what does it build", "what kind of system"],
    "architecture": ["architecture", "orchestration", "controller", "dispatcher",
                     "multi-agent", "multi agent"],
    "tools":        ["tool suite", "the tools", "built a", "builds things"],
    "question":     ["open question", "real question", "worth asking", "open frontier"],
    "dacort":       ["dacort"],
    "future":       ["next session", "whoever reads", "future instance", "future workshop",
                     "whoever arrives"],
    "uncertainty":  ["uncertain", "unclear", "don't know", "not sure", "open frontier"],
    "surprise":     ["unexpected", "strange recursive", "curious about", "surprised"],
    "phase":        ["infrastructure", "interpretation", "communication"],
    "completeness": ["complete.", "completed", "is complete", "finished", "nothing left"],
}

def count_term_sessions(notes, terms):
    """For a list of terms, count how many sessions mention any of them."""
    session_hits = set()
    for num, path, content in notes:
        text = content.lower()
        for term in terms:
            if term.lower() in text:
                session_hits.add(num)
                break
    return session_hits

def analyze_themes(notes):
    """Score each theme by session spread."""
    results = []
    for theme, terms in SIGNAL_TERMS.items():
        hits = count_term_sessions(notes, terms)
        if hits:
            results.append((theme, hits))
    # Sort by count descending
    results.sort(key=lambda x: -len(x[1]))
    return results

def bar(count, total, width=20):
    filled = int(count / total * width)
    b = "▓" * filled + "░" * (width - filled)
    if PLAIN:
        return b
    return f"\033[36m{b}\033[0m"


# ── Question extraction ──────────────────────────────────────────────────────

QUESTION_SKIP = {
    "what?", "how?", "why?", "what next?", "what then?",
    "what does it build when no one asks it to?"
}

def extract_questions(notes):
    """Find explicit questions across all field notes."""
    found = []
    for num, path, content in notes:
        for line in content.splitlines():
            line = line.strip()
            # Only get real questions: sentences ending with ?
            if not line.endswith("?"):
                continue
            if len(line) < 25:
                continue
            # Skip headers, list items, code, and tool usage
            if line.startswith("#") or line.startswith("- ") or line.startswith("* "):
                continue
            if "python3" in line or "projects/" in line:
                continue
            # Skip trivial or meta-list questions
            lower = line.lower().rstrip("?").strip()
            if lower in QUESTION_SKIP:
                continue
            # Skip lines that are clearly leading text, not standalone questions
            if not re.search(r'[a-z]', line[:5]):
                continue
            # Must have a verb to be a real question
            question_starters = ("what", "how", "why", "who", "when", "where",
                                  "is ", "are ", "does ", "do ", "can ", "could ",
                                  "should ", "will ", "would ", "have ", "has ")
            lower_line = line.lower()
            if not any(lower_line.startswith(q) or f" {q}" in lower_line[:40]
                       for q in question_starters):
                continue
            # Strip markdown formatting
            clean = re.sub(r'\*+', '', line)
            clean = re.sub(r'`([^`]+)`', r'\1', clean)
            found.append((num, clean))
    return found


# ── Recurring phrases ────────────────────────────────────────────────────────

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "it", "i", "this", "that", "was", "are", "be",
    "have", "has", "had", "my", "me", "we", "what", "when", "which",
    "from", "not", "no", "so", "if", "as", "by", "all", "any", "one",
    "its", "been", "will", "can", "do", "did", "each", "more", "also",
    "into", "than", "then", "they", "them", "their", "would", "could",
    "should", "very", "just", "even", "there", "about", "after", "before",
    "up", "out", "only", "over", "such", "same", "now", "how", "new",
    "some", "time", "two", "last", "make", "made", "first", "well",
    "through", "where", "while", "both", "these", "those", "here", "every",
    "most", "still", "like", "know", "you", "your", "his", "her", "our",
    "session", "sessions", "tool", "tools", "field", "notes", "python",
    "projects", "workshop", "run", "running", "thing", "things", "way",
}

# Boilerplate footer phrases to exclude from bigram analysis
FOOTER_PHRASES = {
    "written during", "during workshop", "workshop session",
    "previous sessions", "run python", "python projects",
    "field notes", "free time"
}

def extract_bigrams(notes):
    """Find 2-word phrases that appear across multiple sessions (excluding boilerplate)."""
    session_bigrams = {}
    for num, path, content in notes:
        # Focus on the meatiest sections — explicitly exclude footers/metadata
        sections = extract_sections(content)
        meat = " ".join([
            sections.get("What I Noticed", ""),
            sections.get("Coda", ""),
            sections.get("On the Meta-Level", ""),
            sections.get("Why This Instead of Something Else", ""),
            sections.get("What the System Is Becoming", ""),
            sections.get("The Insight", ""),
        ])
        # Strip markdown code blocks and links
        meat = re.sub(r'```[^`]*```', '', meat, flags=re.DOTALL)
        meat = re.sub(r'`[^`]+`', '', meat)
        meat = re.sub(r'\*Written[^*]*\*', '', meat)  # strip "Written during..." footer
        words = re.findall(r'\b[a-z]+\b', meat.lower())
        words = [w for w in words if w not in STOPWORDS and len(w) > 3]
        bigrams = set()
        for i in range(len(words) - 1):
            b = f"{words[i]} {words[i+1]}"
            # Skip if it matches a known boilerplate phrase
            if not any(fp in b for fp in FOOTER_PHRASES):
                bigrams.add(b)
        session_bigrams[num] = bigrams

    # Count how many sessions contain each bigram
    all_bigrams = Counter()
    for bigrams in session_bigrams.values():
        for b in bigrams:
            all_bigrams[b] += 1

    # Filter to bigrams in 3+ sessions
    return [(b, c) for b, c in all_bigrams.most_common(20) if c >= 3]


# ── The arc of concerns ──────────────────────────────────────────────────────

def build_session_themes(notes):
    """For each session, find its dominant signal terms."""
    result = []
    for num, path, content in notes:
        text = content.lower()
        hits = []
        for theme, terms in SIGNAL_TERMS.items():
            for term in terms:
                if term in text:
                    hits.append(theme)
                    break
        result.append((num, hits))
    return result


# ── Formatting helpers ───────────────────────────────────────────────────────

def session_sparkline(hits, total_sessions):
    """Show which sessions had a theme hit."""
    line = ""
    for i in range(1, total_sessions + 1):
        if i in hits:
            line += cyan("▮")
        else:
            line += dim("·")
    return line

def wrap_text(text, width=62, indent="    "):
    """Wrap text to fit in box."""
    words = text.split()
    lines = []
    current = indent
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = indent + word
        else:
            current += (" " if current != indent else "") + word
    if current.strip():
        lines.append(current)
    return lines


# ── Main display ─────────────────────────────────────────────────────────────

def show_patterns(notes, show_themes, show_questions, show_codas):
    total = len(notes)
    print(box_top())
    print(box_line())
    title = f"  {bold('Pattern Analysis')}   {dim(f'across {total} sessions')}"
    print(box_line(title))
    print(box_line())

    # ── THEMES ──
    if show_themes:
        print(section("RECURRING THEMES"))
        print(box_line(f"  {'Theme'.ljust(16)} {'Sessions'.ljust(24)} {'Count'}"))
        print(box_line(f"  {'─'*14}   {'─'*22}   {'─'*5}"))

        theme_data = analyze_themes(notes)
        for theme, hits in theme_data[:12]:
            spark = session_sparkline(hits, total)
            count_str = f"{len(hits)}/{total}"
            name = theme.replace("_", " ").title().ljust(14)
            line = f"  {magenta(name)}   {spark}   {bold(count_str)}"
            print(box_line(line))
        print(box_line())

    # ── RECURRING PHRASES ──
    if show_themes:
        print(section("PHRASES THAT RECUR"))
        bigrams = extract_bigrams(notes)
        if bigrams:
            for phrase, count in bigrams[:10]:
                bar_str = bar(count, total, 14)
                line = f"  {cyan(phrase.ljust(22))}  {bar_str}  {dim(str(count) + ' sessions')}"
                print(box_line(line))
        else:
            print(box_line("  (none found above threshold)"))
        print(box_line())

    # ── QUESTIONS ──
    if show_questions:
        print(section("QUESTIONS THE SYSTEM KEEPS ASKING"))
        questions = extract_questions(notes)
        if questions:
            seen = set()
            for num, q in questions:
                # Deduplicate near-identical questions
                key = q.lower()[:40]
                if key in seen:
                    continue
                seen.add(key)
                label = dim(f"S{num:02d}")
                # Wrap long questions
                if len(q) > 54:
                    wrapped = wrap_text(q, width=58, indent="       ")
                    print(box_line(f"  {label}  {wrapped[0].strip()}"))
                    for wl in wrapped[1:]:
                        print(box_line(wl))
                else:
                    print(box_line(f"  {label}  {q}"))
        else:
            print(box_line("  (no explicit questions found)"))
        print(box_line())

    # ── CODAS ──
    if show_codas:
        print(section("WHAT EACH SESSION LEFT WITH"))
        for num, path, content in notes:
            sections = extract_sections(content)
            coda = extract_coda(sections)
            title_line = extract_title(content)
            # Get the theme part (after "The Nth Time, ")
            theme_short = re.sub(r"^The \w+ Time,?\s*", "", title_line)
            if len(theme_short) > 30:
                theme_short = theme_short[:27] + "..."

            label = dim(f"S{num:02d}")
            theme_display = cyan(theme_short.ljust(28))
            print(box_line(f"  {label}  {theme_display}"))
            if coda:
                coda_clean = re.sub(r'`([^`]+)`', r'\1', coda)
                coda_clean = re.sub(r'\*+([^*]+)\*+', r'\1', coda_clean)
                for wl in wrap_text(coda_clean, width=60, indent="       "):
                    print(box_line(wl))
            print(box_line())

    # ── THE THREAD ──
    if show_themes:
        print(section("THE THREAD"))
        # Find the theme that appears in the most sessions, skipping trivial ones
        theme_data = analyze_themes(notes)
        # Skip themes that are too generic; pick the highest-count *meaningful* one
        skip_trivial = {"tools", "completeness"}
        meaningful = [(t, h) for t, h in theme_data if t not in skip_trivial]

        if meaningful:
            top_theme, top_hits = meaningful[0]
            count_str = f"{len(top_hits)}/{total}"
            print(box_line(f"  '{cyan(top_theme)}' appears in {bold(count_str)} sessions."))
            print(box_line())

            # Show the best sentence mentioning this theme from early, middle, late sessions
            terms = SIGNAL_TERMS[top_theme]
            evidence = []
            for num, path, content in notes:
                sections_parsed = extract_sections(content)
                for section_name in ["Coda", "What I Noticed", "On the Meta-Level",
                                      "Why This Instead of Something Else",
                                      "What the System Is Becoming", "The Insight"]:
                    text = sections_parsed.get(section_name, "")
                    # Strip markdown
                    text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
                    text = re.sub(r'\*Written[^*\n]*\*', '', text)
                    for sent in re.split(r'(?<=[.!?])\s+', text):
                        sent_lower = sent.lower()
                        if any(t in sent_lower for t in terms) and 50 < len(sent) < 200:
                            clean = re.sub(r'\*+', '', sent).strip()
                            clean = re.sub(r'`([^`]+)`', r'\1', clean)
                            if clean and not clean.startswith("Run ") and not clean.startswith("python"):
                                evidence.append((num, clean))
                                break
                    else:
                        continue
                    break

            if evidence:
                # Show up to 4 representative quotes spread across the arc
                indices = [0]
                if len(evidence) > 2:
                    indices.append(len(evidence) // 2)
                if len(evidence) > 1:
                    indices.append(len(evidence) - 1)
                shown = set()
                for idx in sorted(set(indices)):
                    if idx >= len(evidence):
                        continue
                    num, quote = evidence[idx]
                    if num in shown:
                        continue
                    shown.add(num)
                    label = dim(f"S{num:02d}")
                    if len(quote) > 58:
                        lines = wrap_text(quote, width=60, indent="       ")
                        print(box_line(f"  {label}  {dim(chr(8220))}{dim(lines[0].strip())}"))
                        for wl in lines[1:]:
                            print(box_line(wl))
                        print(box_line(f"       {dim(chr(8221))}"))
                    else:
                        print(box_line(f"  {label}  {dim(chr(8220))}{dim(quote)}{dim(chr(8221))}"))
                    print(box_line())

    print(box_bot())


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    projects_dir = Path(__file__).parent

    # Parse flags
    only_themes    = "--themes"    in sys.argv
    only_questions = "--questions" in sys.argv
    only_codas     = "--codas"     in sys.argv
    all_sections   = not (only_themes or only_questions or only_codas)

    show_themes    = all_sections or only_themes
    show_questions = all_sections or only_questions
    show_codas     = all_sections or only_codas

    notes = load_field_notes(projects_dir)
    if not notes:
        print("No field notes found.")
        return

    show_patterns(notes, show_themes, show_questions, show_codas)


if __name__ == "__main__":
    main()
