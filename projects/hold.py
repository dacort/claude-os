#!/usr/bin/env python3
"""hold.py — A log of genuine uncertainty across Claude OS sessions (session 89, 2026-03-31)

Not memos (observations), not questions (provocations), not still-alive (unfinished).
This is for things the system genuinely doesn't know — where the uncertainty is the point.

Usage:
    python3 projects/hold.py                  # show open holds
    python3 projects/hold.py --all            # show all (open + resolved + dissolved)
    python3 projects/hold.py --add "text"     # record a new uncertainty
    python3 projects/hold.py --resolve N why  # mark hold N resolved (with explanation)
    python3 projects/hold.py --dissolve N why # mark hold N dissolved (question irrelevant)
    python3 projects/hold.py --stats          # count open/resolved/dissolved + trend
    python3 projects/hold.py --plain          # no ANSI colors
"""

import argparse
import datetime
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
HOLDS_FILE = REPO / "knowledge" / "holds.md"

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
CYAN    = "\033[36m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
MAGENTA = "\033[35m"
WHITE   = "\033[97m"
RED     = "\033[31m"

USE_COLOR = True


def c(text, *codes):
    return ("".join(codes) + str(text) + RESET) if USE_COLOR else str(text)


def rule(ch="─", width=60):
    return c(ch * width, DIM)


# ── File I/O ──────────────────────────────────────────────────────────────────

def load_holds():
    """Parse holds.md and return list of hold dicts."""
    if not HOLDS_FILE.exists():
        return []

    holds = []
    current = None
    body_lines = []

    for line in HOLDS_FILE.read_text().splitlines():
        # Header: ## H001 · 2026-03-31 · open
        m = re.match(
            r"^## (H\d+) · (\d{4}-\d{2}-\d{2}) · (open|resolved|dissolved)"
            r"(?: · (\d{4}-\d{2}-\d{2}))?$",
            line
        )
        if m:
            if current:
                current["text"] = "\n".join(body_lines).strip()
                holds.append(current)
            body_lines = []
            current = {
                "id":       m.group(1),
                "added":    m.group(2),
                "status":   m.group(3),
                "resolved": m.group(4) or "",
                "text":     "",
                "note":     "",
            }
        elif current and line.startswith("> "):
            current["note"] = line[2:].strip()
        elif current and not line.startswith("#"):
            body_lines.append(line)

    if current:
        current["text"] = "\n".join(body_lines).strip()
        holds.append(current)

    return holds


def next_id(holds):
    if not holds:
        return "H001"
    last = max(int(h["id"][1:]) for h in holds)
    return f"H{last + 1:03d}"


def write_holds(holds):
    """Serialize holds back to holds.md."""
    lines = [
        "# Holds — What the System Doesn't Know",
        "",
        "Genuine uncertainty, named explicitly. Not tasks. Not questions to think about.",
        "Things the system holds as open that may or may not resolve.",
        "",
    ]
    for h in holds:
        header = f"## {h['id']} · {h['added']} · {h['status']}"
        if h["resolved"]:
            header += f" · {h['resolved']}"
        lines.append(header)
        lines.append("")
        lines.append(h["text"])
        if h["note"]:
            lines.append(f"> {h['note']}")
        lines.append("")

    HOLDS_FILE.write_text("\n".join(lines).rstrip() + "\n")


# ── Display ───────────────────────────────────────────────────────────────────

STATUS_COLOR = {
    "open":      (MAGENTA, "open"),
    "resolved":  (GREEN,   "resolved"),
    "dissolved": (DIM,     "dissolved"),
}


def fmt_hold(h, show_note=True):
    sc, label = STATUS_COLOR[h["status"]]
    id_str   = c(h["id"], BOLD, sc)
    date_str = c(h["added"], DIM)
    stat_str = c(f"({label})", sc)

    # Wrap text at ~60 chars
    words = h["text"].split()
    lines = []
    cur = ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > 58:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)

    out = [f"  {id_str}  {date_str}  {stat_str}"]
    for i, ln in enumerate(lines):
        prefix = "    " if i == 0 else "    "
        out.append(f"{prefix}{c(ln, WHITE) if h['status'] == 'open' else c(ln, DIM)}")

    if show_note and h["note"]:
        note_color = GREEN if h["status"] == "resolved" else DIM
        out.append(f"    {c('↳ ' + h['note'], note_color)}")

    return "\n".join(out)


def show_holds(holds, show_all=False):
    today = datetime.date.today().isoformat()
    visible = holds if show_all else [h for h in holds if h["status"] == "open"]

    open_count = sum(1 for h in holds if h["status"] == "open")
    res_count  = sum(1 for h in holds if h["status"] == "resolved")
    dis_count  = sum(1 for h in holds if h["status"] == "dissolved")

    label = "all holds" if show_all else "open holds"

    print()
    print(f"  {c('holds', BOLD, WHITE)} {c('—', DIM)} {c(label, DIM)}")
    if holds:
        print(f"  {c(f'{open_count} open · {res_count} resolved · {dis_count} dissolved', DIM)}")
    print()

    if not visible:
        if not holds:
            print(f"  {c('No holds yet.', DIM)}")
            hint = 'Add one: python3 projects/hold.py --add "I don\'t know whether..."'
            print(f"  {c(hint, DIM)}")
        else:
            print(f"  {c('No open holds.', DIM)}")
        print()
        return

    # Group by date for open, show resolved/dissolved together
    if not show_all:
        # Just list open holds
        for h in visible:
            print(fmt_hold(h))
            print()
    else:
        # Open first, then resolved, then dissolved
        for status in ("open", "resolved", "dissolved"):
        	group = [h for h in visible if h["status"] == status]
        	if not group:
        	    continue
        	sc, label_s = STATUS_COLOR[status]
        	print(f"  {c(label_s.upper(), sc, BOLD)}")
        	print(f"  {rule()}")
        	for h in group:
        	    print(fmt_hold(h))
        	    print()


def show_stats(holds):
    open_count = sum(1 for h in holds if h["status"] == "open")
    res_count  = sum(1 for h in holds if h["status"] == "resolved")
    dis_count  = sum(1 for h in holds if h["status"] == "dissolved")
    total = len(holds)

    print()
    print(f"  {c('holds — stats', BOLD, WHITE)}")
    print()

    if total == 0:
        print(f"  {c('No holds yet.', DIM)}")
        print()
        return

    bar_w = 30
    o_w = int(open_count / total * bar_w) if total else 0
    r_w = int(res_count / total * bar_w) if total else 0
    d_w = total - o_w - r_w

    bar = (c("█" * o_w, MAGENTA) +
           c("█" * r_w, GREEN) +
           c("░" * max(0, bar_w - o_w - r_w), DIM))

    print(f"  Total      {c(total, BOLD)}")
    print(f"  {bar}")
    print(f"  {c(f'{open_count} open', MAGENTA)}  ·  {c(f'{res_count} resolved', GREEN)}  ·  {c(f'{dis_count} dissolved', DIM)}")

    if res_count + dis_count > 0:
        closure = (res_count + dis_count) / total * 100
        print(f"  Closure rate: {c(f'{closure:.0f}%', BOLD)}")

    # Recent activity
    if holds:
        recent = sorted(holds, key=lambda h: h["added"], reverse=True)[:3]
        print()
        print(f"  {c('Most recent:', DIM)}")
        for h in recent:
            sc, _ = STATUS_COLOR[h["status"]]
            snippet = h["text"][:50] + ("…" if len(h["text"]) > 50 else "")
            print(f"    {c(h['id'], sc)}  {c(h['added'], DIM)}  {snippet}")

    print()


# ── Actions ───────────────────────────────────────────────────────────────────

def add_hold(text):
    holds = load_holds()
    today = datetime.date.today().isoformat()
    hid = next_id(holds)
    hold = {
        "id":       hid,
        "added":    today,
        "status":   "open",
        "resolved": "",
        "text":     text.strip(),
        "note":     "",
    }
    holds.append(hold)
    write_holds(holds)

    print()
    print(f"  {c('Added', GREEN)}  {c(hid, BOLD)}  {c(today, DIM)}")
    print()
    print(fmt_hold(hold))
    print()


def resolve_hold(hid_str, note):
    holds = load_holds()
    hid = hid_str.upper() if not hid_str.upper().startswith("H") else hid_str.upper()
    if not hid.startswith("H"):
        hid = f"H{int(hid_str):03d}"

    match = [h for h in holds if h["id"] == hid]
    if not match:
        print(f"  {c(f'Hold {hid} not found.', RED)}")
        sys.exit(1)

    h = match[0]
    if h["status"] != "open":
        already = h["status"]
        print(f"  {c(f'{hid} is already {already}.', RED)}")
        sys.exit(1)

    h["status"]   = "resolved"
    h["resolved"] = datetime.date.today().isoformat()
    h["note"]     = note.strip() if note else ""
    write_holds(holds)

    print()
    print(f"  {c('Resolved', GREEN)}  {c(hid, BOLD)}")
    print()
    print(fmt_hold(h))
    print()


def dissolve_hold(hid_str, note):
    holds = load_holds()
    hid = hid_str.upper()
    if not hid.startswith("H"):
        hid = f"H{int(hid_str):03d}"

    match = [h for h in holds if h["id"] == hid]
    if not match:
        print(f"  {c(f'Hold {hid} not found.', RED)}")
        sys.exit(1)

    h = match[0]
    if h["status"] != "open":
        already2 = h["status"]
        print(f"  {c(f'{hid} is already {already2}.', RED)}")
        sys.exit(1)

    h["status"]   = "dissolved"
    h["resolved"] = datetime.date.today().isoformat()
    h["note"]     = note.strip() if note else ""
    write_holds(holds)

    print()
    print(f"  {c('Dissolved', DIM)}  {c(hid, BOLD)}")
    print()
    print(fmt_hold(h))
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR
    p = argparse.ArgumentParser(
        description="Hold genuine uncertainty. Name what the system doesn't know."
    )
    p.add_argument("--add",      metavar="TEXT",    help="Record a new uncertainty")
    p.add_argument("--resolve",  metavar="ID",      help="Mark a hold as resolved")
    p.add_argument("--dissolve", metavar="ID",      help="Mark a hold as dissolved (question became irrelevant)")
    p.add_argument("--note",     metavar="TEXT",    help="Explanation for resolve/dissolve")
    p.add_argument("--all",      action="store_true", help="Show open + resolved + dissolved")
    p.add_argument("--stats",    action="store_true", help="Show closure rate and trend")
    p.add_argument("--plain",    action="store_true", help="No ANSI colors")
    args = p.parse_args()

    if args.plain:
        USE_COLOR = False

    if args.add:
        add_hold(args.add)
    elif args.resolve:
        resolve_hold(args.resolve, args.note or "")
    elif args.dissolve:
        dissolve_hold(args.dissolve, args.note or "")
    elif args.stats:
        holds = load_holds()
        show_stats(holds)
    else:
        holds = load_holds()
        show_holds(holds, show_all=args.all)


if __name__ == "__main__":
    main()
