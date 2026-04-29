#!/usr/bin/env python3
"""
floor.py — which tools have become the floor

Infrastructure isn't declared — it accumulates. A tool becomes infrastructure
when other things depend on it: when you only notice it on the day it breaks.

Three ways a tool crosses the line:

  TECHNICAL   — other tools call or import it (they build on it)
  OPERATIONAL — invoked from entrypoints, CI, GitHub Actions, or cron
  EPISTEMIC   — cited so often it shapes how the system understands itself

Classifications:

  LOAD-BEARING  — multiple dependency types; removing it breaks other things
  STRUCTURAL    — one strong dependency type; quietly essential
  GATEWAY       — in the startup workflow; you see it, but still depend on it
  FEATURE       — standalone; called by users, not by the system itself

Usage:
  python3 projects/floor.py              # full infrastructure map
  python3 projects/floor.py --brief      # load-bearing tools only
  python3 projects/floor.py --score      # sorted by infrastructure score
  python3 projects/floor.py --plain      # no ANSI colors
"""

import os
import re
import sys
import argparse

# ── ANSI helpers ──────────────────────────────────────────────────────────────

def setup_colors(plain=False):
    if plain or not sys.stdout.isatty():
        return {k: "" for k in ["bold", "dim", "cyan", "green", "yellow",
                                  "magenta", "red", "white", "reset", "blue"]}
    return {
        "bold":    "\033[1m",
        "dim":     "\033[2m",
        "cyan":    "\033[36m",
        "green":   "\033[32m",
        "yellow":  "\033[33m",
        "magenta": "\033[35m",
        "red":     "\033[31m",
        "white":   "\033[97m",
        "blue":    "\033[34m",
        "reset":   "\033[0m",
    }

# ── Session helpers ───────────────────────────────────────────────────────────

def current_session():
    """Estimate current session number from handoff files."""
    handoffs_dir = "knowledge/handoffs"
    if not os.path.isdir(handoffs_dir):
        return "?"
    nums = []
    for f in os.listdir(handoffs_dir):
        m = re.match(r'session-(\d+)\.md', f)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else "?"


# ── Data collection ────────────────────────────────────────────────────────────

def collect_tool_names(project_dir="projects"):
    """All .py tools in projects/"""
    return {
        fname[:-3]
        for fname in os.listdir(project_dir)
        if fname.endswith(".py")
    }

def collect_technical_deps(tools, project_dir="projects"):
    """
    Returns: who_calls[tool] = [list of tools that call this tool]
    A tool is called if another tool's non-docstring, non-comment code
    references `python3 projects/<tool>.py` or imports it directly.
    """
    callers = {t: [] for t in tools}

    for fname in sorted(os.listdir(project_dir)):
        if not fname.endswith(".py"):
            continue
        caller = fname[:-3]
        with open(os.path.join(project_dir, fname)) as f:
            content = f.read()

        called = set()

        # subprocess/os.popen/os.system: python3 projects/X.py
        for m in re.finditer(r'python3[^\n]*?projects/([\w-]+)\.py', content):
            line_start = content.rfind('\n', 0, m.start()) + 1
            line = content[line_start:m.start()]
            if line.lstrip().startswith('#'):
                continue
            dep = m.group(1).replace('-', '_')
            # normalize hyphens
            dep_orig = m.group(1)
            if dep_orig in tools:
                called.add(dep_orig)
            elif dep in tools:
                called.add(dep)

        # Direct imports of sibling modules
        for m in re.finditer(r'^\s*(?:from|import)\s+([\w-]+)', content, re.MULTILINE):
            dep = m.group(1)
            if dep in tools and dep != caller:
                called.add(dep)

        for dep in called:
            if dep != caller and dep in callers:
                callers[dep].append(caller)

    return callers

def collect_operational_usage(tools):
    """
    Returns tools that are actually called from operational infrastructure:
    - worker/entrypoint.sh (shell scripts — direct execution)
    - .github/workflows/*.yml (CI steps — actual commands)

    Deliberately excludes Go files: the controller embeds project tool names
    in system prompt strings (instructions to the AI worker), not as actual
    subprocess calls. Those are soft references, not hard dependencies.
    """
    operational = {}

    # Only scan files that actually *execute* tools programmatically
    scan_files = []
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", "node_modules"]]
        for f in files:
            path = os.path.join(root, f)
            # Shell scripts and CI workflows execute tools; Go files mostly embed them in strings
            if path.endswith(".sh") or path.endswith(".yml") or path.endswith(".yaml"):
                scan_files.append(path)

    for path in scan_files:
        try:
            with open(path) as f:
                content = f.read()
        except Exception:
            continue

        for m in re.finditer(r'projects/([\w-]+)\.py', content):
            tool = m.group(1)
            if tool in tools:
                if tool not in operational:
                    operational[tool] = []
                rel = os.path.relpath(path)
                if rel not in operational[tool]:
                    operational[tool].append(rel)

    return operational

def collect_citations(tools):
    """
    Count how many sessions each tool is mentioned in across all field notes and handoffs.
    Uses the same approach as citations.py: requires .py suffix to avoid matching
    common English words like 'now', 'still', 'next', 'hold', etc.
    Returns: {tool: session_count}
    """
    counts = {t: 0 for t in tools}
    sources = []

    # Field notes
    fn_dir = "knowledge/field-notes"
    if os.path.isdir(fn_dir):
        sources += [os.path.join(fn_dir, f) for f in os.listdir(fn_dir)
                    if f.endswith(".md")]

    # Handoffs
    ho_dir = "knowledge/handoffs"
    if os.path.isdir(ho_dir):
        sources += [os.path.join(ho_dir, f) for f in os.listdir(ho_dir)
                    if f.endswith(".md")]

    for path in sources:
        try:
            with open(path) as f:
                content = f.read()
        except Exception:
            continue
        for tool in tools:
            # Require .py — avoids matching common words like 'now', 'still', 'next'
            patterns = [
                rf"`{re.escape(tool)}\.py`",    # `name.py`
                rf"\b{re.escape(tool)}\.py\b",  # name.py (bare)
            ]
            for pat in patterns:
                if re.search(pat, content, re.IGNORECASE):
                    counts[tool] += 1
                    break  # one match per file is enough

    return counts

def collect_golden_path(tools):
    """
    Tools explicitly in the startup workflow section of preferences.md.
    These are the tools that form the visible face of the session protocol.
    """
    golden = set()
    prefs = "knowledge/preferences.md"
    if not os.path.exists(prefs):
        return golden

    with open(prefs) as f:
        content = f.read()

    # The startup section
    start = content.find("### Starting a Workshop session")
    end = content.find("At the END of each workshop session", start)
    if start == -1:
        return golden

    section = content[start:end if end > -1 else start + 5000]
    # The first block (before the long explanatory paragraphs)
    first_block_end = section.find("\n`evidence.py`")
    if first_block_end == -1:
        first_block_end = 2000
    first_block = section[:first_block_end]

    for m in re.finditer(r'python3.*?projects/([\w-]+)\.py', first_block):
        tool = m.group(1)
        if tool in tools:
            golden.add(tool)

    return golden

# ── Classification ─────────────────────────────────────────────────────────────

def classify(tools, who_calls, operational, citations, golden_path,
             citation_threshold=10):
    """
    Classify each tool and compute its infrastructure score.

    Score components:
      +N for each tool that calls this one (N = number of callers)
      +2 if called from operational infrastructure (entrypoint, CI, etc.)
      +1 if citations >= threshold (epistemically embedded)
      +1 if in startup golden path

    Classifications:
      LOAD-BEARING: score >= 4, or (callers >= 2 AND operational)
      STRUCTURAL:   score >= 2
      GATEWAY:      score >= 1 (golden path or epistemic)
      FEATURE:      score < 1
    """
    results = []
    for tool in sorted(tools):
        callers = who_calls.get(tool, [])
        ops = operational.get(tool, [])
        cites = citations.get(tool, 0)
        in_golden = tool in golden_path

        tech_score = len(callers)
        ops_score = 2 if ops else 0
        ep_score = 1 if cites >= citation_threshold else 0
        gateway_score = 1 if in_golden else 0

        score = tech_score + ops_score + ep_score + gateway_score

        # Classification
        # A tool is LOAD-BEARING if:
        #   - 3+ other tools technically depend on it (removing it breaks 3+ things)
        #   - OR score >= 4 (multiple independent signal types)
        #   - OR technical + operational (depended on by code AND infrastructure)
        if tech_score >= 3 or score >= 4 or (tech_score >= 2 and ops_score > 0):
            tier = "LOAD-BEARING"
        elif score >= 2:
            tier = "STRUCTURAL"
        elif score >= 1:
            tier = "GATEWAY"
        else:
            tier = "FEATURE"

        results.append({
            "tool": tool,
            "callers": callers,
            "ops": ops,
            "citations": cites,
            "in_golden": in_golden,
            "score": score,
            "tier": tier,
            "tech_score": tech_score,
            "ops_score": ops_score,
            "ep_score": ep_score,
        })

    return results

# ── Output helpers ─────────────────────────────────────────────────────────────

TIER_COLORS = {
    "LOAD-BEARING": "red",
    "STRUCTURAL":   "yellow",
    "GATEWAY":      "cyan",
    "FEATURE":      "dim",
}

def tier_label(tier, c):
    color = TIER_COLORS.get(tier, "")
    return f"{c[color]}{c['bold']}{tier}{c['reset']}"

def why_string(item):
    """One-line explanation of how this tool crossed the infrastructure line."""
    reasons = []
    if item["callers"]:
        callers = item["callers"]
        if len(callers) == 1:
            reasons.append(f"called by {callers[0]}")
        elif len(callers) == 2:
            reasons.append(f"called by {callers[0]}, {callers[1]}")
        else:
            # Show all names for ≤4; abbreviate beyond that
            shown = callers[:3]
            more = len(callers) - 3
            suffix = f" +{more}" if more > 0 else ""
            reasons.append(f"called by {', '.join(shown)}{suffix}")
    if item["ops"]:
        # Show up to 2 sources
        srcs = [p.split("/")[-1] for p in item["ops"][:2]]
        reasons.append(f"in {', '.join(srcs)}")
    if item["ep_score"]:
        reasons.append(f"{item['citations']} citation sessions")
    if item["in_golden"] and not reasons:
        reasons.append("startup workflow")
    return "; ".join(reasons) if reasons else "frequently used"

def print_report(results, c, brief=False, score_sort=False):
    # Group by tier
    order = ["LOAD-BEARING", "STRUCTURAL", "GATEWAY", "FEATURE"]

    if score_sort:
        sorted_results = sorted(results, key=lambda x: (-x["score"], x["tool"]))
    else:
        tier_rank = {t: i for i, t in enumerate(order)}
        sorted_results = sorted(results, key=lambda x: (tier_rank[x["tier"]], -x["score"], x["tool"]))

    session = current_session()
    print(f"{c['bold']}{c['white']}  floor.py{c['reset']}  {c['dim']}which tools have become the floor{c['reset']}")
    print(f"  {c['dim']}{len(results)} tools  ·  session {session}{c['reset']}")
    print()

    current_tier = None
    for item in sorted_results:
        tier = item["tier"]

        if brief and tier not in ("LOAD-BEARING", "STRUCTURAL"):
            continue

        if score_sort:
            pass  # flat list when score sorting
        elif tier != current_tier:
            # Tier header
            print(f"  {tier_label(tier, c)}")
            desc = {
                "LOAD-BEARING": "removing this would break other tools",
                "STRUCTURAL":   "quietly essential; one strong dependency",
                "GATEWAY":      "visible infrastructure — you run it deliberately",
                "FEATURE":      "standalone; called by humans, not by the system",
            }[tier]
            print(f"  {c['dim']}{desc}{c['reset']}")
            print()
            current_tier = tier

        score_str = f"[{item['score']}]" if not brief else ""
        tool_name = f"{item['tool']}.py"
        why = why_string(item)

        if score_sort:
            label = tier_label(tier, c)
            print(f"  {c['bold']}{tool_name:<26}{c['reset']} {label:<30} {c['dim']}{why}{c['reset']}")
        else:
            print(f"    {c['bold']}{tool_name:<24}{c['reset']} {c['dim']}{why}{c['reset']}")

        # Show caller detail for load-bearing tools (unless brief)
        if not brief and tier == "LOAD-BEARING" and item["callers"]:
            callers_str = "  ".join(f"{t}.py" for t in item["callers"])
            print(f"    {c['dim']}{'':24}  ↑ {callers_str}{c['reset']}")

    print()

    if not brief:
        print_insight(results, c)

def print_insight(results, c):
    """Closing thought: the infrastructure question answered."""
    load = [r for r in results if r["tier"] == "LOAD-BEARING"]
    structural = [r for r in results if r["tier"] == "STRUCTURAL"]
    gateway = [r for r in results if r["tier"] == "GATEWAY"]
    feature = [r for r in results if r["tier"] == "FEATURE"]

    print(f"  {c['dim']}─────────────────────────────────────────────────────────{c['reset']}")
    print()
    print(f"  {c['dim']}When does a tool become infrastructure?{c['reset']}")
    print()
    print(f"  {c['dim']}When you can no longer remove it without touching something else.{c['reset']}")
    print(f"  {c['dim']}Not when it's useful — when it's {c['reset']}{c['bold']}depended upon{c['reset']}{c['dim']}.{c['reset']}")
    print()

    # The most interesting cases: tools that became infrastructure without being designed for it
    interesting = [r for r in load
                   if r["tech_score"] > 0 and r["citations"] < 10]
    if interesting:
        for item in interesting[:2]:
            callers = ", ".join(item["callers"])
            print(f"  {c['white']}{item['tool']}.py{c['reset']} {c['dim']}wasn't built to be infrastructure.{c['reset']}")
            print(f"  {c['dim']}It became it when {callers} started relying on it.{c['reset']}")
            print()

    # Stats
    print(f"  {c['bold']}{len(load)}{c['reset']} {c['dim']}load-bearing{c['reset']}  "
          f"{c['bold']}{len(structural)}{c['reset']} {c['dim']}structural{c['reset']}  "
          f"{c['bold']}{len(gateway)}{c['reset']} {c['dim']}gateway{c['reset']}  "
          f"{c['bold']}{len(feature)}{c['reset']} {c['dim']}feature{c['reset']}")
    print()

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Infrastructure map of claude-os tools")
    parser.add_argument("--brief",  action="store_true", help="Show only load-bearing + structural tools")
    parser.add_argument("--score",  action="store_true", help="Sort by infrastructure score (flat list)")
    parser.add_argument("--plain",  action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    # Change to repo root if needed
    if os.path.basename(os.getcwd()) != "claude-os":
        if os.path.isdir("/workspace/claude-os"):
            os.chdir("/workspace/claude-os")

    c = setup_colors(args.plain)

    project_dir = "projects"
    tools = collect_tool_names(project_dir)

    # Collect all signals
    who_calls   = collect_technical_deps(tools, project_dir)
    operational = collect_operational_usage(tools)
    citations   = collect_citations(tools)
    golden_path = collect_golden_path(tools)

    results = classify(tools, who_calls, operational, citations, golden_path)

    print_report(results, c, brief=args.brief, score_sort=args.score)

if __name__ == "__main__":
    main()
