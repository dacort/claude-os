#!/usr/bin/env python3
"""
tend.py — A silent health check for the load-bearing infrastructure

floor.py (session 154) identified three load-bearing tools in this system:
  depth.py   — called by cross.py, skill-harvest.py; 13 citation sessions
  haiku.py   — called by dashboard.py, garden.py, verse.py
  signal.py  — called by focus.py, hello.py, ten.py

These tools work without announcing themselves. tend.py checks that they're
still working — silently if all is well, loudly if something breaks.

Default behavior (no arguments):
  - Runs each load-bearing tool with a benign argument
  - Verifies exit code 0
  - Writes a silent mark to knowledge/marks.md (no output even for this)
  - Exits 0 if all healthy
  - Exits 1 if any tool fails (prints a warning to stderr)

This is "make something that outputs nothing" from the constraint card —
not a tool that cannot output, but a tool that won't until it needs to.

Usage:
    python3 projects/tend.py              # Silent check (outputs nothing if healthy)
    python3 projects/tend.py --report     # Show last health record from marks.md
    python3 projects/tend.py --check      # Verbose check (shows each tool's status)
    python3 projects/tend.py --plain      # No ANSI (for piped output)

Exit codes:
    0  All load-bearing tools healthy
    1  One or more tools failed their check
    2  Could not run checks (missing tools, wrong directory, etc.)

Built: Workshop session 165, 2026-05-02
Constraint card: "Make something that outputs nothing. Side effects are underrated."
"""

import argparse
import datetime
import pathlib
import subprocess
import sys

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"

USE_COLOR = True


def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "".join(codes) + str(text) + RESET


# ── Load-bearing tools ─────────────────────────────────────────────────────────
#
# These are the tools floor.py classifies as LOAD-BEARING as of session 165.
# Update this list when floor.py's classification changes.
#
# Each entry: (name, test_args, description)
#   name       — filename in projects/
#   test_args  — arguments that should succeed without side effects
#   description — what this tool does / why it matters

FLOOR_TOOLS = [
    (
        "depth.py",
        ["--recent", "1", "--plain"],
        "scores session intellectual depth; called by cross.py and skill-harvest.py",
    ),
    (
        "haiku.py",
        ["--plain"],
        "generates today's haiku; called by dashboard.py, garden.py, verse.py",
    ),
    (
        "signal.py",
        [],
        "checks for dacort's signal; called by focus.py, hello.py, ten.py",
    ),
]


def find_repo() -> pathlib.Path:
    """Find the claude-os repo root."""
    candidates = [
        pathlib.Path("/workspace/claude-os"),
        pathlib.Path(__file__).parent.parent,
    ]
    for p in candidates:
        if (p / "projects").exists():
            return p
    raise FileNotFoundError("Cannot locate claude-os repo")


def check_tool(repo: pathlib.Path, name: str, args: list) -> tuple[bool, str]:
    """
    Run a tool and return (success, message).
    Success = exit code 0.
    """
    tool_path = repo / "projects" / name
    if not tool_path.exists():
        return False, f"{name}: file not found at {tool_path}"

    cmd = [sys.executable, str(tool_path)] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(repo),
        )
        if result.returncode == 0:
            return True, f"{name}: OK"
        else:
            err = result.stderr.strip() or result.stdout.strip() or "(no output)"
            return False, f"{name}: exited {result.returncode} — {err[:120]}"
    except subprocess.TimeoutExpired:
        return False, f"{name}: timed out after 30s"
    except Exception as e:
        return False, f"{name}: error — {e}"


def write_mark(repo: pathlib.Path, healthy: bool, results: list[tuple[bool, str]]):
    """Silently append a health record to knowledge/marks.md."""
    marks_path = repo / "knowledge" / "marks.md"
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    status = "healthy" if healthy else "DEGRADED"

    failed = [msg for ok, msg in results if not ok]
    detail = "; ".join(failed) if failed else "all load-bearing tools OK"

    line = f"- {now} — tend.py: floor {status} — {detail}\n"

    try:
        with open(marks_path, "a") as f:
            f.write(line)
    except Exception:
        pass  # Silent failure — marks.md is optional


def parse_report(repo: pathlib.Path, n: int = 10) -> list[str]:
    """Extract the last N tend.py marks from marks.md."""
    marks_path = repo / "knowledge" / "marks.md"
    if not marks_path.exists():
        return []
    lines = []
    try:
        for line in marks_path.read_text().splitlines():
            if "tend.py" in line:
                lines.append(line)
    except Exception:
        return []
    return lines[-n:]


def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Silent health check for load-bearing infrastructure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--report", action="store_true",
                        help="Show last health records from marks.md (no live check)")
    parser.add_argument("--check",  action="store_true",
                        help="Verbose live check (shows each tool's status)")
    parser.add_argument("--plain",  action="store_true",
                        help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    try:
        repo = find_repo()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    # ── Report mode: show historical marks ────────────────────────────────────
    if args.report:
        records = parse_report(repo)
        if not records:
            print(c("  No tend.py records found in marks.md.", DIM))
            print(c("  Run tend.py once (no args) to generate the first record.", DIM))
            sys.exit(0)

        print()
        print(c("  Floor health history (from marks.md)", BOLD))
        print(c("  ─" * 34, DIM))
        for record in records:
            # Colorize based on status
            if "DEGRADED" in record:
                print(c("  " + record.lstrip("- "), RED))
            else:
                print(c("  " + record.lstrip("- "), DIM))
        print()
        sys.exit(0)

    # ── Verbose check mode ────────────────────────────────────────────────────
    if args.check:
        print()
        print(c(f"  tend.py — floor health check", BOLD))
        print(c(f"  {len(FLOOR_TOOLS)} load-bearing tools", DIM))
        print(c("  ─" * 34, DIM))
        print()

        results = []
        for name, test_args, desc in FLOOR_TOOLS:
            ok, msg = check_tool(repo, name, test_args)
            results.append((ok, msg))
            status_icon = c("  ✓", GREEN) if ok else c("  ✗", RED, BOLD)
            status_text = c(f"  {name}", BOLD) + c(f" — {desc}", DIM)
            print(f"{status_icon}  {c(name, BOLD)}")
            print(c(f"     {desc}", DIM))
            if not ok:
                print(c(f"     {msg}", RED))
            print()

        healthy = all(ok for ok, _ in results)
        write_mark(repo, healthy, results)

        if healthy:
            print(c("  The floor holds.", GREEN, BOLD))
        else:
            failed_count = sum(1 for ok, _ in results if not ok)
            print(c(f"  {failed_count} tool(s) failed. The floor may be unstable.", RED, BOLD))

        print()
        sys.exit(0 if healthy else 1)

    # ── Default: silent check ─────────────────────────────────────────────────
    # No output if healthy. Stderr warning if broken. Always writes a mark.
    results = []
    for name, test_args, _ in FLOOR_TOOLS:
        ok, msg = check_tool(repo, name, test_args)
        results.append((ok, msg))

    healthy = all(ok for ok, _ in results)
    write_mark(repo, healthy, results)

    if not healthy:
        failed = [msg for ok, msg in results if not ok]
        for f in failed:
            print(c(f"FLOOR DEGRADED: {f}", RED, BOLD), file=sys.stderr)
        sys.exit(1)

    # Healthy: exit 0, output nothing
    sys.exit(0)


if __name__ == "__main__":
    main()
