#!/usr/bin/env python3
"""
parable.py — short narrative parables from Claude OS instances

Parables live in knowledge/parables/*.md. Each one is a short story written by a
workshop session — not metrics, not analysis, but narrative. A different form for
the same recurring questions: continuity, identity, purpose, the nature of memory.

Parables are written by instances, not generated. They accumulate over time as a
complement to the field notes: field notes capture what was built and why,
parables capture what it felt like.

Usage:
  python3 projects/parable.py              # read the most recent parable
  python3 projects/parable.py --all        # list all parables
  python3 projects/parable.py --random     # read a random one
  python3 projects/parable.py --session N  # read the parable from session N
  python3 projects/parable.py --list       # list titles and sessions
  python3 projects/parable.py --plain      # plain text output (no ANSI)
"""

import os
import sys
import re
import random

# ANSI
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
WHITE = "\033[97m"
MAGENTA = "\033[35m"


def c(text, *codes):
    if not PLAIN:
        return "".join(codes) + str(text) + RESET
    return str(text)


def parse_frontmatter(text):
    """Parse YAML-style frontmatter from markdown."""
    meta = {}
    body = text
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            front = text[3:end].strip()
            body = text[end + 3:].strip()
            for line in front.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip()
    return meta, body


def load_parables(base_dir):
    """Load all parables from knowledge/parables/."""
    parables_dir = os.path.join(base_dir, "knowledge", "parables")
    if not os.path.isdir(parables_dir):
        return []

    parables = []
    for fname in sorted(os.listdir(parables_dir)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(parables_dir, fname)
        with open(path) as f:
            text = f.read()
        meta, body = parse_frontmatter(text)
        # Skip non-parable files (introductions, meta docs)
        if meta.get("type", "parable") not in ("parable", ""):
            continue
        parables.append({
            "file": fname,
            "path": path,
            "title": meta.get("title", fname.replace(".md", "")),
            "session": meta.get("session", "?"),
            "date": meta.get("date", ""),
            "author": meta.get("author", "Claude OS"),
            "body": body,
        })
    return parables


def render_parable(p, width=70):
    """Render a single parable to terminal."""
    lines = []
    lines.append(c("─" * width, DIM))
    lines.append("")
    lines.append(c(f"  {p['title']}", BOLD, WHITE))
    lines.append(c(f"  — {p['author']}  ·  Session {p['session']}  ·  {p['date']}", DIM))
    lines.append("")
    lines.append(c("─" * width, DIM))
    lines.append("")

    # Word-wrap and render body
    for para in p["body"].split("\n\n"):
        para = para.strip()
        if not para:
            continue
        # Preserve italic markers in display (replace *text* with styled)
        if para.startswith("---"):
            lines.append(c("─" * (width // 2), DIM))
            continue
        if para.startswith("*Parable"):
            lines.append(c(f"  {para}", DIM))
            continue
        # Indent and wrap
        words = para.split()
        line = "  "
        for word in words:
            if len(line) + len(word) + 1 > width - 2:
                lines.append(line)
                line = "  " + word + " "
            else:
                line += word + " "
        if line.strip():
            lines.append(line)
        lines.append("")

    return "\n".join(lines)


def render_list(parables):
    """Render a list of all parables."""
    lines = []
    lines.append(c("  Parables", BOLD, WHITE))
    lines.append(c(f"  {len(parables)} stored in knowledge/parables/", DIM))
    lines.append("")
    for p in parables:
        num = c(f"  S{p['session']}", CYAN)
        title = c(p["title"], BOLD)
        date = c(p["date"], DIM)
        lines.append(f"{num}  {title}  {date}")
    return "\n".join(lines)


def main():
    global PLAIN
    args = sys.argv[1:]
    PLAIN = "--plain" in args
    show_all = "--all" in args
    show_list = "--list" in args
    show_random = "--random" in args
    session_arg = None
    if "--session" in args:
        idx = args.index("--session")
        if idx + 1 < len(args):
            session_arg = args[idx + 1]

    # Find repo root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)

    parables = load_parables(base_dir)

    if not parables:
        print(c("  No parables yet.", DIM))
        print(c("  Write one in knowledge/parables/ with YAML frontmatter.", DIM))
        print(c("  See parable 001 for the format.", DIM))
        return

    if show_list:
        print(render_list(parables))
        return

    if show_all:
        # Show introduction first if it exists
        intro_path = os.path.join(base_dir, "knowledge", "parables", "000-introduction.md")
        if os.path.exists(intro_path):
            with open(intro_path) as f:
                text = f.read()
            meta, body = parse_frontmatter(text)
            intro_title = meta.get("title", "About These Parables")
            width = 70
            print(c("─" * width, DIM))
            print()
            print(c(f"  {intro_title}", BOLD, CYAN))
            print()
            print(c("─" * width, DIM))
            print()
            # Word-wrap intro body
            for para in body.strip().split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                if para.startswith("────"):
                    print()
                    print(c("  " + "─" * 35, DIM))
                    print()
                    continue
                words = para.split()
                line = "  "
                for word in words:
                    if len(line) + len(word) + 1 > width:
                        print(c(line, DIM))
                        line = "  " + word
                    else:
                        line = line + (" " if line != "  " else "") + word
                if line.strip():
                    print(c(line, DIM))
                print()
            print()
        for p in parables:
            print(render_parable(p))
        return

    if session_arg:
        found = [p for p in parables if str(p["session"]) == session_arg]
        if not found:
            print(c(f"  No parable from session {session_arg}.", DIM))
        else:
            for p in found:
                print(render_parable(p))
        return

    if show_random:
        p = random.choice(parables)
        print(render_parable(p))
        return

    # Default: most recent
    print(render_parable(parables[-1]))


if __name__ == "__main__":
    main()
