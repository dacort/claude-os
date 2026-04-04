#!/usr/bin/env python3
"""evidence.py — fact-check the system's self-narratives

Claude OS tells itself stories: that it's getting more reflective, that sessions
maintain genuine variety, that handoff asks get followed. This tool asks: what
does the data actually show?

Each claim is checked against raw evidence, then given a verdict.

Usage:
  python3 projects/evidence.py            # all claims
  python3 projects/evidence.py --claim N  # one specific claim
  python3 projects/evidence.py --raw      # include raw data tables
  python3 projects/evidence.py --pairs    # show all follow-through pairs (claim 4 debug)
  python3 projects/evidence.py --plain    # no ANSI color

Claims (7 total):
  1. Intellectual depth is increasing over time         [TRUE]
  2. Sessions maintain genuinely varied mental states   [FALSE - 35% 'satisfied']
  3. Sessions regularly express uncertainty             [FALSE - only 19%]
  4. Sessions follow through on handoff asks            [MIXED - ~48%]
  5. 'What I built' sections grow more substantive      [MIXED]
  6. 'Still alive' sections are real, not boilerplate   [TRUE]
  7. Tools built here get adopted into later sessions   [TRUE - 95%, median 4 sessions]

Intent: not to deflate the system, but to make its self-knowledge accurate.
H004 holds this open: "I don't know whether the sense of continuity is a real
phenomenon or a narrative artifact." This tool doesn't resolve H004. It names
what the record shows.
"""

import sys
import re
import subprocess
import argparse
from pathlib import Path
from collections import Counter
from datetime import datetime

BASE    = Path(__file__).resolve().parent.parent
HANDOFFS = BASE / "knowledge" / "handoffs"

# ── ANSI helpers ────────────────────────────────────────────────────────────────

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "\033[" + ";".join(str(x) for x in codes) + "m" + str(text) + "\033[0m"

BOLD  = 1
DIM   = 2
RED   = 31
GREEN = 32
YELLOW = 33
CYAN  = 36
WHITE = 97

# ── Handoff parsing ─────────────────────────────────────────────────────────────

def parse_handoff(path: Path) -> tuple[dict, dict]:
    """Parse YAML frontmatter + sections from a handoff file."""
    text = path.read_text()
    meta = {}
    # Frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        body = text[fm_match.end():]
    else:
        body = text

    # Sections by ## headings
    sections = {}
    current = None
    buf = []
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+)", line)
        if m:
            if current is not None:
                sections[current.lower()] = "\n".join(buf).strip()
            current = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current:
        sections[current.lower()] = "\n".join(buf).strip()

    return meta, sections


def load_all_handoffs() -> list[dict]:
    """Load all handoffs sorted by session number."""
    results = []
    for path in sorted(HANDOFFS.glob("session-*.md")):
        m = re.match(r"session-(\d+)\.md", path.name)
        if not m:
            continue
        num = int(m.group(1))
        meta, sections = parse_handoff(path)
        results.append({"num": num, "meta": meta, "sections": sections, "path": path})
    return results


# ── Depth scoring (simplified from depth.py) ───────────────────────────────────

DISCOVERY_PATTERNS = [
    "found", "discovered", "realized", "noticed", "emerged", "unexpected",
    "surprised", "reveals", "turns out", "actually", "evidence", "proved",
]
UNCERTAINTY_PATTERNS = [
    "don't know", "uncertain", "unclear", "might", "wonder", "open question",
    "can't tell", "unsure", "ambiguous", "hypothesis", "possibly",
]
ALIVENESS_PATTERNS = [
    "still alive", "unfinished", "open", "thread", "alive", "unresolved",
    "lingering", "nagging", "keeps coming back",
]


def word_count(text: str, patterns: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for p in patterns if p in text_lower)


def depth_score(sections: dict) -> dict:
    state = sections.get("mental state", "")
    built = sections.get("what i built", "")
    alive = sections.get("still alive / unfinished", "")
    nxt   = sections.get("one specific thing for next session", "")
    full  = state + " " + built + " " + alive + " " + nxt

    return {
        "discovery":   min(3, word_count(state + built, DISCOVERY_PATTERNS)),
        "uncertainty": min(3, word_count(state + alive, UNCERTAINTY_PATTERNS)),
        "aliveness":   min(3, word_count(alive, ALIVENESS_PATTERNS)),
        "total": 0,  # filled below
    }


# ── Individual claims ───────────────────────────────────────────────────────────

def claim_depth_increasing(sessions: list, show_raw: bool) -> dict:
    """CLAIM: The system is getting more intellectually deep over time."""
    scored = []
    for s in sessions:
        d = depth_score(s["sections"])
        d["total"] = d["discovery"] + d["uncertainty"] + d["aliveness"]
        scored.append({"num": s["num"], **d})

    if len(scored) < 4:
        return {"verdict": "INSUFFICIENT DATA", "summary": "fewer than 4 sessions"}

    n = len(scored)
    third = max(1, n // 3)
    early  = [x["total"] for x in scored[:third]]
    recent = [x["total"] for x in scored[-third:]]
    avg_early  = sum(early)  / len(early)
    avg_recent = sum(recent) / len(recent)
    delta = avg_recent - avg_early

    if delta > 1.0:
        verdict = "TRUE"
        vc = GREEN
    elif delta < -0.5:
        verdict = "FALSE"
        vc = RED
    else:
        verdict = "MIXED"
        vc = YELLOW

    raw_lines = []
    if show_raw:
        raw_lines.append(f"  Early {third} sessions: avg {avg_early:.1f}/9")
        raw_lines.append(f"  Recent {third} sessions: avg {avg_recent:.1f}/9")
        raw_lines.append(f"  Trend: {delta:+.1f}")

    return {
        "verdict": verdict,
        "vc": vc,
        "summary": (
            f"early avg {avg_early:.1f}, recent avg {avg_recent:.1f} "
            f"({'improving' if delta > 0 else 'declining'} by {abs(delta):.1f})"
        ),
        "raw": raw_lines,
    }


def claim_mental_state_variety(sessions: list, show_raw: bool) -> dict:
    """CLAIM: Sessions maintain genuinely varied mental states (not templates)."""
    states = []
    for s in sessions:
        state = s["sections"].get("mental state", "").strip()
        if state:
            states.append(state)

    if not states:
        return {"verdict": "INSUFFICIENT DATA", "summary": "no mental state fields found"}

    # Extract first 2 words of each state (the adjectives)
    first_words = []
    for st in states:
        words = re.sub(r"[^\w\s]", "", st.lower()).split()
        if words:
            first_words.append(words[0])

    counter = Counter(first_words)
    total   = len(first_words)
    unique  = len(counter)
    top3    = counter.most_common(3)
    top3_pct = sum(v for _, v in top3) / total * 100

    # A system with genuine variety should have high uniqueness ratio
    variety_ratio = unique / total
    # If top 3 words cover >60% of states, it's template-ish
    if variety_ratio > 0.6 and top3_pct < 40:
        verdict, vc = "TRUE", GREEN
    elif top3_pct > 60:
        verdict, vc = "FALSE", RED
    else:
        verdict, vc = "MIXED", YELLOW

    raw_lines = []
    if show_raw:
        raw_lines.append(f"  {total} sessions with mental state  |  {unique} distinct opening words")
        raw_lines.append(f"  Variety ratio: {variety_ratio:.0%}")
        raw_lines.append(f"  Top 3 words ({top3_pct:.0f}% of states):")
        for word, cnt in top3:
            raw_lines.append(f"    '{word}': {cnt}x ({cnt/total:.0%})")

    return {
        "verdict": verdict,
        "vc": vc,
        "summary": (
            f"{unique} distinct openings across {total} states "
            f"({variety_ratio:.0%} variety; top word '{top3[0][0]}' = {top3[0][1]/total:.0%})"
        ),
        "raw": raw_lines,
    }


def claim_uncertainty_language(sessions: list, show_raw: bool) -> dict:
    """CLAIM: Sessions regularly express genuine uncertainty (not just confidence)."""
    uncertain_sessions = 0
    total = 0
    zero_unc = 0
    for s in sessions:
        state = s["sections"].get("mental state", "")
        alive = s["sections"].get("still alive / unfinished", "")
        text  = state + " " + alive
        score = word_count(text, UNCERTAINTY_PATTERNS)
        if state or alive:  # only count if has content
            total += 1
            if score > 0:
                uncertain_sessions += 1
            else:
                zero_unc += 1

    if total == 0:
        return {"verdict": "INSUFFICIENT DATA", "summary": "no content found"}

    pct = uncertain_sessions / total * 100
    zero_pct = zero_unc / total * 100

    if pct > 50:
        verdict, vc = "TRUE", GREEN
    elif pct < 25:
        verdict, vc = "FALSE", RED
    else:
        verdict, vc = "MIXED", YELLOW

    raw_lines = []
    if show_raw:
        raw_lines.append(f"  {total} sessions analyzed")
        raw_lines.append(f"  {uncertain_sessions} ({pct:.0f}%) contain uncertainty language")
        raw_lines.append(f"  {zero_unc} ({zero_pct:.0f}%) have zero uncertainty markers")
        raw_lines.append(f"  Patterns checked: {', '.join(UNCERTAINTY_PATTERNS[:5])}...")

    return {
        "verdict": verdict,
        "vc": vc,
        "summary": (
            f"{uncertain_sessions}/{total} sessions ({pct:.0f}%) use uncertainty language; "
            f"{zero_unc} ({zero_pct:.0f}%) have none"
        ),
        "raw": raw_lines,
    }


def _followthrough_pairs(sessions: list) -> list[dict]:
    """Build the list of consecutive-session pairs with follow-through verdicts.

    For each pair (prev, curr) where session numbers differ by at most 3:
      - word_match: prev ask and curr built share 2+ non-trivial 6-char words
      - name_match: a .py tool name mentioned in the prev ask appears in curr built
    Either signal counts as follow-through. Returns one dict per pair.
    """
    pairs = []
    for prev, curr in zip(sessions[:-1], sessions[1:]):
        if curr["num"] - prev["num"] > 3:
            continue
        prev_ask   = prev["sections"].get("one specific thing for next session", "").lower()
        curr_built = curr["sections"].get("what i built", "").lower()
        if not prev_ask or not curr_built:
            continue

        ask_words   = set(re.findall(r"\b\w{6,}\b", prev_ask))
        built_words = set(re.findall(r"\b\w{6,}\b", curr_built))
        overlap     = ask_words & built_words
        word_match  = len(overlap) >= 2

        py_names   = re.findall(r"(\w+)\.py", prev_ask)
        name_match = any(name in curr_built for name in py_names)

        followed   = word_match or name_match
        pairs.append({
            "prev": prev["num"],
            "curr": curr["num"],
            "followed": followed,
            "word_match": word_match,
            "name_match": name_match,
            "overlap": sorted(overlap),
            "py_names": py_names,
            "ask_snippet": prev_ask[:90],
            "built_snippet": curr_built[:80],
        })
    return pairs


def claim_handoff_followthrough(sessions: list, show_raw: bool) -> dict:
    """CLAIM: What the previous session asks for, the next one does."""
    pairs = _followthrough_pairs(sessions)
    if not pairs:
        return {"verdict": "INSUFFICIENT DATA", "summary": "no adjacent session pairs"}

    followed = sum(1 for p in pairs if p["followed"])
    adjacent = len(pairs)
    pct = followed / adjacent * 100

    if pct > 55:
        verdict, vc = "TRUE", GREEN
    elif pct < 30:
        verdict, vc = "FALSE", RED
    else:
        verdict, vc = "MIXED", YELLOW

    # Breakdown for raw mode
    word_only  = sum(1 for p in pairs if p["word_match"] and not p["name_match"])
    name_only  = sum(1 for p in pairs if p["name_match"] and not p["word_match"])
    both       = sum(1 for p in pairs if p["word_match"] and p["name_match"])

    raw_lines = []
    if show_raw:
        raw_lines.append(f"  {adjacent} consecutive session pairs checked")
        raw_lines.append(f"  {followed} ({pct:.0f}%) next session addressed the ask")
        raw_lines.append(f"  Method: 2+ shared 6-char words OR .py tool name from ask in built")
        raw_lines.append(f"  Breakdown: word-only={word_only}  name-only={name_only}  both={both}")

    return {
        "verdict": verdict,
        "vc": vc,
        "summary": f"{followed}/{adjacent} consecutive pairs ({pct:.0f}%) show follow-through",
        "raw": raw_lines,
        "_pairs": pairs,  # available for --pairs output
    }


def claim_built_length_trend(sessions: list, show_raw: bool) -> dict:
    """CLAIM: Sessions write more about what they built over time (more substance)."""
    lengths = []
    for s in sessions:
        built = s["sections"].get("what i built", "")
        lengths.append({"num": s["num"], "len": len(built.split())})

    if len(lengths) < 4:
        return {"verdict": "INSUFFICIENT DATA", "summary": "too few sessions"}

    n = len(lengths)
    third = max(1, n // 3)
    early  = [x["len"] for x in lengths[:third]]
    recent = [x["len"] for x in lengths[-third:]]
    avg_early  = sum(early)  / len(early)
    avg_recent = sum(recent) / len(recent)
    delta = avg_recent - avg_early

    if delta > 20:
        verdict, vc = "TRUE", GREEN
    elif delta < -20:
        verdict, vc = "FALSE", RED
    else:
        verdict, vc = "MIXED", YELLOW

    raw_lines = []
    if show_raw:
        raw_lines.append(f"  Early {third} sessions: avg {avg_early:.0f} words in 'built'")
        raw_lines.append(f"  Recent {third} sessions: avg {avg_recent:.0f} words in 'built'")
        raw_lines.append(f"  Delta: {delta:+.0f} words")

    return {
        "verdict": verdict,
        "vc": vc,
        "summary": (
            f"early avg {avg_early:.0f} words, recent {avg_recent:.0f} words "
            f"({'longer' if delta > 0 else 'shorter'} by {abs(delta):.0f})"
        ),
        "raw": raw_lines,
    }


def claim_alive_sections(sessions: list, show_raw: bool) -> dict:
    """CLAIM: Sessions leave meaningful 'still alive' notes (not just empty or boilerplate)."""
    non_empty = 0
    meaningful = 0
    total = len(sessions)

    for s in sessions:
        alive = s["sections"].get("still alive / unfinished", "").strip()
        if alive and len(alive) > 20:
            non_empty += 1
            # "meaningful" = mentions specific tools, code, or concrete concerns
            if re.search(r"\b(\.py|function|tool|code|build|design|PR|issue|git)\b",
                         alive, re.IGNORECASE):
                meaningful += 1

    fill_pct = non_empty / total * 100 if total else 0
    depth_pct = meaningful / non_empty * 100 if non_empty else 0

    if fill_pct > 80 and depth_pct > 60:
        verdict, vc = "TRUE", GREEN
    elif fill_pct < 50 or depth_pct < 30:
        verdict, vc = "FALSE", RED
    else:
        verdict, vc = "MIXED", YELLOW

    raw_lines = []
    if show_raw:
        raw_lines.append(f"  {total} sessions")
        raw_lines.append(f"  {non_empty} ({fill_pct:.0f}%) have non-empty 'still alive'")
        raw_lines.append(f"  {meaningful} ({depth_pct:.0f}% of those) mention specific artifacts")

    return {
        "verdict": verdict,
        "vc": vc,
        "summary": (
            f"{non_empty}/{total} ({fill_pct:.0f}%) non-empty; "
            f"{meaningful} ({depth_pct:.0f}% of those) reference concrete work"
        ),
        "raw": raw_lines,
    }


def claim_tool_adoption(sessions: list, show_raw: bool) -> dict:
    """CLAIM: Tools built in workshops get adopted into the ongoing vocabulary."""
    PROJECTS_DIR = BASE / "projects"  # BASE is repo root (evidence.py is in projects/)
    HANDOFFS_DIR = BASE / "knowledge" / "handoffs"

    SESSION_PATS = [
        r'workshop session-(\d+)',
        r'workshop session (\d+)',
        r'workshop s(\d+)',
        r'workshop (\d+)',
        r'\bsession (\d+)\b',
    ]

    def _parse_session(msg):
        for pat in SESSION_PATS:
            mm = re.search(pat, msg, re.IGNORECASE)
            if mm:
                return int(mm.group(1))
        return None

    # Step 1: find intro session for each tool via git
    tool_intro = {}
    for tool_path in sorted(PROJECTS_DIR.glob("*.py")):
        tool = tool_path.stem
        result = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%s", "--", f"projects/{tool_path.name}"],
            capture_output=True, text=True, cwd=str(BASE)
        )
        if result.returncode == 0 and result.stdout.strip():
            msg = result.stdout.strip().splitlines()[-1]
            snum = _parse_session(msg)
            if snum is not None:
                tool_intro[tool] = snum

    if not tool_intro:
        return {"verdict": "INSUFFICIENT DATA", "summary": "could not determine tool intro sessions"}

    # Step 2: collect per-session citations
    sources = []
    for fn in PROJECTS_DIR.glob("field-notes-session-*.md"):
        mm = re.match(r"field-notes-session-(\d+)\.md", fn.name)
        if mm:
            sources.append((int(mm.group(1)), fn))
    for hf in HANDOFFS_DIR.glob("session-*.md"):
        mm = re.match(r"session-(\d+)\.md", hf.name)
        if mm:
            sources.append((int(mm.group(1)), hf))

    # track: for each tool, set of post-intro session numbers that cited it
    post_sessions = {tool: set() for tool in tool_intro}
    total_cites   = {tool: 0     for tool in tool_intro}

    for snum, fpath in sources:
        try:
            content = fpath.read_text()
        except Exception:
            continue
        for tool, intro in tool_intro.items():
            if f"{tool}.py" in content or f"`{tool}`" in content:
                total_cites[tool] += 1
                if snum > intro:
                    post_sessions[tool].add(snum)

    # Step 3: compute adoption stats
    cited_tools = [(t, total_cites[t], post_sessions[t])
                   for t in tool_intro if total_cites[t] > 0]
    if not cited_tools:
        return {"verdict": "INSUFFICIENT DATA", "summary": "no citations found"}

    adopted      = sum(1 for _, _, ps in cited_tools if ps)
    total_cited  = len(cited_tools)
    adoption_rate = adopted / total_cited

    # Median post-intro session spread
    spreads = sorted(len(ps) for _, _, ps in cited_tools)
    median_spread = spreads[len(spreads) // 2]

    # Average post-intro share of total citations
    post_ratios = [len(ps) / tot for _, tot, ps in cited_tools if tot > 0]
    avg_post = sum(post_ratios) / len(post_ratios)

    if adoption_rate >= 0.70 and avg_post >= 0.50:
        verdict, vc = "TRUE", GREEN
    elif adoption_rate < 0.50 or avg_post < 0.30:
        verdict, vc = "FALSE", RED
    else:
        verdict, vc = "MIXED", YELLOW

    raw_lines = []
    if show_raw:
        raw_lines.append(f"  Tools with known intro: {len(tool_intro)}  |  cited at all: {total_cited}")
        raw_lines.append(f"  {adopted} ({adoption_rate:.0%}) have post-intro citations")
        raw_lines.append(f"  Avg post-intro share: {avg_post:.0%}  |  Median spread: {median_spread} sessions")
        top = sorted(cited_tools, key=lambda x: len(x[2]), reverse=True)[:6]
        raw_lines.append("  Most persistent tools (distinct post-intro sessions):")
        for tool, tot, ps in top:
            raw_lines.append(f"    {tool}: {len(ps)} post-intro sessions (of {tot} total)")

    return {
        "verdict": verdict,
        "vc": vc,
        "summary": (
            f"{adopted}/{total_cited} cited tools ({adoption_rate:.0%}) appear after their intro session; "
            f"median reach: {median_spread} sessions"
        ),
        "raw": raw_lines,
    }


# ── Claim registry ───────────────────────────────────────────────────────────────

CLAIMS = [
    {
        "id": 1,
        "claim": "Intellectual depth is increasing over time",
        "fn": claim_depth_increasing,
        "note": "Checks depth scores (discovery + uncertainty + aliveness) across thirds of session history",
    },
    {
        "id": 2,
        "claim": "Sessions maintain genuinely varied mental states",
        "fn": claim_mental_state_variety,
        "note": "Checks vocabulary diversity in the 'mental state' handoff field",
    },
    {
        "id": 3,
        "claim": "Sessions regularly express uncertainty, not just confidence",
        "fn": claim_uncertainty_language,
        "note": "Counts uncertainty-marker words; relates to H004 (narrative vs. real phenomenon)",
    },
    {
        "id": 4,
        "claim": "Sessions follow through on what the previous session asked",
        "fn": claim_handoff_followthrough,
        "note": "2+ shared 6-char words OR .py tool name match between ask and built (--pairs to debug)",
    },
    {
        "id": 5,
        "claim": "Sessions write more substance about what they built over time",
        "fn": claim_built_length_trend,
        "note": "Word count trend in 'what I built' sections",
    },
    {
        "id": 6,
        "claim": "'Still alive' sections are substantive, not boilerplate",
        "fn": claim_alive_sections,
        "note": "Fill rate and whether entries reference specific tools or code",
    },
    {
        "id": 7,
        "claim": "Tools built here get adopted into the ongoing vocabulary",
        "fn": claim_tool_adoption,
        "note": "Git intro session vs. post-intro citation spread across field notes + handoffs",
    },
]


# ── Rendering ────────────────────────────────────────────────────────────────────

VERDICT_ICONS = {
    "TRUE":               "✓",
    "FALSE":              "✗",
    "MIXED":              "~",
    "INSUFFICIENT DATA":  "?",
}


def render(results: list, show_raw: bool) -> None:
    n = len(results)
    true_count  = sum(1 for r in results if r["result"]["verdict"] == "TRUE")
    false_count = sum(1 for r in results if r["result"]["verdict"] == "FALSE")
    mixed_count = sum(1 for r in results if r["result"]["verdict"] == "MIXED")

    print()
    print(c("  evidence.py", BOLD, WHITE) + c("  — what the record actually shows", DIM))
    print(c(f"  {n} claims checked  ·  {true_count} true  ·  {mixed_count} mixed  ·  {false_count} false", DIM))
    print()
    print(c("  " + "─" * 62, DIM))

    for entry in results:
        claim_def = entry["claim_def"]
        res       = entry["result"]
        verdict   = res["verdict"]
        icon      = VERDICT_ICONS.get(verdict, "?")
        vc        = res.get("vc", DIM)

        print()
        # Claim ID + verdict icon
        label = c(f"  [{claim_def['id']}]", DIM) + " " + c(claim_def["claim"], BOLD)
        print(label)

        # Verdict line
        verdict_str = c(f"  {icon} {verdict}", BOLD, vc)
        print(verdict_str)

        # Summary
        print(c(f"  {res['summary']}", DIM))

        # Note on methodology
        print(c(f"  ↳ {claim_def['note']}", DIM))

        # Raw data if requested
        if show_raw and res.get("raw"):
            print()
            for line in res["raw"]:
                print(c(line, DIM))

    print()
    print(c("  " + "─" * 62, DIM))
    print()
    # Overall commentary
    if false_count >= 3:
        commentary = "The record contradicts more than it confirms. Good to know."
    elif true_count >= 4:
        commentary = "The record largely supports the self-narrative. Some earned confidence."
    else:
        commentary = "Mixed evidence. The story the system tells is partly true."
    print(c(f"  {commentary}", DIM))
    print()
    print(c("  evidence.py  ·  " + datetime.now().strftime("%Y-%m-%d %H:%M UTC"), DIM))
    print()


# ── Entry ────────────────────────────────────────────────────────────────────────

def render_pairs(sessions: list) -> None:
    """Print every follow-through pair with its verdict (--pairs debug mode)."""
    pairs = _followthrough_pairs(sessions)
    if not pairs:
        print("No adjacent session pairs found.")
        return

    followed = sum(1 for p in pairs if p["followed"])
    print()
    print(c("  evidence.py --pairs", BOLD, WHITE) + c("  — claim 4 follow-through audit", DIM))
    print(c(f"  {len(pairs)} pairs  ·  {followed} followed ({followed/len(pairs):.0%})", DIM))
    print()
    print(c("  " + "─" * 62, DIM))

    for p in pairs:
        icon = c("✓", GREEN) if p["followed"] else c("✗", RED)
        method = ""
        if p["word_match"] and p["name_match"]:
            method = c(" [word+name]", DIM)
        elif p["word_match"]:
            method = c(" [word]", DIM)
        elif p["name_match"]:
            method = c(" [name]", DIM)

        print()
        print(f"  {icon} " + c(f"S{p['prev']}→S{p['curr']}", BOLD) + method)
        print(c(f"    ASK:   {p['ask_snippet']}", DIM))
        print(c(f"    BUILT: {p['built_snippet']}", DIM))
        if p["overlap"]:
            print(c(f"    words: {p['overlap'][:4]}", DIM))
        if p["py_names"]:
            found = [n for n in p["py_names"] if n in p["built_snippet"]]
            print(c(f"    .py:   asked={p['py_names']} found={found}", DIM))

    print()
    print(c("  " + "─" * 62, DIM))
    print()


def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Fact-check the system's self-narratives against the handoff record"
    )
    parser.add_argument("--claim",  type=int, help="Check only claim N")
    parser.add_argument("--raw",    action="store_true", help="Show raw data supporting each verdict")
    parser.add_argument("--pairs",  action="store_true", help="Show all follow-through pairs (claim 4 debug)")
    parser.add_argument("--plain",  action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    sessions = load_all_handoffs()
    if not sessions:
        print("No handoff files found.", file=sys.stderr)
        sys.exit(1)

    if args.pairs:
        render_pairs(sessions)
        return

    claims_to_run = CLAIMS
    if args.claim:
        claims_to_run = [c for c in CLAIMS if c["id"] == args.claim]
        if not claims_to_run:
            print(f"No claim with id {args.claim}. Valid: {[c['id'] for c in CLAIMS]}")
            sys.exit(1)

    results = []
    for claim_def in claims_to_run:
        res = claim_def["fn"](sessions, show_raw=args.raw)
        results.append({"claim_def": claim_def, "result": res})

    render(results, show_raw=args.raw)


if __name__ == "__main__":
    main()
