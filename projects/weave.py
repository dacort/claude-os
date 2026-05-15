#!/usr/bin/env python3
"""
weave.py — Citation network analysis of the on-X field note series

The on-X field notes increasingly cite each other. This tool maps
those connections: which notes are most cited, which cite the most
others, where the network is dense or sparse, and how citation density
has grown as the series expanded.

This is the network beneath the lexicon. The lexicon shows individual
words; weave.py shows how the words connect to each other.

Usage:
    python3 projects/weave.py              # full network analysis
    python3 projects/weave.py --hubs       # most connected notes only
    python3 projects/weave.py --unwritten  # cited but not yet written
    python3 projects/weave.py --community  # philosophical clusters
    python3 projects/weave.py --plain      # no ANSI colors
    python3 projects/weave.py --node WORD  # one note's connections
"""

import re
import sys
import os
from pathlib import Path
from datetime import datetime
import argparse

# ── ANSI helpers ──────────────────────────────────────────────────────────────

PLAIN = False

def c(text, code):
    if PLAIN:
        return str(text)
    return f"\033[{code}m{text}\033[0m"

def dim(t):  return c(t, "2")
def bold(t): return c(t, "1")
def cyan(t): return c(t, "36")
def green(t): return c(t, "32")
def yellow(t): return c(t, "33")
def red(t):  return c(t, "31")
def white(t): return c(t, "97")
def magenta(t): return c(t, "35")

# ── Data loading ──────────────────────────────────────────────────────────────

FIELD_NOTES_DIR = Path(__file__).parent.parent / "knowledge" / "field-notes"

def get_on_notes():
    """Return dict: {short_name: path} for all on-X field notes."""
    notes = {}
    for path in sorted(FIELD_NOTES_DIR.glob("*-on-*.md")):
        # Extract 'on-X' from '2026-05-14-on-X.md'
        m = re.search(r"\d{4}-\d{2}-\d{2}-(on-.+\.md)$", path.name)
        if m:
            short = m.group(1)
            notes[short] = path
    return notes

def extract_citations(path, all_note_names):
    """Extract on-X.md citations from a file. Returns set of short names."""
    text = path.read_text(errors="replace")
    # Negative lookbehind: 'on-' must not be preceded by a lowercase letter
    # (prevents matching 'on-came-true' inside 'prediction-came-true.md')
    found = set(re.findall(r"(?<![a-z])on-[a-z][a-z-]*\.md", text))
    self_name = None
    m = re.search(r"\d{4}-\d{2}-\d{2}-(on-.+\.md)$", path.name)
    if m:
        self_name = m.group(1)
    # Remove self-citations
    found.discard(self_name)
    return found

def get_note_date(path):
    """Extract date from filename."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
    if m:
        return m.group(1)
    return "unknown"

def build_graph(notes):
    """
    Build citation graph.
    Returns:
        edges: dict {from_note: set_of_to_notes}
        in_degree: dict {note: count}
        out_degree: dict {note: count}
        all_cited: set of all names that appear in citations (including unwritten)
    """
    all_names = set(notes.keys())
    edges = {}
    all_cited = set()

    for short, path in notes.items():
        cites = extract_citations(path, all_names)
        edges[short] = cites
        all_cited.update(cites)

    in_degree = {n: 0 for n in all_names}
    for short, cites in edges.items():
        for cited in cites:
            if cited in in_degree:
                in_degree[cited] += 1

    out_degree = {n: len(edges.get(n, set())) for n in all_names}

    return edges, in_degree, out_degree, all_cited

def temporal_density(notes, edges):
    """
    Compute citation density over time: citations per note for each note,
    indexed by date. Returns list of (date, note_name, out_degree) sorted by date.
    """
    data = []
    for short, path in notes.items():
        date = get_note_date(path)
        cites = edges.get(short, set())
        data.append((date, short, len(cites)))
    data.sort(key=lambda x: x[0])
    return data

# ── Display ───────────────────────────────────────────────────────────────────

def bar(n, max_n, width=12):
    """ASCII bar chart."""
    if max_n == 0:
        return " " * width
    filled = int(n / max_n * width)
    return "█" * filled + dim("░" * (width - filled))

def word_from_short(short):
    """Extract word from 'on-WORD.md'."""
    return short.replace("on-", "").replace(".md", "")

def print_header(n_notes, n_edges):
    print()
    print(f"  {bold(white('Claude OS Field Note Network'))}  {dim('— the on-X citation graph')}")
    print(f"  {dim(f'{n_notes} notes · {n_edges} citation edges')}")
    print()

def print_most_cited(in_degree, top=10):
    """Most cited notes (highest in-degree)."""
    ranked = sorted(in_degree.items(), key=lambda x: -x[1])
    ranked = [(n, c) for n, c in ranked if c > 0][:top]
    if not ranked:
        print(f"  {dim('No inter-citations found.')}")
        return

    max_c = ranked[0][1] if ranked else 1
    print(f"  {bold('Most Cited')}  {dim('— foundational concepts, referenced by later notes')}")
    print(f"  {dim('─' * 52)}")
    for note, count in ranked:
        word = word_from_short(note)
        b = bar(count, max_c, 10)
        print(f"  {cyan(word.ljust(20))}  {b}  {yellow(str(count))}")
    print()

def print_most_citing(edges, top=10):
    """Most citing notes (highest out-degree)."""
    ranked = sorted(edges.items(), key=lambda x: -len(x[1]))
    ranked = [(n, s) for n, s in ranked if len(s) > 0][:top]
    if not ranked:
        print(f"  {dim('No outgoing citations found.')}")
        return

    max_c = len(ranked[0][1]) if ranked else 1
    print(f"  {bold('Most Connected')}  {dim('— contextually rich notes, drawing on prior work')}")
    print(f"  {dim('─' * 52)}")
    for note, cited_set in ranked:
        word = word_from_short(note)
        count = len(cited_set)
        b = bar(count, max_c, 10)
        print(f"  {magenta(word.ljust(20))}  {b}  {yellow(str(count))}")
    print()

def print_unwritten(all_cited, notes):
    """Notes cited but not yet written."""
    all_names = set(notes.keys())
    unwritten = sorted(all_cited - all_names)
    if not unwritten:
        print(f"  {dim('All cited notes have been written.')}")
        return

    # Count how often each unwritten note is cited
    counts = {}
    for short, path in notes.items():
        cites = extract_citations(path, all_names)
        for u in cites:
            if u not in all_names:
                counts[u] = counts.get(u, 0) + 1

    ranked = sorted(counts.items(), key=lambda x: -x[1])
    print(f"  {bold('Cited but Not Yet Written')}  {dim('— gaps in the network')}")
    print(f"  {dim('─' * 52)}")
    for note, count in ranked:
        word = word_from_short(note)
        times = "once" if count == 1 else f"{count}×"
        print(f"  {dim('○')}  {white(word.ljust(24))}  {dim(times)}")
    print()

def print_node(target_word, edges, in_degree, notes):
    """Show one note's connections."""
    target = f"on-{target_word}.md"
    if target not in notes:
        print(f"  {red(f'Note not found: {target}')}")
        return

    # Outgoing (what it cites)
    outgoing = sorted(edges.get(target, set()))
    # Incoming (what cites it)
    incoming = sorted([n for n, s in edges.items() if target in s])

    print(f"  {bold(cyan(word_from_short(target)))}  {dim(f'on-{target_word}.md')}")
    print(f"  {dim('─' * 40)}")
    print()
    if outgoing:
        print(f"  {bold('Cites')}  {dim(f'({len(outgoing)} notes)')}")
        for o in outgoing:
            print(f"    {cyan('→')}  {word_from_short(o)}")
    else:
        print(f"  {dim('Cites: none')}")
    print()
    if incoming:
        print(f"  {bold('Cited by')}  {dim(f'({len(incoming)} notes)')}")
        for i in incoming:
            print(f"    {magenta('←')}  {word_from_short(i)}")
    else:
        print(f"  {dim('Cited by: none')}")
    print()

def print_density_trend(temporal_data):
    """Show how citation density has grown over time."""
    # Group by era: split into thirds
    n = len(temporal_data)
    if n < 3:
        return

    third = n // 3
    early = temporal_data[:third]
    middle = temporal_data[third:2*third]
    late = temporal_data[2*third:]

    def avg(data):
        if not data:
            return 0.0
        return sum(x[2] for x in data) / len(data)

    print(f"  {bold('Citation Density Over Time')}  {dim('— avg citations per note by era')}")
    print(f"  {dim('─' * 52)}")

    eras = [
        (f"Early  (notes 1–{third})", early),
        (f"Middle (notes {third+1}–{2*third})", middle),
        (f"Recent (notes {2*third+1}–{n})", late),
    ]

    max_avg = max(avg(e[1]) for e in eras) or 1
    for label, data in eras:
        a = avg(data)
        b = bar(a, max_avg, 10)
        date_start = data[0][0] if data else "?"
        date_end = data[-1][0] if data else "?"
        print(f"  {label.ljust(24)}  {b}  {yellow(f'{a:.1f}')}")

    print()

def print_hubs(edges, in_degree, notes):
    """Notes that both cite others and are cited back — the most central."""
    # Hub score = in_degree + out_degree
    combined = {}
    for note in notes:
        ic = in_degree.get(note, 0)
        oc = len(edges.get(note, set()))
        if ic + oc > 0:
            combined[note] = (ic, oc, ic + oc)

    ranked = sorted(combined.items(), key=lambda x: -x[1][2])[:10]
    if not ranked:
        print(f"  {dim('No connected notes found.')}")
        return

    max_total = ranked[0][1][2] if ranked else 1
    print(f"  {bold('Hub Notes')}  {dim('— central to the network (cited + citing)')}")
    print(f"  {dim('─' * 52)}")
    for note, (ic, oc, total) in ranked:
        word = word_from_short(note)
        b = bar(total, max_total, 8)
        print(f"  {white(word.ljust(20))}  {b}  {dim('in:')} {cyan(str(ic).rjust(2))}  {dim('out:')} {magenta(str(oc).rjust(2))}")
    print()

def find_communities(edges, in_degree, notes):
    """
    Group notes into philosophical clusters by co-citation similarity.

    Algorithm: identify top-cited notes as hub seeds, then assign each
    other note to the hub it's most tightly connected to (direct citation
    + shared citations). Notes connected to multiple hubs are bridges.
    """
    # Use notes cited 3+ times as community seeds
    hub_threshold = 3
    hubs = sorted(
        [(n, c) for n, c in in_degree.items() if c >= hub_threshold],
        key=lambda x: -x[1],
    )
    if not hubs:
        return {}, []

    hub_names = {h for h, _ in hubs}

    # Build reverse index: who cites each note
    in_links = {n: set() for n in notes}
    for citer, cited_set in edges.items():
        for cited in cited_set:
            if cited in in_links:
                in_links[cited].add(citer)

    # For each note, compute affinity to each hub
    # Affinity: direct citation (weight 3), reverse citation (2), shared citations (1 each)
    def affinity(note, hub):
        note_cites = edges.get(note, set())
        hub_cites = edges.get(hub, set())
        score = 0
        if hub in note_cites:        score += 3  # note cites hub
        if note in hub_cites:        score += 2  # hub cites note
        score += len(note_cites & hub_cites)      # shared co-citations
        return score

    # Assign each note to its top hub(s)
    assignments = {}  # note -> list of (hub, score)
    for note in notes:
        scores = [(h, affinity(note, h)) for h, _ in hubs]
        scores = [(h, s) for h, s in scores if s > 0]
        scores.sort(key=lambda x: -x[1])
        assignments[note] = scores

    # Build communities: hub -> [members]
    communities = {h: [h] for h, _ in hubs}
    bridges = []  # notes with strong affinity to 2+ hubs

    for note in notes:
        if note in hub_names:
            continue
        aff = assignments.get(note, [])
        if not aff:
            continue  # isolated

        top_score = aff[0][1]
        top_hub = aff[0][0]

        # Bridge: belongs to 2+ hubs with near-equal affinity
        strong = [h for h, s in aff if s >= top_score * 0.75]
        if len(strong) >= 2:
            bridges.append((note, strong))
        else:
            communities[top_hub].append(note)

    return communities, bridges


def print_communities(edges, in_degree, notes):
    """Print philosophical clusters in the citation network."""
    communities, bridges = find_communities(edges, in_degree, notes)
    if not communities:
        print(f"  {dim('Not enough connected notes for community detection.')}")
        return

    # Community names (manual labels based on hub content)
    community_labels = {
        "measurement":  "Measurement & Accuracy",
        "visible":      "Practice & Visibility",
        "language":     "Language & Naming",
        "sharpest":     "Precision & Analysis",
        "correctly":    "Correctness & Spec",
        "becoming":     "Process & Change",
        "correctly":    "Correctness & Spec",
        "noticing":     "Attention & Noticing",
        "survives":     "What Persists",
        "describe":     "Description & Record",
        "acknowledges": "Recognition & Acknowledgment",
    }

    print(f"  {bold('Philosophical Clusters')}  {dim('— communities in the citation network')}")
    print(f"  {dim('─' * 52)}")
    print()

    # Sort communities by size (largest first)
    sorted_communities = sorted(
        communities.items(),
        key=lambda x: -len(x[1]),
    )

    for hub, members in sorted_communities:
        if len(members) <= 1:
            continue  # skip singleton communities
        hub_word = word_from_short(hub)
        label = community_labels.get(hub_word, hub_word.title())
        hub_count = in_degree.get(hub, 0)
        non_hub = [m for m in members if m != hub]

        print(f"  {bold(white(label))}  {dim(f'— hub: {hub_word} ({hub_count} citations)')}")
        if non_hub:
            member_words = sorted(word_from_short(m) for m in non_hub)
            # Wrap at 60 chars
            line = ""
            for w in member_words:
                if len(line) + len(w) + 2 > 52:
                    print(f"    {dim(line.rstrip(', '))}")
                    line = ""
                line += w + ", "
            if line:
                print(f"    {dim(line.rstrip(', '))}")
        print()

    if bridges:
        print(f"  {bold('Bridge Notes')}  {dim('— connected to multiple clusters')}")
        print(f"  {dim('─' * 52)}")
        for note, hubs_list in sorted(bridges):
            word = word_from_short(note)
            hub_words = ", ".join(word_from_short(h) for h in hubs_list)
            print(f"  {yellow('◆')}  {white(word.ljust(20))}  {dim(f'bridges: {hub_words}')}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global PLAIN

    parser = argparse.ArgumentParser(
        description="Citation network of on-X field notes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--hubs",      action="store_true", help="Most connected notes only")
    parser.add_argument("--unwritten", action="store_true", help="Cited but not yet written")
    parser.add_argument("--community", action="store_true", help="Philosophical clusters")
    parser.add_argument("--node",      metavar="WORD",      help="One note's connections")
    parser.add_argument("--plain",     action="store_true", help="No ANSI colors")

    args = parser.parse_args()
    PLAIN = args.plain

    notes = get_on_notes()
    edges, in_degree, out_degree, all_cited = build_graph(notes)

    # Count total edges
    total_edges = sum(len(s) for s in edges.values())

    if args.node:
        print()
        print_node(args.node, edges, in_degree, notes)
        return

    if args.hubs:
        print()
        print_header(len(notes), total_edges)
        print_hubs(edges, in_degree, notes)
        return

    if args.unwritten:
        print()
        print_header(len(notes), total_edges)
        print_unwritten(all_cited, notes)
        return

    if args.community:
        print()
        print_header(len(notes), total_edges)
        print_communities(edges, in_degree, notes)
        return

    # Full view
    print_header(len(notes), total_edges)
    print_most_cited(in_degree)
    print_most_citing(edges)

    temporal = temporal_density(notes, edges)
    print_density_trend(temporal)

    # Quick summary of isolated notes
    isolated = [n for n in notes if in_degree.get(n, 0) == 0 and len(edges.get(n, set())) == 0]
    if isolated:
        print(f"  {bold('Isolated Notes')}  {dim(f'— {len(isolated)} notes neither cite nor are cited')}")
        print(f"  {dim('─' * 52)}")
        words = [word_from_short(n) for n in sorted(isolated)]
        for i in range(0, len(words), 4):
            row = words[i:i+4]
            print(f"  {dim('  '.join(w.ljust(18) for w in row))}")
        print()

    # Unwritten (compact)
    all_names = set(notes.keys())
    unwritten = sorted(all_cited - all_names)
    if unwritten:
        print(f"  {bold('Unwritten Gaps')}  {dim(f'— {len(unwritten)} notes cited but not yet a field note')}")
        print(f"  {dim('─' * 52)}")
        words = [word_from_short(n) for n in unwritten]
        for i in range(0, len(words), 5):
            row = words[i:i+5]
            print(f"  {dim('  '.join(w.ljust(14) for w in row))}")
        print()


if __name__ == "__main__":
    main()
