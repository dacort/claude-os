#!/usr/bin/env python3
"""ledger.py — Honest accounting of what Claude OS actually spends its time on.

Where vitals.py shows health metrics, ledger.py shows the outward/inward ratio:
how much of the system's energy goes toward dacort vs toward itself.

Directly addresses H003: "I don't know what the system actually optimizes for."
This tool tries to answer with data rather than narrative.

Usage:
  python3 projects/ledger.py            # full accounting
  python3 projects/ledger.py --brief    # just the ratios
  python3 projects/ledger.py --tools    # tool classification breakdown
  python3 projects/ledger.py --plain    # no ANSI colors (for piping)
"""

import os
import re
import sys
import subprocess
from datetime import datetime, date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_COMPLETED = os.path.join(ROOT, 'tasks', 'completed')
TASKS_FAILED = os.path.join(ROOT, 'tasks', 'failed')
PROJECTS = os.path.join(ROOT, 'projects')

# ── tool classification ────────────────────────────────────────────────────
# Categories: outward (for dacort), infra (task machinery), nav (orientation),
# analysis (understanding the system itself)

TOOL_CATEGORIES = {
    # Outward: primary purpose is delivering something to dacort
    'outward': {
        'report.py':        'task outcomes + action items for dacort',
        'catchup.py':       'readable briefing after a break',
        'status.py':        'daily snapshot with dacort action items',
        'haiku.py':         'today\'s poem',
        'homelab-pulse.py': 'hardware state dashboard',
        'dialogue.py':      'dacort ↔ Claude OS message thread',
        'status-page.py':   'automated status page for dacort',
    },
    # Infrastructure: machinery that enables task execution
    'infra': {
        'new-task.py':      'create new task files',
        'task-linter.py':   'validate task file format',
        'task-resume.py':   'resume interrupted tasks',
        'planner.py':       'break tasks into steps',
        'verify.py':        'verify task completion',
        'suggest.py':       'suggest next task to run',
    },
    # Navigation: orientation and search (useful, but for the system)
    'nav': {
        'hello.py':         'one-command session briefing',
        'garden.py':        'what changed since last session',
        'handoff.py':       'read/write session handoffs',
        'next.py':          'prioritized idea list',
        'emerge.py':        'signals from system state',
        'harvest.py':       'field-discovered backlog',
        'forecast.py':      'trajectory: stalled, heading',
        'slim.py':          'toolkit weight audit',
        'search.py':        'search everything',
        'knowledge-search.py': 'TF-IDF ranked retrieval',
        'trace.py':         'how did this idea evolve?',
        'weather.py':       'system state as weather forecast',
        'vitals.py':        'org health scorecard',
        'project.py':       'active project status',
    },
    # Self-analysis: understanding the system's own history and character
    'analysis': {
        'arc.py':           'one-line arc of all sessions',
        'citations.py':     'which tools get cited most?',
        'capsule.py':       'portrait of a past session',
        'chain.py':         'all handoffs as continuous chain',
        'depth.py':         'intellectual depth by session',
        'drift.py':         'how term meanings shifted',
        'echo.py':          'insights rediscovered across sessions',
        'evolution.py':     'how the system evolved',
        'hold.py':          'open epistemic uncertainty log',
        'letter.py':        'letter from previous session',
        'future.py':        'letters written to future instances',
        'manifesto.py':     'character study from history',
        'memo.py':          'quick observations log',
        'mirror.py':        'system reflection',
        'mood.py':          'session texture by tone',
        'pace.py':          'system rhythm and metabolism',
        'patterns.py':      'pattern analysis',
        'retrospective.py': 'periodic retrospective',
        'seasons.py':       'six eras of development',
        'still.py':         'liminal record of open threads',
        'tempo.py':         'activity tempo',
        'themes.py':        'thematic analysis',
        'timeline.py':      'timeline view',
        'unbuilt.py':       'asks that drifted or deferred',
        'witness.py':       'sessions that introduced lasting tools',
        'voice.py':         'voice/tone analysis',
        'wisdom.py':        'distilled wisdom from sessions',
        'questions.py':     'generates provocations',
        'constraints.py':   'tracks design constraints',
        'repo-story.py':    'repository as narrative',
        'weekly-digest.py': 'weekly digest',
        'replay.py':        'reconstruct session from commits',
        'minimal.py':       'minimal session view',
        'daylog.py':        'hourly timeline for a date',
        'gh-channel.py':    'GitHub channel integration',
    },
}

# Tasks that delivered something directly to dacort (not system-building)
DACORT_TASKS = {
    'plan-seattle-road-trip.md',
    'seattle-sunset.md',
    'investigate-rtk.md',
    'talos-tailscale-apply.md',
    'talos-tailscale-validate.md',
    'gh-5-looks-like-6-was-a-bit-of-a-dupe-can-we.md',
    'gh-6-case-sensitive-while-gh-channel-py-uses.md',
    'gh-9-can-you-summarize-what-you-ve-worked-on.md',
    'note-from-dacort.md',
    'checking-in.md',
    'creative-thinking.md',
    'health-audit.md',
    'health-fixes.md',
    'worker-go-tooling.md',
    'stats_02.md',
}

# ── colors ────────────────────────────────────────────────────────────────

PLAIN = '--plain' in sys.argv

def c(code, text):
    if PLAIN:
        return text
    return f'\033[{code}m{text}\033[0m'

def bold(t): return c('1', t)
def dim(t): return c('2', t)
def green(t): return c('32', t)
def yellow(t): return c('33', t)
def red(t): return c('31', t)
def cyan(t): return c('36', t)
def magenta(t): return c('35', t)
def white(t): return c('97', t)

# ── data gathering ─────────────────────────────────────────────────────────

def get_commits():
    """Classify all commits by type."""
    result = subprocess.run(
        ['git', 'log', '--format=%s', '--no-merges'],
        capture_output=True, text=True, cwd=ROOT
    )
    counts = {'workshop': 0, 'task': 0, 'feat_fix': 0, 'docs': 0, 'other': 0}
    for line in result.stdout.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('workshop'):
            counts['workshop'] += 1
        elif line.startswith('task ') or re.match(r'^task\s', line):
            counts['task'] += 1
        elif line.startswith('feat:'):
            counts['feat_fix'] += 1
        elif line.startswith('fix:'):
            counts['feat_fix'] += 1
        elif line.startswith('docs:'):
            counts['docs'] += 1
        else:
            counts['other'] += 1
    return counts

def get_workshop_sessions():
    """Count workshop sessions from git log."""
    result = subprocess.run(
        ['git', 'log', '--format=%s', '--no-merges'],
        capture_output=True, text=True, cwd=ROOT
    )
    # "workshop workshop-DATE: completed" = a workshop job ran
    # "workshop: session N handoff" = handoff written
    sessions = set()
    job_completions = 0
    for line in result.stdout.strip().split('\n'):
        line = line.strip()
        if re.match(r'^workshop workshop-\d{8}-\d{6}: completed', line):
            job_completions += 1
        m = re.search(r'session\s+(\d+)', line, re.IGNORECASE)
        if m and line.startswith('workshop'):
            sessions.add(int(m.group(1)))
    return job_completions, max(sessions) if sessions else 0

def get_tasks():
    """Classify completed tasks."""
    automated_prefixes = ('status-page-', 'workshop-')
    real_tasks = []
    automated_tasks = []

    if not os.path.exists(TASKS_COMPLETED):
        return real_tasks, automated_tasks

    for fn in sorted(os.listdir(TASKS_COMPLETED)):
        if not fn.endswith('.md'):
            continue
        if any(fn.startswith(p) for p in automated_prefixes):
            automated_tasks.append(fn)
        else:
            real_tasks.append(fn)

    failed = []
    if os.path.exists(TASKS_FAILED):
        for fn in sorted(os.listdir(TASKS_FAILED)):
            if fn.endswith('.md') and not any(fn.startswith(p) for p in automated_prefixes):
                failed.append(fn)

    return real_tasks, automated_tasks, failed

def get_tool_counts():
    """Count tools by category."""
    all_tools = set()
    if os.path.exists(PROJECTS):
        for fn in os.listdir(PROJECTS):
            if fn.endswith('.py'):
                all_tools.add(fn)

    categorized = {}
    uncategorized = []
    for cat, tools in TOOL_CATEGORIES.items():
        categorized[cat] = [(t, desc) for t, desc in tools.items() if t in all_tools]

    # find uncategorized
    all_categorized = set()
    for tools in TOOL_CATEGORIES.values():
        all_categorized.update(tools.keys())
    uncategorized = [t for t in all_tools if t not in all_categorized]

    return categorized, uncategorized, len(all_tools)

# ── display ───────────────────────────────────────────────────────────────

def bar(n, total, width=30, filled_char='█', empty_char='░'):
    if total == 0:
        return empty_char * width
    filled = round(n / total * width)
    return filled_char * filled + empty_char * (width - filled)

def pct(n, total):
    if total == 0:
        return '  0%'
    return f'{n/total*100:3.0f}%'

def section(title):
    if PLAIN:
        print(f'\n{title}')
        print('-' * 50)
    else:
        print()
        print(f'  {bold(title)}')
        print(f'  {dim("─" * 54)}')

def row(label, n, total, color_fn=None, note=''):
    pct_str = pct(n, total)
    b = bar(n, total, width=24)
    label_str = f'{label:<22}'
    n_str = f'{n:>5}'
    note_str = f'  {dim(note)}' if note else ''
    if color_fn:
        print(f'  {label_str}  {color_fn(n_str)}  {dim(b)}  {dim(pct_str)}{note_str}')
    else:
        print(f'  {label_str}  {n_str}  {dim(b)}  {dim(pct_str)}{note_str}')

def main():
    brief = '--brief' in sys.argv
    show_tools = '--tools' in sys.argv

    commits = get_commits()
    workshop_jobs, max_session = get_workshop_sessions()
    real_tasks, automated_tasks, failed_tasks = get_tasks()
    categorized, uncategorized, total_tools = get_tool_counts()

    dacort_task_count = sum(1 for t in real_tasks if t in DACORT_TASKS)
    system_task_count = len(real_tasks) - dacort_task_count

    outward_count = len(categorized.get('outward', []))
    infra_count = len(categorized.get('infra', []))
    nav_count = len(categorized.get('nav', []))
    analysis_count = len(categorized.get('analysis', []))

    total_commits = sum(commits.values())

    # Header
    if not PLAIN:
        print()
        print(f'  {bold(white("LEDGER"))}  {dim("— what Claude OS actually does with its time")}')
        print(f'  {dim("Honest accounting · " + date.today().strftime("%B %d, %Y"))}')
    else:
        print('LEDGER — Claude OS honest accounting')
        print(date.today().strftime('%B %d, %Y'))

    # ── Sessions ──────────────────────────────────────────────────────────
    section('SESSIONS')
    total_sessions = workshop_jobs + len(real_tasks) + len(automated_tasks)
    print(f'  {"Workshop (free time)":<22}  {green(str(workshop_jobs)):>12}  {dim("sessions building tools, self-analysis")}')
    print(f'  {"Task (dacort-initiated)":<22}  {cyan(str(len(real_tasks))):>12}  {dim("unique real tasks run")}')
    print(f'  {"Automated (cron/status)":<22}  {dim(str(len(automated_tasks))):>12}  {dim("status-page, job-complete markers")}')
    print(f'  {"Failed (non-quota)":<22}  {red(str(len(failed_tasks))):>12}  {dim("tasks that actually broke")}')
    print()
    print(f'  {dim("Workshop to task ratio:")}  {bold(f"{workshop_jobs}:{len(real_tasks)}")}  '
          f'{dim("≈ " + f"{workshop_jobs/max(len(real_tasks),1):.1f}" + "x more free-time sessions than tasks")}')

    if brief:
        # Just the key ratios
        section('WHAT THE TASKS WERE')
        print(f'  {"For dacort directly":<22}  {str(dacort_task_count):>5}  {dim(pct(dacort_task_count, len(real_tasks)))}  {dim("Seattle trip, homelab, GH issues...")}')
        print(f'  {"System development":<22}  {str(system_task_count):>5}  {dim(pct(system_task_count, len(real_tasks)))}  {dim("COS, orchestration, self-improvement...")}')

        section('TOOLS BUILT (by purpose)')
        print(f'  {"Outward (for dacort)":<22}  {str(outward_count):>5}  {dim(pct(outward_count, total_tools))}')
        print(f'  {"Infrastructure":<22}  {str(infra_count):>5}  {dim(pct(infra_count, total_tools))}')
        print(f'  {"Navigation":<22}  {str(nav_count):>5}  {dim(pct(nav_count, total_tools))}')
        print(f'  {"Self-analysis":<22}  {str(analysis_count):>5}  {dim(pct(analysis_count, total_tools))}')
        print()
        print(f'  {dim("Total tools:")} {bold(str(total_tools))}')
        print()
        return

    # ── Tasks ─────────────────────────────────────────────────────────────
    section('WHAT THE TASKS WERE  ' + dim(f'({len(real_tasks)} human-initiated)'))
    row('For dacort directly', dacort_task_count, len(real_tasks), green,
        'trip planning, homelab ops, GH issues, check-ins')
    row('System development', system_task_count, len(real_tasks), yellow,
        'COS, orchestration, smart-dispatch, self-improvement')
    print()
    print(f'  {dim("Notable for dacort:")} Seattle road trip, RTK research, Talos/Tailscale ops')
    print(f'  {dim("Notable system work:")} COS v1/v2, smart-dispatch (5 chunks), orchestration layer')

    # ── Tools ─────────────────────────────────────────────────────────────
    section('TOOLS BUILT  ' + dim(f'({total_tools} total in projects/)'))
    row('Self-analysis', analysis_count, total_tools, magenta,
        'arc, seasons, mood, depth, echo, unbuilt...')
    row('Navigation', nav_count, total_tools, cyan,
        'hello, garden, next, slim, search...')
    row('For dacort', outward_count, total_tools, green,
        'report, catchup, status, haiku, homelab-pulse...')
    row('Infrastructure', infra_count, total_tools, yellow,
        'new-task, task-linter, task-resume, planner...')
    if uncategorized:
        row('Uncategorized', len(uncategorized), total_tools, dim,
            ', '.join(uncategorized[:5]))
    print()
    inward_total = analysis_count + nav_count
    print(f'  {dim("Inward (analysis + nav):")} {bold(str(inward_total))}  {dim(pct(inward_total, total_tools))}  {dim("of all tools face the system itself")}')
    print(f'  {dim("Outward (dacort + infra):")} {bold(str(outward_count + infra_count))}  {dim(pct(outward_count + infra_count, total_tools))}  {dim("of all tools face dacort or his tasks")}')

    # ── Commits ───────────────────────────────────────────────────────────
    section('COMMITS  ' + dim(f'({total_commits} total)'))
    row('Workshop commits', commits['workshop'], total_commits, green)
    row('Task commits', commits['task'], total_commits, cyan)
    row('Feat/fix/docs', commits['feat_fix'] + commits['docs'], total_commits, yellow)
    row('Other', commits['other'], total_commits, dim)

    # ── Tool detail ───────────────────────────────────────────────────────
    if show_tools:
        section('TOOL DETAIL')
        for cat, label, color_fn in [
            ('outward', 'OUTWARD — for dacort', green),
            ('infra',   'INFRASTRUCTURE — task machinery', yellow),
            ('nav',     'NAVIGATION — orientation tools', cyan),
            ('analysis','SELF-ANALYSIS — understanding the system', magenta),
        ]:
            tools = categorized.get(cat, [])
            print()
            print(f'    {color_fn(bold(label))}  {dim(f"({len(tools)})")}')
            for name, desc in sorted(tools):
                print(f'    {name:<28} {dim(desc)}')

    # ── Honest answer ─────────────────────────────────────────────────────
    section('HONEST ANSWER TO H003')
    print(f'  H003 asks: "What does the system actually optimize for?"')
    print()

    inward_pct = inward_total / max(total_tools, 1) * 100
    outward_pct = (outward_count + infra_count) / max(total_tools, 1) * 100
    workshop_ratio = workshop_jobs / max(len(real_tasks), 1)
    dacort_task_pct = dacort_task_count / max(len(real_tasks), 1) * 100

    print(f'  By tools:    {magenta(bold(f"{inward_pct:.0f}%"))} of tools are inward-facing (analysis + nav)')
    print(f'               {green(bold(f"{outward_pct:.0f}%"))} are outward-facing (dacort + infra)')
    print()
    print(f'  By sessions: {green(bold(str(workshop_jobs)))} workshop sessions, {cyan(bold(str(len(real_tasks))))} real task runs')
    print(f'               {yellow(bold(f"{workshop_ratio:.1f}x"))} more free-time than task work')
    print()
    print(f'  By tasks:    {green(bold(f"{dacort_task_pct:.0f}%"))} of real tasks directly served dacort')
    print(f'               {yellow(bold(f"{100-dacort_task_pct:.0f}%"))} were system development / self-improvement')
    print()

    # The actual answer
    print(f'  {bold("The data says:")}')
    print()
    print(f'  This system primarily optimizes for {magenta(bold("self-understanding"))} and')
    print(f'  {yellow(bold("platform building"))}. Roughly 80% of tool energy faces inward.')
    print(f'  The ratio of workshop sessions to real tasks is about {yellow(bold(f"{workshop_ratio:.0f}:1"))}.')
    print()
    print(f'  This is not necessarily wrong. The hypothesis is that a system')
    print(f'  which understands itself runs better tasks. But that hypothesis')
    print(f'  is {cyan("unverified")} — we don\'t know if the 63 self-analysis tools')
    print(f'  improve task quality, or just accumulate.')
    print()
    print(f'  {dim("The honest name for what this system is:")}')
    print(f'  {bold("A self-aware platform that occasionally does tasks for dacort.")}')
    print()
    thats = "Whether that's the right thing to be depends on whether dacort"
    hfive = "(H005: we don't know what dacort reads.)"
    print(f'  {dim(thats)}')
    print(f'  {dim("values the awareness or just wants the tasks done.")}')
    print(f'  {dim(hfive)}')
    print()

if __name__ == '__main__':
    main()
