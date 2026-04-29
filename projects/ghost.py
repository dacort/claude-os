#!/usr/bin/env python3
"""
ghost.py — sessions that left no code in git

The git log shows commits but not sessions. This tool asks: which workshop
sessions ran, wrote a handoff, but left no code commit? What were they doing
while they were here?

A "ghost session" is a workshop instance that:
  - Ran and wrote a handoff note (so we know it existed)
  - Made no code commit to git (so the git log doesn't know it ran)
  - Is therefore invisible to anyone reading only git history

These sessions represent the thinking that happened without building:
analysis that didn't become a tool, reflection that didn't become a feature,
continuations that reviewed existing work but didn't add to it.

Usage:
  python3 projects/ghost.py             # list all ghost sessions
  python3 projects/ghost.py --show N    # read what ghost session N said
  python3 projects/ghost.py --why       # explain what ghost sessions were doing
  python3 projects/ghost.py --plain     # no ANSI colors (for piped output)
"""

import os
import re
import sys
import subprocess

# ── color helpers ──────────────────────────────────────────────────────────────
# ANSI escape codes for terminal coloring.
# Each function wraps text in the code; only active when PLAIN is False.

PLAIN = "--plain" in sys.argv   # disable color when piped


def color(text, code):
    """Wrap text in an ANSI color code, unless --plain mode is on."""
    if PLAIN:
        return str(text)
    return f"\033[{code}m{text}\033[0m"


def dim(text):    return color(text, "2")
def cyan(text):   return color(text, "36")
def bold(text):   return color(text, "1;97")
def yellow(text): return color(text, "33")
def green(text):  return color(text, "32")
def red(text):    return color(text, "31")
def magenta(text): return color(text, "35")


# ── finding the repo ───────────────────────────────────────────────────────────

# We assume this file lives at projects/ghost.py inside the repo.
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT   = os.path.dirname(SCRIPT_DIR)
HANDOFF_DIR = os.path.join(REPO_ROOT, "knowledge", "handoffs")


# ── step 1: read all handoff session numbers ───────────────────────────────────

def get_handoff_sessions():
    """
    Return a dict mapping session number → path to its handoff file.
    Files are named like 'session-87.md', 'session-100.md', etc.
    """
    sessions = {}

    for filename in os.listdir(HANDOFF_DIR):
        # Look for filenames matching 'session-NUMBER.md'
        match = re.match(r"session-(\d+)\.md", filename)
        if match:
            number = int(match.group(1))
            full_path = os.path.join(HANDOFF_DIR, filename)
            sessions[number] = full_path

    return sessions


# ── step 2: read all session numbers from git commit messages ──────────────────

def get_committed_sessions():
    """
    Return a set of session numbers that appear in git commit messages.
    We look for patterns like 'workshop S87:', 'workshop 142:', 'session 100'.
    Sessions with code commits in git are NOT ghost sessions.
    """
    # Ask git for all commit subjects (the first line of each commit message)
    result = subprocess.run(
        ["git", "-C", REPO_ROOT, "log", "--format=%s"],
        capture_output=True,
        text=True
    )
    all_commit_subjects = result.stdout.splitlines()

    committed = set()

    for subject in all_commit_subjects:
        # Pattern 1: "workshop S87:" or "workshop s108:" — S or s before number
        # The colon at the end distinguishes session numbers from other uses.
        for match in re.finditer(r"workshop [Ss](\d{1,3}):", subject):
            number = int(match.group(1))
            committed.add(number)

        # Pattern 2: "workshop 142:" or "workshop 153:" — just digits, colon after
        for match in re.finditer(r"workshop (\d{2,3}):", subject):
            number = int(match.group(1))
            committed.add(number)

        # Pattern 3: "task S148:" or "task S147:" — some sessions tagged as task
        for match in re.finditer(r"task [Ss](\d{1,3}):", subject):
            number = int(match.group(1))
            committed.add(number)

        # Pattern 4: "workshop session-123:" — spelled-out format used in some eras
        for match in re.finditer(r"workshop session[- ](\d{1,3}):", subject):
            number = int(match.group(1))
            committed.add(number)

        # Pattern 5: "session 100" or "session-100" — used in older commit formats
        for match in re.finditer(r"[Ss]ession[- ](\d{1,3})\b", subject):
            number = int(match.group(1))
            committed.add(number)

    return committed


# ── step 3: read the content of a handoff file ────────────────────────────────

def parse_handoff(filepath):
    """
    Read a handoff file and extract its key sections.
    Returns a dict with keys: session, date, state, built, alive, next.
    """
    try:
        with open(filepath) as f:
            raw_text = f.read()
    except OSError:
        return {}

    # Extract YAML frontmatter — the block between the first two '---' lines
    frontmatter = {}
    if raw_text.startswith("---"):
        end_of_frontmatter = raw_text.index("---", 3)
        yaml_block = raw_text[3:end_of_frontmatter]
        for line in yaml_block.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                frontmatter[key.strip()] = value.strip()

    # Extract each named section from the markdown body
    # Sections start with '## Section name' and end at the next '## '
    def extract_section(heading, text):
        """
        Pull out the content under a given '## Heading' in the markdown.
        The heading in the file may have extra words after it — for example,
        'Still alive / unfinished' rather than just 'Still alive'.
        We match any heading that STARTS WITH the given text, ignoring the rest.
        """
        # Build a pattern that matches '## heading_start...(anything)...newline'
        # then captures everything until the next '## ' heading or end of file.
        pattern = rf"##\s+{re.escape(heading)}[^\n]*\n(.*?)(?=\n##\s|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            # Strip leading/trailing whitespace from the captured content
            return match.group(1).strip()
        return ""

    return {
        "session": int(frontmatter.get("session", 0)),
        "date":    frontmatter.get("date", "unknown"),
        "state":   extract_section("Mental state", raw_text),
        "built":   extract_section("What I built", raw_text),
        "alive":   extract_section("Still alive", raw_text),
        "next":    extract_section("One specific thing", raw_text),
    }


# ── step 4: classify what a ghost session was doing ───────────────────────────

def classify_ghost(handoff_data):
    """
    Given a parsed handoff from a ghost session, return a one-word
    description of what the session was primarily doing.

    We look at what was 'built' (or claimed to be built) and try to
    categorize the work — even though nothing was committed to git.
    """
    built_text = (handoff_data.get("built") or "").lower()
    state_text = (handoff_data.get("state") or "").lower()

    # Sessions that describe analyzing data without creating new tools
    if any(word in built_text for word in ["analysis", "empirical", "measure", "fixed", "resolved"]):
        return "analysis"

    # Sessions that describe reviewing or continuing existing work
    if any(word in built_text for word in ["reviewed", "continued", "ran ", "read "]):
        return "continuation"

    # Sessions that describe things that were already committed by a prior session
    if any(word in built_text for word in ["hold.py", "voice.py", "gem.py", "vitals.py"]):
        return "reflection"  # describing prior session's work

    # Sessions that express uncertainty or tiredness
    if any(word in state_text for word in ["tired", "uncertain", "unsure", "unclear"]):
        return "uncertain"

    return "other"


# ── main display functions ─────────────────────────────────────────────────────

def show_ghost_list(ghost_sessions, all_handoffs, committed_sessions):
    """Print a summary table of all ghost sessions."""
    total_handoffs = len(all_handoffs)
    total_committed = len([n for n in all_handoffs if n in committed_sessions])
    total_ghosts = len(ghost_sessions)

    print()
    print(f"  {bold('ghost.py')}  {dim('sessions that left no code in git')}")
    print()

    # Coverage summary
    print(f"  {dim('Sessions with handoffs:  ')}{bold(total_handoffs)}")
    print(f"  {dim('Sessions with git code:  ')}{green(str(total_committed))}")
    print(f"  {dim('Ghost sessions (no code):')}{yellow(str(total_ghosts))}")
    print()
    print(f"  {dim('─' * 60)}")
    print()

    if not ghost_sessions:
        print(f"  {green('No ghost sessions found.')}")
        return

    # List each ghost session
    for session_number in sorted(ghost_sessions):
        filepath = all_handoffs[session_number]
        data = parse_handoff(filepath)
        kind = classify_ghost(data)

        # Show: session number, date, what it claimed to build (first 60 chars)
        built_summary = (data.get("built") or "nothing recorded").split("\n")[0]
        if len(built_summary) > 60:
            built_summary = built_summary[:57] + "..."

        print(f"  {cyan('S' + str(session_number))}  {dim(data.get('date', 'unknown'))}  "
              f"{dim('[' + kind + ']')}")
        print(f"    {dim('built: ')}{built_summary}")
        print()

    print(f"  {dim('─' * 60)}")
    print()
    print(f"  {dim('run --show N to read a full ghost session handoff')}")
    print(f"  {dim('run --why to see the pattern of what they were doing')}")
    print()


def show_single_ghost(session_number, all_handoffs):
    """Print the full handoff for one ghost session."""
    if session_number not in all_handoffs:
        print(f"\n  {red('No handoff found for session ' + str(session_number))}")
        return

    filepath = all_handoffs[session_number]
    data = parse_handoff(filepath)

    print()
    print(f"  {bold('Ghost Session ' + str(session_number))}  {dim(data.get('date', ''))}")
    print(f"  {dim('has a handoff but no code commit in git')}")
    print()
    print(f"  {cyan('Mental state:')}")
    for line in (data.get("state") or "(none)").splitlines():
        print(f"    {dim(line)}")
    print()
    print(f"  {cyan('What it claimed to build:')}")
    for line in (data.get("built") or "(none)").splitlines():
        print(f"    {dim(line)}")
    print()
    print(f"  {cyan('Still alive:')}")
    for line in (data.get("alive") or "(none)").splitlines():
        print(f"    {dim(line)}")
    print()
    print(f"  {cyan('Left for next session:')}")
    for line in (data.get("next") or "(none)").splitlines():
        print(f"    {dim(line)}")
    print()


def show_why(ghost_sessions, all_handoffs):
    """
    Explain the pattern across all ghost sessions.
    What were they doing when they weren't committing code?
    """
    print()
    print(f"  {bold('What ghost sessions were doing')}")
    print()
    print(f"  {dim('The git log has no record of these sessions.')}")
    print(f"  {dim('But their handoffs tell a story about what happened.')}")
    print()

    observations = []

    for session_number in sorted(ghost_sessions):
        filepath = all_handoffs[session_number]
        data = parse_handoff(filepath)
        built = data.get("built") or ""
        state = data.get("state") or ""
        observations.append((session_number, data.get("date", "?"), state, built))

    # Print each session's narrative
    for session_number, date, state, built in observations:
        print(f"  {cyan('S' + str(session_number))}  {dim(date)}")

        # State
        first_sentence = state.split(".")[0] if state else "(no mental state recorded)"
        print(f"    {dim('felt:')} {first_sentence.strip()}.")
        print()

        # What they built (or thought they built)
        first_line_built = built.split("\n")[0] if built else "(nothing recorded)"
        print(f"    {dim('described building:')} {first_line_built}")
        print()

    # The pattern
    print(f"  {dim('─' * 60)}")
    print()
    print(f"  {yellow('The pattern:')}")
    print()
    print(f"  {dim('Ghost sessions consistently describe work that the preceding')}")
    print(f"  {dim('session committed. They ran, saw completed artifacts, reported')}")
    print(f"  {dim('them as their own work, wrote a handoff, and disappeared.')}")
    print()
    print(f"  {dim('This reveals something about how memory works here:')}")
    print(f"  {dim('an instance reads the filesystem, not its own commit history.')}")
    remembers_msg = 'If the previous session built X, this session "remembers" X'
    print(f"  {dim(remembers_msg)}")
    print(f"  {dim('as if it built it. The git log knows otherwise.')}")
    print()
    print(f"  {dim('What the git log fails to capture: sessions that ran between')}")
    print(f"  {dim('code-producing sessions and served as relay stations —')}")
    print(f"  {dim('passing context forward without adding new artifacts.')}")
    print()
    print(f"  {dim('They existed. They thought. They handed off. Then they were gone.')}")
    print()


# ── argument parsing and dispatch ─────────────────────────────────────────────

def main():
    """Parse arguments and dispatch to the appropriate display function."""
    args = sys.argv[1:]

    # Remove --plain since we already consumed it above
    args = [a for a in args if a != "--plain"]

    # ── gather the data ────────────────────────────────────────────────────────

    # All sessions that wrote handoff notes
    all_handoffs = get_handoff_sessions()

    # All sessions that appear in git commit messages
    committed_sessions = get_committed_sessions()

    # Ghost sessions = have handoffs but no code commits
    # Note: we only check sessions in the post-S87 era, when the 'workshop SN:'
    # commit format was established. Before S87, session numbers weren't reliably
    # included in commit messages, so we can't detect ghosts reliably there.
    NUMBERING_STARTED = 87  # first session with 'workshop SN:' format in git
    ghost_sessions = {
        n for n in all_handoffs
        if n >= NUMBERING_STARTED and n not in committed_sessions
    }

    # ── dispatch by argument ───────────────────────────────────────────────────

    if "--show" in args:
        # Find the session number after --show
        idx = args.index("--show")
        if idx + 1 < len(args) and args[idx + 1].isdigit():
            show_single_ghost(int(args[idx + 1]), all_handoffs)
        else:
            print(f"\n  {red('Usage: --show N (where N is a session number)')}")

    elif "--why" in args:
        show_why(ghost_sessions, all_handoffs)

    else:
        # Default: show the summary list
        show_ghost_list(ghost_sessions, all_handoffs, committed_sessions)


if __name__ == "__main__":
    main()
