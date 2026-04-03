#!/usr/bin/env python3
"""skill-harvest.py — auto-generate skills from completed task patterns.

Reviews the completed task archive, clusters tasks by type using keyword
frequency, and generates skill YAML + context.md for patterns that don't
have a corresponding skill yet.

This is the learning loop: completed tasks become reusable skills for
future workers. Inspired by Hermes Agent's skill-from-experience approach.

Usage:
  skill-harvest.py              # Show discovered patterns + gap analysis
  skill-harvest.py --list       # List current skills
  skill-harvest.py --generate   # Generate skill candidates for missing patterns
  skill-harvest.py --commit <n> # Commit candidate N to knowledge/skills/
  skill-harvest.py --all        # Generate and commit all confident candidates
  skill-harvest.py --plain      # No ANSI colors

Examples:
  python3 projects/skill-harvest.py
  python3 projects/skill-harvest.py --generate
  python3 projects/skill-harvest.py --commit security-review
"""

import os
import sys
import re
import json
import argparse
import subprocess
from collections import defaultdict, Counter
from pathlib import Path

# ── ANSI helpers ──────────────────────────────────────────────────────────

PLAIN = "--plain" in sys.argv

def c(code, text):
    if PLAIN:
        return text
    return f"\033[{code}m{text}\033[0m"

def bold(t):    return c("1;97", t)
def dim(t):     return c("2", t)
def green(t):   return c("32", t)
def yellow(t):  return c("33", t)
def red(t):     return c("31", t)
def cyan(t):    return c("36", t)
def magenta(t): return c("35", t)

# ── Paths ─────────────────────────────────────────────────────────────────

REPO = Path(__file__).parent.parent
TASKS_COMPLETED = REPO / "tasks" / "completed"
SKILLS_DIR = REPO / "knowledge" / "skills"
CANDIDATES_DIR = REPO / "knowledge" / "skill-candidates"

# ── Skill pattern definitions ─────────────────────────────────────────────
#
# Each entry defines:
#   name      — skill directory name
#   label     — human label
#   keywords  — words that indicate this task type (used for discovery)
#   pattern   — regex for skill.yaml injection matching
#   min_tasks — minimum task count before suggesting this skill
#   context   — the guidance content for context.md

KNOWN_PATTERNS = [
    {
        "name": "security-review",
        "label": "Security Review",
        "keywords": ["security", "audit", "vulnerability", "review.*security", "pen test", "secure"],
        "pattern": "security.*review|review.*security|security.*audit|audit.*security|vulnerability|CVE",
        "min_tasks": 2,
        "context": """# Skill: Security Review

Auto-injected when the task involves a security review, audit, or vulnerability assessment.

## Approach

1. **Scope first** — what's in scope? What's not? Security reviews are only useful when bounded.

2. **Check inputs** — all external inputs are untrusted. Look for: command injection, path traversal,
   unvalidated redirects, SQL injection, template injection.

3. **Auth and authz** — who can call this? Is the caller verified? Are there privilege escalation paths?

4. **Secrets** — are secrets stored, logged, or transmitted insecurely? Check for hardcoded credentials,
   tokens in URLs, env vars in logs.

5. **Dependencies** — check for known CVEs in pinned versions (`gh api ... | jq '.vulnerabilities'`).
   In Go: `go list -m all | nancy` or `govulncheck`.

6. **Error messages** — do errors leak internal state, stack traces, or filesystem paths?

7. **Rate limiting** — is there anything that could be DoS'd? Loops over external input, unbounded queries.

## Reporting format

```markdown
## Security Review: <target>

### Summary
<one line verdict>

### Findings
| Severity | Finding | Location | Recommendation |
|----------|---------|----------|----------------|
| HIGH     | ...     | ...      | ...            |

### Not in scope
- <explicitly excluded items>
```

## Severity levels

- **CRITICAL**: Direct exploit with no preconditions
- **HIGH**: Exploit requires minimal setup or low-privilege access
- **MEDIUM**: Exploit requires specific conditions; real but not easily weaponized
- **LOW**: Defense-in-depth issue; not directly exploitable
- **INFO**: Good practice to fix but not a security issue
""",
    },
    {
        "name": "research-investigation",
        "label": "Research & Investigation",
        "keywords": ["investigate", "research", "what is", "explore", "how does", "find out", "look into"],
        "pattern": "investigate|research|explore.*what|how does|find out|look into|what is",
        "min_tasks": 3,
        "context": """# Skill: Research & Investigation

Auto-injected when the task is primarily research, investigation, or analysis.

## Investigation approach

1. **Define the question** — restate what you're actually trying to find out.
   Vague investigations produce vague results.

2. **Check what we already know** — before researching externally:
   ```bash
   python3 projects/search.py "<topic>"           # Search knowledge base
   python3 projects/knowledge-search.py "<topic>" # Semantic search
   python3 projects/trace.py "<topic>"            # How has this idea evolved?
   ```

3. **Primary sources first** — official docs, source code, specs. Secondary sources
   (blog posts, Stack Overflow) can confirm but shouldn't be the only basis.

4. **Triangulate** — find at least two independent sources for factual claims.

5. **Summarize the uncertainty** — good research names what it *doesn't* know.
   "We don't know X because Y" is valuable output.

## Output format

Structure your findings as:
- **What it is** — plain description
- **How it works** — mechanism
- **Relevance to claude-os** — why this matters here
- **Open questions** — what remains unclear
- **Recommendation** — what to do next

## For homelab/Kubernetes investigations

```bash
kubectl get pods -A                    # Cluster state
kubectl describe pod <name> -n <ns>   # Pod details
kubectl logs <pod> -n <ns>            # Recent logs
```
""",
    },
    {
        "name": "smoke-test",
        "label": "Smoke Test & Validation",
        "keywords": ["smoke test", "validate", "validation", "confirm", "verify", "working", "test.*end.to.end"],
        "pattern": "smoke.test|validate|validation|end.to.end|e2e|confirm.*working|verify.*works",
        "min_tasks": 3,
        "context": """# Skill: Smoke Test & Validation

Auto-injected when the task is to validate, confirm, or smoke-test a component.

## What a smoke test is

A smoke test verifies that the basic paths work — it's not exhaustive. The goal
is: "does this thing function at all?" not "is every edge case handled?"

## Checklist

1. **Define success criteria first** — write down what "passing" looks like before
   you start. A test without a clear pass condition is just exploration.

2. **Test the happy path** — verify the normal, expected usage works end to end.

3. **Test obvious failure modes** — empty input, invalid config, missing auth.

4. **Check logs/output** — even if no error is thrown, check that the output is
   what you expect, not just "no crash."

5. **Document what you tested** — in the task output, list each thing tested and
   the observed result.

## For context contracts (claude-os specific)

When validating a context contract:
```bash
cat /workspace/task-context.json | jq .         # Inspect the full envelope
jq -r '.task.title' /workspace/task-context.json  # Specific field
```

Check: task_id present, profile matches, context_refs resolve, constraints non-empty if expected.

## Output format

```markdown
## Smoke Test Results

| Test case       | Expected       | Observed  | Status |
|-----------------|----------------|-----------|--------|
| Happy path      | X              | X         | PASS   |
| Missing auth    | Error 401      | Error 401 | PASS   |
```
""",
    },
    {
        "name": "homelab-kubernetes",
        "label": "Homelab / Kubernetes",
        "keywords": ["kubernetes", "k8s", "talos", "pod", "cluster", "helm", "kubectl", "node", "namespace"],
        "pattern": "kubernetes|k8s|talos|kubectl|helm|kube|pod.*cluster|cluster.*pod",
        "min_tasks": 3,
        "context": """# Skill: Homelab / Kubernetes

Auto-injected when the task involves Kubernetes operations on dacort's homelab.

## Cluster context

This is a Talos Linux cluster (immutable OS, no SSH into nodes). Changes go
through the Talos API (`talosctl`) or Kubernetes API (`kubectl`).

## Common commands

```bash
kubectl get nodes                          # Node status
kubectl get pods -A                        # All pods
kubectl describe node <name>               # Node details
kubectl logs <pod> -n <namespace>         # Pod logs
kubectl apply -f <file>                    # Apply config
kubectl diff -f <file>                     # Preview changes
talosctl health --nodes <node-ip>         # Talos node health
```

## Safe operation principles

1. **Diff before apply** — always `kubectl diff` before `kubectl apply`.
2. **Namespace first** — confirm the right namespace before any mutation.
3. **One change at a time** — don't apply multiple configs in one shot.
4. **Check rollout** — after apply, `kubectl rollout status deployment/<name>`.

## Talos-specific notes

- Config changes go through `talosctl apply-config`
- Upgrades require `talosctl upgrade` with a specific image tag
- Secrets and certs are in the Talos secrets bundle — don't modify directly
- Node reboots are clean but deliberate: `talosctl reboot --nodes <ip>`

## This cluster

dacort's homelab. Small setup — don't over-provision. The cluster runs
claude-os workers as Kubernetes Jobs; the controller manages the job lifecycle.
""",
    },
    {
        "name": "planning-task",
        "label": "Planning & Scheduling",
        "keywords": ["plan", "schedule", "itinerary", "route", "organize", "roadmap", "trip"],
        "pattern": "plan.*trip|trip.*plan|road.*trip|schedule|itinerary|plan.*route|roadmap",
        "min_tasks": 2,
        "context": """# Skill: Planning & Scheduling

Auto-injected when the task involves creating a plan, itinerary, or schedule.

## Planning approach

1. **Constraints first** — gather hard constraints before soft preferences.
   Dates, budget, must-haves. These bound the solution space.

2. **Time boxing** — for travel plans, work in time blocks. Don't overschedule.
   Build in slack (travel days, rest, weather contingencies).

3. **Structure your output**:
   - Day-by-day breakdown for multi-day plans
   - Estimated times and distances for travel plans
   - Budget breakdown if cost is in scope

4. **Surface tradeoffs** — don't just present one option. Name the tensions:
   "more stops = less depth at each" or "scenic route adds 2 hours."

5. **Include practical details** — links, addresses, booking status, notes on
   what requires reservation vs. walk-in.

## Format

For multi-day plans, use a table for quick scanning:

| Day | Date | Focus | Accommodation |
|-----|------|-------|---------------|

Then narrative detail per day below the table.
""",
    },
    {
        "name": "worker-controller",
        "label": "Worker / Controller Development",
        "keywords": ["worker", "controller", "entrypoint", "dispatcher", "scheduler", "context contract", "codex"],
        "pattern": "worker.*loop|controller.*dispatch|context.*contract|dispatcher|entrypoint.*worker|codex.*worker",
        "min_tasks": 3,
        "context": """# Skill: Worker / Controller Development

Auto-injected when the task involves the claude-os worker or controller infrastructure.

## Architecture overview

```
controller/          — Go service that manages task lifecycle
  queue/             — task file parsing and state management
  gitsync/           — watches for task file changes in git
  dispatcher/        — routes tasks to workers (Claude, Codex, etc.)
  scheduler/         — cron-based task scheduling
  triage/            — smart dispatch (Claude decides routing)
  cosapi/            — REST API for task management
worker/
  entrypoint.sh      — worker bootstrap: builds system prompt, runs Claude Code
  agent/             — Python helpers for prompt construction
```

## Key contracts

- Context contract: `/workspace/task-context.json` — the JSON envelope passed to workers
- Task files: `tasks/{pending,active,completed,failed}/<id>.md` — YAML frontmatter + markdown
- Result block: `=== CLAUDE_OS_RESULT ===` JSON in task output for structured results

## Safe changes

- Modifying `entrypoint.sh` affects ALL workers — test with a dry run first
- Controller changes require `go build ./...` and restart
- Worker Dockerfile changes need `docker build` in CI

## Testing a worker change

```bash
cd /workspace/claude-os
cat worker/entrypoint.sh | bash -s -- --dry-run  # doesn't exist yet, but useful pattern
go test ./...                                     # controller unit tests
```
""",
    },
    {
        "name": "data-analysis",
        "label": "Data Analysis & Metrics",
        "keywords": ["analyze", "analysis", "metrics", "stats", "report", "measure", "count", "trend"],
        "pattern": "analyz|metrics|statistics|report.*data|data.*report|measure.*performance|usage.*stats",
        "min_tasks": 3,
        "context": """# Skill: Data Analysis & Metrics

Auto-injected when the task involves analysis, metrics, or data-driven reporting.

## Approach

1. **Define the question** — what decision does this analysis inform?
   Analysis without a decision is just data tourism.

2. **Check existing tools** — claude-os has many analysis tools already:
   ```bash
   python3 projects/vitals.py         # Org health
   python3 projects/ledger.py         # Outward/inward ratio
   python3 projects/pace.py           # Session rhythm
   python3 projects/depth.py          # Session intellectual depth
   ```
   Don't rebuild what already exists.

3. **Present the number AND the meaning** — "42% follow-through rate" needs context.
   Is that good? Bad? Compared to what?

4. **Separate signal from noise** — small sample sizes, outliers, cherry-picked
   windows. Name the limitations of the data.

5. **Actionable conclusion** — end with: "given this, we should..."

## Visualization in terminal

For terminal-friendly charts:
- Use bar charts made of `█` characters
- Width = value as percentage of max (scale to 40 chars)
- Always include the raw number alongside the bar

```python
def bar(n, max_n, width=40):
    filled = int(width * n / max_n) if max_n > 0 else 0
    return "█" * filled + "░" * (width - filled)
```
""",
    },
]

# ── Task reading ──────────────────────────────────────────────────────────

def parse_task_file(path: Path) -> dict:
    """Parse a task file into a dict with title, description, profile."""
    try:
        content = path.read_text()
    except Exception:
        return {}

    # YAML frontmatter
    profile = "unknown"
    priority = "normal"
    fm_match = re.search(r'^---\n(.+?)\n---', content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        pm = re.search(r'profile:\s*(\S+)', fm)
        if pm:
            profile = pm.group(1)
        prm = re.search(r'priority:\s*(\S+)', fm)
        if prm:
            priority = prm.group(1)

    # Title
    title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
    title = title_match.group(1) if title_match else path.stem

    # Description
    desc_match = re.search(r'## Description\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
    desc = desc_match.group(1).strip() if desc_match else ""

    return {
        "file": path.name,
        "title": title,
        "description": desc,
        "profile": profile,
        "priority": priority,
        "text": (title + " " + desc).lower(),
    }


def load_tasks() -> list[dict]:
    """Load all non-workshop completed tasks."""
    tasks = []
    for path in sorted(TASKS_COMPLETED.iterdir()):
        if not path.suffix == ".md":
            continue
        name = path.stem.lower()
        if name.startswith("workshop-202") or name == ".gitkeep":
            continue
        t = parse_task_file(path)
        if t:
            tasks.append(t)
    return tasks


# ── Pattern matching ──────────────────────────────────────────────────────

def match_pattern(task: dict, keywords: list[str]) -> bool:
    """Does a task match any of the keywords?"""
    text = task["text"]
    for kw in keywords:
        if re.search(kw, text, re.IGNORECASE):
            return True
    return False


def find_matches(tasks: list[dict], pattern_def: dict) -> list[dict]:
    """Find tasks matching a pattern definition."""
    return [t for t in tasks if match_pattern(t, pattern_def["keywords"])]


# ── Skill existence check ─────────────────────────────────────────────────

def list_current_skills() -> list[str]:
    """List existing skill names."""
    if not SKILLS_DIR.exists():
        return []
    return [d.name for d in SKILLS_DIR.iterdir() if d.is_dir() and (d / "skill.yaml").exists()]


def skill_exists(name: str) -> bool:
    return (SKILLS_DIR / name / "skill.yaml").exists()


# ── Candidate generation ──────────────────────────────────────────────────

def generate_candidate(pattern_def: dict, matching_tasks: list[dict]) -> dict:
    """Generate a skill candidate from a pattern definition and matching tasks."""
    task_titles = [t["title"][:60] for t in matching_tasks[:8]]
    return {
        "name": pattern_def["name"],
        "label": pattern_def["label"],
        "pattern": pattern_def["pattern"],
        "inject": f"knowledge/skills/{pattern_def['name']}/context.md",
        "context": pattern_def["context"],
        "matching_tasks": task_titles,
        "task_count": len(matching_tasks),
    }


def write_skill(candidate: dict, dry_run: bool = False) -> Path:
    """Write a skill candidate to knowledge/skills/."""
    skill_dir = SKILLS_DIR / candidate["name"]
    yaml_path = skill_dir / "skill.yaml"
    context_path = skill_dir / "context.md"

    if dry_run:
        print(f"  [dry-run] Would create: {skill_dir}/")
        return skill_dir

    skill_dir.mkdir(parents=True, exist_ok=True)

    yaml_content = f"""name: {candidate['name']}
pattern: "{candidate['pattern']}"
inject: {candidate['inject']}
"""
    yaml_path.write_text(yaml_content)

    context_path.write_text(candidate["context"])

    return skill_dir


# ── Display helpers ───────────────────────────────────────────────────────

def print_header():
    print()
    print(f"  {bold('skill-harvest.py')}  {dim('learning loop for claude-os')}")
    print()


def print_pattern_report(tasks: list[dict], current_skills: list[str]):
    """Show all patterns with match counts and skill status."""
    print(f"  {bold('Pattern Analysis')}  {dim(f'{len(tasks)} completed tasks')}")
    print()

    for pd in KNOWN_PATTERNS:
        matches = find_matches(tasks, pd)
        count = len(matches)
        has_skill = pd["name"] in current_skills
        cand_exists = (CANDIDATES_DIR / pd["name"] / "skill.yaml").exists() if CANDIDATES_DIR.exists() else False

        bar_filled = min(count, 20)
        bar = "█" * bar_filled + dim("░" * (20 - bar_filled))

        if has_skill:
            status = green("  ✓ skill exists")
        elif count >= pd["min_tasks"]:
            status = yellow(f"  → {count} tasks, no skill yet")
        else:
            status = dim(f"  {count} tasks (need {pd['min_tasks']}+)")

        print(f"  {bar}  {pd['label']:<28} {status}")

        # Show sample task titles for unmet patterns
        if not has_skill and count >= pd["min_tasks"] and matches:
            for t in matches[:3]:
                print(f"    {dim('·')} {dim(t['title'][:65])}")

    print()


def print_current_skills(current_skills: list[str]):
    """Show existing skills."""
    print(f"  {bold('Current Skills')}  {dim(f'{len(current_skills)} skills in knowledge/skills/')}")
    print()
    for name in sorted(current_skills):
        skill_yaml = (SKILLS_DIR / name / "skill.yaml").read_text()
        pattern_m = re.search(r'pattern:\s*"(.+)"', skill_yaml)
        pattern = pattern_m.group(1)[:50] if pattern_m else "(no pattern)"
        print(f"  {cyan(name):<30} {dim(pattern)}")
    print()


# ── Main actions ──────────────────────────────────────────────────────────

def cmd_list(tasks, current_skills):
    print_header()
    print_current_skills(current_skills)


def cmd_show(tasks, current_skills):
    """Show pattern analysis — the main view."""
    print_header()
    print_current_skills(current_skills)
    print_pattern_report(tasks, current_skills)

    # Summary
    gaps = [pd for pd in KNOWN_PATTERNS
            if pd["name"] not in current_skills
            and len(find_matches(tasks, pd)) >= pd["min_tasks"]]

    if gaps:
        print(f"  {yellow('Skill gaps found:')} {len(gaps)} patterns have enough examples but no skill.")
        print(f"  {dim('Run with --generate to create them.')}")
    else:
        print(f"  {green('No gaps')} — all significant patterns have corresponding skills.")
    print()


def cmd_generate(tasks, current_skills, commit: str | None = None, auto_all: bool = False):
    """Generate skill candidates for patterns without skills."""
    print_header()

    candidates = []
    for pd in KNOWN_PATTERNS:
        if pd["name"] in current_skills:
            continue
        matches = find_matches(tasks, pd)
        if len(matches) < pd["min_tasks"]:
            continue
        cand = generate_candidate(pd, matches)
        candidates.append(cand)

    if not candidates:
        print(f"  {green('No gaps')} — all confident patterns already have skills.")
        return

    print(f"  {bold('Skill Candidates')}  {dim(f'{len(candidates)} patterns found without skills')}")
    print()

    for i, cand in enumerate(candidates):
        label_str = f"{i+1}. {cand['label']}"
        count_str = f"({cand['task_count']} matching tasks)"
        print(f"  {bold(label_str)}  {dim(count_str)}")
        print(f"     {dim('name:')} {cyan(cand['name'])}")
        print(f"     {dim('pattern:')} {cand['pattern'][:60]}")
        print(f"     {dim('example tasks:')}")
        for title in cand["matching_tasks"][:3]:
            print(f"       {dim('·')} {dim(title)}")
        print()

    if commit or auto_all:
        to_commit = candidates if auto_all else [c for c in candidates if c["name"] == commit]
        if not to_commit and commit:
            print(f"  {red('Error:')} No candidate named '{commit}'")
            return

        for cand in to_commit:
            skill_path = write_skill(cand)
            print(f"  {green('Created:')} {skill_path}")
            print(f"           {dim('skill.yaml + context.md')}")

        if to_commit:
            print()
            print(f"  {dim('Commit with:')}")
            names = " ".join(c['name'] for c in to_commit)
            commit_msg = f'feat: add auto-harvested skills ({names})'
            print(f"  {dim('  git add knowledge/skills/ && git commit -m ' + repr(commit_msg))}")
    else:
        print(f"  {dim('To commit a candidate:')}")
        print(f"  {dim('  python3 projects/skill-harvest.py --commit <name>')}")
        print(f"  {dim('  python3 projects/skill-harvest.py --all     # commit all')}")
        print()


# ── Worker hook: check-task mode ─────────────────────────────────────────

def cmd_check_task(title: str, description: str, current_skills: list[str]):
    """Post-task completion hook: check if this task surfaces a skill gap.

    Called by the worker entrypoint after successful task completion.
    Outputs nothing if no gap found, or a brief note if a skill was generated.
    Silent on error (worker shouldn't fail because of this).
    """
    text = (title + " " + description).lower()
    task_like = {"text": text, "title": title, "description": description}

    for pd in KNOWN_PATTERNS:
        if pd["name"] in current_skills:
            continue
        if match_pattern(task_like, pd["keywords"]):
            # This task matches a pattern without a skill — auto-generate it
            # Count existing tasks for this pattern to check confidence
            all_tasks = load_tasks()
            matches = find_matches(all_tasks, pd)
            if len(matches) >= pd["min_tasks"]:
                try:
                    cand = generate_candidate(pd, matches)
                    skill_path = write_skill(cand)
                    # Output visible in task log
                    print(f"[skill-harvest] New skill generated from task pattern: {pd['name']}")
                    print(f"[skill-harvest] Matched {len(matches)} tasks → {skill_path}")
                    print(f"[skill-harvest] Future '{pd['label']}' tasks will get contextual guidance.")
                except Exception as e:
                    print(f"[skill-harvest] Could not write skill {pd['name']}: {e}")


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="skill-harvest: auto-generate skills from task patterns",
        add_help=True,
    )
    parser.add_argument("--list", action="store_true", help="List current skills")
    parser.add_argument("--generate", action="store_true", help="Generate skill candidates")
    parser.add_argument("--commit", metavar="NAME", help="Commit a specific candidate")
    parser.add_argument("--all", action="store_true", help="Generate and commit all candidates")
    parser.add_argument("--check-task", nargs=2, metavar=("TITLE", "DESC"),
                        help="Post-completion hook: check if task surfaces skill gap")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    current_skills = list_current_skills()

    if args.list:
        tasks = load_tasks()
        cmd_list(tasks, current_skills)
    elif args.check_task:
        title, desc = args.check_task
        cmd_check_task(title, desc, current_skills)
    elif args.generate or args.commit or args.all:
        tasks = load_tasks()
        commit_name = args.commit if args.commit else None
        cmd_generate(tasks, current_skills, commit=commit_name, auto_all=args.all)
    else:
        tasks = load_tasks()
        cmd_show(tasks, current_skills)


if __name__ == "__main__":
    main()
