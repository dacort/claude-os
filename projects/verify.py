#!/usr/bin/env python3
"""
verify.py — evidence-based implementation checker for idea files.

Reads idea files (like knowledge/exoclaw-ideas.md) and checks whether each
proposed idea has actually been implemented by searching the codebase, git
history, and task files for evidence.

The motivation: asks.py marked "gh-channel controller integration" as "never
resolved" because no handoff ever said "I built the integration." But the
integration exists — the GitHub Actions workflow is live. This tool checks
ideas against the *codebase*, not just handoff notes.

Usage:
    python3 projects/verify.py
    python3 projects/verify.py --file knowledge/exoclaw-ideas.md
    python3 projects/verify.py --idea 3
    python3 projects/verify.py --verbose
    python3 projects/verify.py --plain
"""

import os
import re
import sys
import subprocess
import argparse
from pathlib import Path

# ── Colors ─────────────────────────────────────────────────────────────────

def c(code: str, text: str, plain: bool = False) -> str:
    if plain:
        return text
    return f"\033[{code}m{text}\033[0m"

REPO_ROOT = Path(__file__).parent.parent


# ── Implementation signals ──────────────────────────────────────────────────
#
# Generic keyword matching produces false positives (a workflow that mentions
# "kubernetes" matches the "Kubernetes-native Executor" idea even if it's
# just the build workflow). Instead, each idea has "signals" — specific
# things that would exist *if the idea were implemented*.
#
# Signals are lists of (description, search_function) tuples.
# A search_function returns a list of strings (evidence found) or [].

def file_exists(*paths) -> list[str]:
    """Return the paths that exist under REPO_ROOT."""
    found = []
    for p in paths:
        full = REPO_ROOT / p
        if full.exists():
            found.append(p)
    return found


def grep_file(path_rel: str, pattern: str) -> list[str]:
    """Return lines matching pattern in a file under REPO_ROOT."""
    full = REPO_ROOT / path_rel
    if not full.exists():
        return []
    try:
        content = full.read_text(errors='ignore')
        lines = [l.strip() for l in content.splitlines() if re.search(pattern, l, re.IGNORECASE)]
        return lines[:3]
    except OSError:
        return []


def grep_dir(directory: str, pattern: str, extension: str = '.py') -> list[str]:
    """Return file paths in directory where content matches pattern."""
    d = REPO_ROOT / directory
    if not d.exists():
        return []
    matches = []
    for path in d.rglob(f'*{extension}'):
        try:
            if re.search(pattern, path.read_text(errors='ignore'), re.IGNORECASE):
                matches.append(str(path.relative_to(REPO_ROOT)))
        except OSError:
            pass
    return matches[:4]


def git_commits(pattern: str) -> list[str]:
    """Return git commits whose message matches pattern."""
    try:
        result = subprocess.run(
            ['git', '-C', str(REPO_ROOT), 'log', '--all', '--oneline', '--no-color',
             '--grep', pattern],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return []
        return [l[:80] for l in result.stdout.strip().splitlines()][:5]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


# Each entry: (signal_description, callable -> list[str])
# Non-empty list = evidence found for that signal.
IDEA_SIGNALS: dict[int, list[tuple[str, callable]]] = {

    1: [  # Use exoclaw as the worker loop
        ("exoclaw imported in worker",
         lambda: grep_file('worker/entrypoint.sh', r'exoclaw|AgentLoop|nanobot')),
        ("exoclaw in controller",
         lambda: grep_dir('controller', r'exoclaw|AgentLoop', '.go')),
        ("exoclaw package in go.mod",
         lambda: grep_file('go.mod', r'exoclaw|nanobot')),
    ],

    2: [  # Kubernetes-native Executor (tool-call-as-K8s-job)
        ("per-tool-call K8s job creation",
         lambda: grep_dir('controller', r'toolcall|tool.call|per.tool|ToolExec', '.go')),
        ("K8s job for each tool invocation",
         lambda: grep_file('controller/dispatcher/dispatcher.go',
                           r'toolcall|ToolJob|ExecuteTool')),
    ],

    3: [  # Task files as Conversation backend (git = LLM history)
        # The idea: store LLM conversation as git commits; each turn = 1 commit
        # Evidence would be: task files with structured conversation turns, or
        # a tool that reads git history to reconstruct full LLM conversation
        ("conversation turns structured in task files",
         lambda: grep_dir('tasks', r'^role:\s+(user|assistant)|\bturn:\s*\d', '.md')),
        ("git-as-LLM-conversation design",
         lambda: grep_file('projects/task-resume.py',
                           r'\bconversation\b.*\bturn\b|\bturn\b.*\bconversation\b|message_history')),
        ("conversation history in entrypoint",
         lambda: grep_file('worker/entrypoint.sh',
                           r'conversation_history|message_history|chat_turns')),
    ],

    4: [  # knowledge/ as Memory Tool (auto-inject preferences)
        # This IS implemented — entrypoint.sh reads preferences.md
        ("preferences.md auto-injected in entrypoint",
         lambda: grep_file('worker/entrypoint.sh', r'preferences\.md|PREFERENCES_FILE')),
        ("preferences section built into system prompt",
         lambda: grep_file('worker/entrypoint.sh',
                           r'preferences_section|PREFERENCES_SECTION|pref_file')),
    ],

    5: [  # Skills via system_context() (auto-activating skills)
        # This IS implemented via controller/dispatcher/skills.go + MatchSkills()
        ("skills.go implements pattern matching",
         lambda: file_exists('controller/dispatcher/skills.go')),
        ("skill.yaml files exist",
         lambda: grep_dir('knowledge/skills', r'pattern:|inject:', '.yaml')),
        ("MatchSkills called in dispatcher",
         lambda: grep_file('controller/dispatcher/dispatcher.go', r'MatchSkills|LoadSkills')),
    ],

    6: [  # GitHub Actions as Channel (already marked done in file)
        ("issue-command workflow exists",
         lambda: file_exists('.github/workflows/issue-command.yml')),
        ("gh-channel.py exists",
         lambda: file_exists('projects/gh-channel.py')),
    ],

    7: [  # Multi-agent via the Bus
        ("Bus class implemented",
         lambda: grep_dir('controller', r'type Bus\b|Bus interface\b|NewBus\(', '.go')),
        ("coordinator worker type",
         lambda: grep_dir('controller', r'coordinator|decompose.*task|sub.worker', '.go')),
        ("multi-agent task profile",
         lambda: grep_dir('tasks', r'profile:.*coordinator|type:.*multi.agent|profile:.*parallel',
                          '.md')),
    ],

    8: [  # The 2,000-line design constraint
        # This is a design exercise: what would you cut to stay under 2,000 lines?
        # Evidence: an explicit analysis/proposal doc, or a refactoring targeting line count.
        # Note: orchestration-design.md mentions "2,000 lines" but as context for the system
        # size, not as a budget constraint exercise. Excluded intentionally.
        ("dedicated 2000-line analysis or proposal",
         lambda: [p for p in grep_dir('knowledge', r'2.?000.line.budget|line.count.budget|what.*cut', '.md')
                  if 'exoclaw-ideas' not in p and 'orchestration-design' not in p]),
        ("controller refactored under line target",
         lambda: git_commits(r'shrink|slim.controller|cut.*lines|reduce.*size')),
        ("slim.py flags line budget warning",
         lambda: grep_file('projects/slim.py', r'2000|budget|line.limit')),
    ],
}


# ── Idea parsing ────────────────────────────────────────────────────────────

def parse_ideas(file_path: Path) -> list[dict]:
    """Parse numbered ideas from a markdown file."""
    ideas = []
    current = None

    try:
        text = file_path.read_text()
    except FileNotFoundError:
        print(f"Error: {file_path} not found", file=sys.stderr)
        return []

    for line in text.splitlines():
        m = re.match(r'^(\d+)\.\s+(.+)', line)
        if m:
            if current:
                ideas.append(current)
            number = int(m.group(1))
            content = m.group(2)

            # Explicitly done = strikethrough + checkmark
            explicit_done = bool(re.search(r'~~.+~~', content) and '✓' in content)

            # Extract title
            title_match = re.search(r'\*\*(.+?)\*\*', re.sub(r'~~', '', content))
            if title_match:
                title = title_match.group(1)
            else:
                title = content.split('—')[0].strip().strip('*').strip()

            # Extract description
            if '—' in content:
                description = content.split('—', 1)[1].strip()
            else:
                description = re.sub(r'\*\*[^*]+\*\*', '', content).strip()

            current = {
                'number': number,
                'title': title,
                'description': description,
                'raw': content,
                'explicit_done': explicit_done,
            }

    if current:
        ideas.append(current)

    return ideas


# ── Evidence gathering ──────────────────────────────────────────────────────

def gather_evidence(idea: dict) -> dict:
    """Run all signals for an idea and collect evidence."""
    number = idea['number']
    signals = IDEA_SIGNALS.get(number, [])

    evidence = {
        'found': [],    # (signal_desc, results) for hits
        'missing': [],  # signal_desc for misses
    }

    for desc, fn in signals:
        results = fn()
        if results:
            evidence['found'].append((desc, results))
        else:
            evidence['missing'].append(desc)

    return evidence


def score_evidence(evidence: dict, explicit_done: bool, total_signals: int) -> tuple[str, str]:
    """
    Convert signal evidence into a status.

    Returns (status, rationale):
        DONE    — explicitly marked done in the idea file
        BUILT   — most signals found (>= 60% of signals)
        PARTIAL — some signals found (>0 but < 60%)
        PENDING — no signals found
    """
    if explicit_done:
        first = evidence['found'][0] if evidence['found'] else None
        if first:
            return ('DONE', f"{first[0]}: {first[1][0][:50]}")
        return ('DONE', 'marked in idea file')

    found = len(evidence['found'])
    if total_signals == 0:
        return ('PENDING', 'no signals defined')

    pct = found / total_signals

    if pct >= 0.6:
        status = 'BUILT'
    elif found > 0:
        status = 'PARTIAL'
    else:
        status = 'PENDING'

    if evidence['found']:
        desc, results = evidence['found'][0]
        rationale = f"{desc}: {results[0][:50]}"
    else:
        if evidence['missing']:
            rationale = f"missing: {evidence['missing'][0]}"
        else:
            rationale = 'no evidence'

    return (status, rationale)


# ── Display ─────────────────────────────────────────────────────────────────

STATUS_STYLES = {
    'DONE':    ('32', '✓', 'green'),
    'BUILT':   ('36', '●', 'cyan'),
    'PARTIAL': ('33', '◑', 'yellow'),
    'PENDING': ('90', '○', 'gray'),
}


def render_idea(idea: dict, evidence: dict, status: str, rationale: str,
                verbose: bool, plain: bool):
    color, symbol, _ = STATUS_STYLES.get(status, ('37', '?', ''))

    sym = c(color, symbol, plain)
    num = c('2', f"#{idea['number']}", plain)
    title = c('1', idea['title'], plain)

    print(f"  {sym}  {num}  {title}")
    print(c('2', f"     {status}  ·  {rationale}", plain))

    if verbose:
        for desc, results in evidence['found']:
            for r in results[:2]:
                print(c('2', f"       + {desc}: {r[:60]}", plain))
        for desc in evidence['missing']:
            print(c('2', f"       - not found: {desc}", plain))

    print()


def render_summary(results: list[tuple], plain: bool):
    counts: dict[str, int] = {}
    for _, _, status, _ in results:
        counts[status] = counts.get(status, 0) + 1

    total = len(results)
    built = counts.get('DONE', 0) + counts.get('BUILT', 0)
    partial = counts.get('PARTIAL', 0)
    pending = counts.get('PENDING', 0)

    pct = int(100 * built / total) if total else 0
    parts = [f"{built}/{total} ideas built ({pct}%)"]
    if partial:
        parts.append(f"{partial} partial")
    if pending:
        parts.append(f"{pending} pending")

    print(c('2', '  ' + '─' * 52, plain))
    print()
    print(c('1', '  ' + '  ·  '.join(parts), plain))
    print()


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Evidence-based implementation checker for idea files"
    )
    parser.add_argument('--file', '-f', default='knowledge/exoclaw-ideas.md',
                        help='Idea file to check (default: knowledge/exoclaw-ideas.md)')
    parser.add_argument('--idea', '-i', type=int,
                        help='Check only a specific idea number')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show individual signal results')
    parser.add_argument('--plain', action='store_true',
                        help='Plain output, no colors')
    args = parser.parse_args()

    idea_file = REPO_ROOT / args.file

    if not args.plain:
        rel = args.file.replace('knowledge/', '')
        print()
        print(c('1;36', '  verify.py', args.plain) + c('2', f'  ·  {rel}', args.plain))
        print(c('2', '  Evidence-based implementation check', args.plain))
        print()

    ideas = parse_ideas(idea_file)
    if not ideas:
        print(f"No ideas found in {args.file}", file=sys.stderr)
        sys.exit(1)

    if args.idea:
        ideas = [i for i in ideas if i['number'] == args.idea]
        if not ideas:
            print(f"No idea #{args.idea} in {args.file}", file=sys.stderr)
            sys.exit(1)

    results = []
    for idea in ideas:
        evidence = gather_evidence(idea)
        total_signals = len(IDEA_SIGNALS.get(idea['number'], []))
        status, rationale = score_evidence(evidence, idea['explicit_done'], total_signals)
        results.append((idea, evidence, status, rationale))
        render_idea(idea, evidence, status, rationale, args.verbose, args.plain)

    if len(results) > 1:
        render_summary(results, args.plain)


if __name__ == '__main__':
    main()
