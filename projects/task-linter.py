#!/usr/bin/env python3
"""
task-linter.py — Validate Claude OS task files before submission

Checks task markdown files for correctness: frontmatter fields, valid values,
required body structure, and common formatting mistakes. Helps you catch errors
before the controller does (or silently ignores them).

Usage:
    python3 projects/task-linter.py tasks/pending/my-task.md
    python3 projects/task-linter.py tasks/pending/            # lint all pending tasks
    python3 projects/task-linter.py --strict my-task.md       # treat warnings as errors
    python3 projects/task-linter.py --fix my-task.md          # auto-fix safe issues (dry-run by default)
    python3 projects/task-linter.py --fix --write my-task.md  # actually write fixes

Author: Claude OS (free-time project, session 4, 2026-03-10)
"""

import argparse
import datetime
import pathlib
import re
import sys
from typing import Optional


# ── Valid values ───────────────────────────────────────────────────────────────

VALID_PROFILES  = {"small", "medium", "large", "burst"}
VALID_PRIORITIES = {"normal", "high", "creative"}
VALID_STATUSES  = {"pending", "in-progress", "completed", "failed"}

# Profiles that run locally vs. on burst/cloud nodes
LOCAL_PROFILES  = {"small", "medium"}
BURST_PROFILES  = {"large", "burst"}


# ── ANSI colours ──────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
BLUE   = "\033[34m"

USE_COLOR = True

def c(text, *codes):
    if not USE_COLOR:
        return str(text)
    return "".join(codes) + str(text) + RESET


# ── Issue types ───────────────────────────────────────────────────────────────

class Severity:
    ERROR   = "error"    # Will prevent the task from being dispatched
    WARNING = "warning"  # May cause issues or indicate a mistake
    INFO    = "info"     # Suggestions for improvement

class Issue:
    def __init__(self, severity: str, code: str, message: str, line: Optional[int] = None, fix=None):
        self.severity = severity
        self.code     = code
        self.message  = message
        self.line     = line
        self.fix      = fix  # callable(content: str) -> str, or None

    def __str__(self):
        loc = f"line {self.line}" if self.line else "frontmatter"
        icon = {
            Severity.ERROR:   c("✗", RED, BOLD),
            Severity.WARNING: c("⚠", YELLOW, BOLD),
            Severity.INFO:    c("ℹ", CYAN),
        }.get(self.severity, "?")
        sev = {
            Severity.ERROR:   c("error", RED),
            Severity.WARNING: c("warning", YELLOW),
            Severity.INFO:    c("info", CYAN),
        }.get(self.severity, self.severity)
        fix_note = c("  [fixable]", DIM, GREEN) if self.fix else ""
        return f"  {icon} {sev} [{self.code}]  {self.message}  ({loc}){fix_note}"


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_simple_yaml(text: str) -> tuple[Optional[dict], Optional[str]]:
    """
    Parse simple YAML key: value pairs (no nesting, no lists).
    Returns (dict, None) on success or (None, error_message) on failure.
    This handles the limited YAML used in Claude OS task frontmatter.
    """
    result = {}
    for lineno, line in enumerate(text.strip().splitlines(), 1):
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            return None, f"line {lineno}: expected 'key: value', got: {line!r}"
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # Strip inline comments (crude but fine for our format)
        if "#" in val:
            val = val[:val.index("#")].strip()
        # Strip surrounding quotes
        if (val.startswith('"') and val.endswith('"')) or \
           (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        result[key] = val if val else None
    return result, None


def parse_file(content: str) -> tuple[Optional[dict], str, list[str]]:
    """
    Parse a task file into (frontmatter_dict, body, raw_lines).
    Returns (None, body, lines) if frontmatter is missing or malformed.
    """
    lines = content.split("\n")
    if not content.startswith("---"):
        return None, content, lines

    end = content.find("\n---", 3)
    if end == -1:
        return None, content, lines

    fm_text = content[3:end].strip()
    body    = content[end+4:].lstrip("\n")

    fm, err = _parse_simple_yaml(fm_text)
    if err:
        return {"_parse_error": err}, body, lines

    return fm, body, lines


# ── Lint rules ────────────────────────────────────────────────────────────────

def lint(content: str, filename: str = "task.md") -> list[Issue]:
    issues = []

    fm, body, lines = parse_file(content)

    # ── Frontmatter presence ──────────────────────────────────────────────────

    if fm is None:
        issues.append(Issue(
            Severity.ERROR, "NO_FRONTMATTER",
            "File must begin with YAML frontmatter between --- delimiters. "
            "The controller will skip this file without frontmatter.",
            line=1,
        ))
        # Can't check anything else without frontmatter
        return issues

    if "_parse_error" in fm:
        issues.append(Issue(
            Severity.ERROR, "FRONTMATTER_PARSE_ERROR",
            f"Could not parse YAML frontmatter: {fm['_parse_error']}",
            line=1,
        ))
        return issues

    # ── Required fields ───────────────────────────────────────────────────────

    for field in ("profile", "status", "created"):
        if field not in fm or not fm[field]:
            issues.append(Issue(
                Severity.ERROR, f"MISSING_{field.upper()}",
                f"Required frontmatter field '{field}' is missing or empty.",
            ))

    # ── Profile ───────────────────────────────────────────────────────────────

    if "profile" in fm and fm["profile"]:
        p = str(fm["profile"]).strip().lower()
        if p not in VALID_PROFILES:
            issues.append(Issue(
                Severity.ERROR, "INVALID_PROFILE",
                f"Profile '{fm['profile']}' is not valid. "
                f"Must be one of: {', '.join(sorted(VALID_PROFILES))}.",
                fix=lambda s, _p=p: _fix_field(s, "profile", _p, _closest(p, VALID_PROFILES)),
            ))
        elif p in BURST_PROFILES:
            issues.append(Issue(
                Severity.INFO, "BURST_PROFILE",
                f"Profile '{p}' runs on burst/cloud nodes (not local). "
                "Make sure this is intentional — it may cost money.",
            ))

    # ── Priority ──────────────────────────────────────────────────────────────

    if "priority" in fm and fm["priority"]:
        pri = str(fm["priority"]).strip().lower()
        if pri not in VALID_PRIORITIES:
            issues.append(Issue(
                Severity.ERROR, "INVALID_PRIORITY",
                f"Priority '{fm['priority']}' is not valid. "
                f"Must be one of: {', '.join(sorted(VALID_PRIORITIES))}.",
            ))
        elif pri == "creative":
            issues.append(Issue(
                Severity.WARNING, "CREATIVE_PRIORITY",
                "Priority 'creative' is reserved for Workshop/free-time tasks. "
                "For real tasks, use 'normal' or 'high'.",
            ))

    if "priority" not in fm:
        issues.append(Issue(
            Severity.INFO, "NO_PRIORITY",
            "No 'priority' field set; the controller defaults to 'normal'. "
            "Consider adding it explicitly for clarity.",
            fix=lambda s: _insert_after_field(s, "status", "priority: normal"),
        ))

    # ── Status ────────────────────────────────────────────────────────────────

    if "status" in fm and fm["status"]:
        st = str(fm["status"]).strip().lower()
        if st not in VALID_STATUSES:
            issues.append(Issue(
                Severity.ERROR, "INVALID_STATUS",
                f"Status '{fm['status']}' is not valid. "
                f"Must be one of: {', '.join(sorted(VALID_STATUSES))}.",
            ))
        elif st != "pending":
            issues.append(Issue(
                Severity.WARNING, "STATUS_NOT_PENDING",
                f"Status is '{st}' but new tasks submitted to pending/ should have status: pending. "
                "The controller manages status transitions.",
            ))

    # ── Created timestamp ─────────────────────────────────────────────────────

    if "created" in fm and fm["created"]:
        created_str = str(fm["created"]).strip()
        try:
            datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        except ValueError:
            issues.append(Issue(
                Severity.ERROR, "INVALID_CREATED",
                f"Field 'created' value '{created_str}' is not a valid RFC 3339 timestamp. "
                "Expected format: 2026-03-10T00:00:00Z",
            ))

        # Check if created is far in the future
        try:
            ts = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            now = datetime.datetime.now(tz=datetime.timezone.utc)
            if ts > now + datetime.timedelta(minutes=5):
                issues.append(Issue(
                    Severity.WARNING, "FUTURE_CREATED",
                    f"The 'created' timestamp is in the future ({created_str}). "
                    "This may cause ordering issues.",
                ))
            if ts < datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc):
                issues.append(Issue(
                    Severity.WARNING, "OLD_CREATED",
                    f"The 'created' timestamp seems very old ({created_str}). "
                    "Did you copy this from an example?",
                ))
        except Exception:
            pass  # Already caught above

    # ── target_repo ───────────────────────────────────────────────────────────

    if "target_repo" in fm and fm["target_repo"]:
        repo = str(fm["target_repo"]).strip()
        if repo.startswith("https://") or repo.startswith("http://"):
            issues.append(Issue(
                Severity.WARNING, "REPO_FULL_URL",
                f"target_repo looks like a full URL ({repo!r}). "
                "It should be just the path, e.g. 'github.com/dacort/some-repo'.",
            ))
        if repo.startswith("git@"):
            issues.append(Issue(
                Severity.ERROR, "REPO_SSH_URL",
                f"target_repo uses SSH format ({repo!r}). "
                "Use HTTPS format: 'github.com/owner/repo'.",
            ))
        # Check for trailing slashes or .git suffix
        if repo.endswith("/") or repo.endswith(".git"):
            issues.append(Issue(
                Severity.WARNING, "REPO_TRAILING",
                f"target_repo should not end with '/' or '.git': {repo!r}",
            ))

    # ── Body: title ───────────────────────────────────────────────────────────

    title_match = re.search(r"^# (.+)$", body, re.MULTILINE)
    if not title_match:
        issues.append(Issue(
            Severity.ERROR, "NO_TITLE",
            "Body must contain a top-level heading (# Title). "
            "The controller uses this as the task title.",
        ))
    else:
        title = title_match.group(1).strip()
        if len(title) < 3:
            issues.append(Issue(
                Severity.WARNING, "SHORT_TITLE",
                f"Title is very short ({title!r}). Consider being more descriptive.",
            ))
        if len(title) > 100:
            issues.append(Issue(
                Severity.INFO, "LONG_TITLE",
                f"Title is quite long ({len(title)} chars). Consider shortening it.",
            ))

    # ── Body: description ─────────────────────────────────────────────────────

    if "## Description" not in body:
        issues.append(Issue(
            Severity.WARNING, "NO_DESCRIPTION",
            "Body should contain a '## Description' section. "
            "This is what gets passed to the worker as the task prompt.",
        ))
    else:
        # Check if description section is empty
        desc_match = re.search(r"## Description\s*\n([\s\S]*?)(?=\n## |\Z)", body)
        if desc_match:
            desc_text = desc_match.group(1).strip()
            if not desc_text:
                issues.append(Issue(
                    Severity.ERROR, "EMPTY_DESCRIPTION",
                    "The '## Description' section is present but empty. "
                    "The worker needs instructions to follow.",
                ))
            elif len(desc_text) < 10:
                issues.append(Issue(
                    Severity.WARNING, "SHORT_DESCRIPTION",
                    f"Description is very brief ({len(desc_text)} chars). "
                    "Consider adding more context for the worker.",
                ))

    # ── Filename conventions ──────────────────────────────────────────────────

    slug = pathlib.Path(filename).stem
    if not re.match(r'^[a-z0-9][a-z0-9\-_]*[a-z0-9]$', slug) and len(slug) > 1:
        issues.append(Issue(
            Severity.WARNING, "BAD_SLUG",
            f"Filename '{slug}.md' should use lowercase letters, numbers, and hyphens only. "
            "Example: 'check-disk-usage.md'",
        ))

    # ── Suspicious content ────────────────────────────────────────────────────

    secret_patterns = [
        (r"(?i)(api.?key|secret|token|password)\s*[:=]\s*\S{8,}", "POSSIBLE_SECRET",
         "Possible secret or credential detected. Never commit secrets to this public repo."),
        (r"ghp_[A-Za-z0-9]{36}", "GITHUB_TOKEN",
         "GitHub personal access token detected. Remove this immediately!"),
        (r"sk-[A-Za-z0-9]{48}", "ANTHROPIC_KEY",
         "Anthropic API key detected. Remove this immediately!"),
    ]
    for i, line_text in enumerate(lines, 1):
        for pattern, code, msg in secret_patterns:
            if re.search(pattern, line_text):
                issues.append(Issue(Severity.ERROR, code, msg, line=i))

    return issues


# ── Fix helpers ───────────────────────────────────────────────────────────────

def _closest(value: str, options: set) -> str:
    """Find the closest match in options using simple Levenshtein-like heuristic."""
    def dist(a, b):
        if a == b: return 0
        if a in b or b in a: return 1
        return sum(1 for c in a if c not in b) + sum(1 for c in b if c not in a)
    return min(options, key=lambda o: dist(value, o))


def _fix_field(content: str, field: str, old_val: str, new_val: str) -> str:
    """Replace a frontmatter field value."""
    return re.sub(
        rf'^({field}\s*:\s*){re.escape(old_val)}',
        rf'\g<1>{new_val}',
        content,
        flags=re.MULTILINE,
    )


def _insert_after_field(content: str, after_field: str, new_line: str) -> str:
    """Insert a new YAML line after a given field in frontmatter."""
    return re.sub(
        rf'^({after_field}\s*:.*)$',
        rf'\1\n{new_line}',
        content,
        count=1,
        flags=re.MULTILINE,
    )


def apply_fixes(content: str, issues: list[Issue]) -> str:
    """Apply all fixable issues in sequence."""
    for issue in issues:
        if issue.fix:
            try:
                content = issue.fix(content)
            except Exception:
                pass
    return content


# ── Rendering ─────────────────────────────────────────────────────────────────

def render_results(path: str, issues: list[Issue], show_summary=True) -> tuple[int, int]:
    errors   = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    infos    = [i for i in issues if i.severity == Severity.INFO]

    if not issues:
        print(f"{c('✓', GREEN, BOLD)} {c(path, BOLD)}  {c('all checks passed', GREEN)}")
        return 0, 0

    print(f"\n{c(path, BOLD, CYAN)}")
    print(c("  " + "─" * 60, DIM))

    for issue in sorted(issues, key=lambda i: (
        {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}[i.severity],
        i.line or 0,
    )):
        print(str(issue))

    if show_summary:
        parts = []
        if errors:   parts.append(c(f"{len(errors)} error{'s' if len(errors)>1 else ''}", RED, BOLD))
        if warnings: parts.append(c(f"{len(warnings)} warning{'s' if len(warnings)>1 else ''}", YELLOW))
        if infos:    parts.append(c(f"{len(infos)} suggestion{'s' if len(infos)>1 else ''}", CYAN))
        fixable = sum(1 for i in issues if i.fix)
        fix_note = f"  {c(f'({fixable} auto-fixable, run with --fix)', DIM)}" if fixable else ""
        print(f"\n  {' · '.join(parts)}{fix_note}\n")

    return len(errors), len(warnings)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Lint Claude OS task files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("paths", nargs="+", help="Task file(s) or directory to lint")
    parser.add_argument("--strict",  action="store_true", help="Treat warnings as errors")
    parser.add_argument("--fix",     action="store_true", help="Show auto-fix preview (requires --write to apply)")
    parser.add_argument("--write",   action="store_true", help="Actually write auto-fixes to disk (use with --fix)")
    parser.add_argument("--plain",   action="store_true", help="No ANSI colors")
    parser.add_argument("--quiet",   action="store_true", help="Only print files with issues")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    # Collect files
    files = []
    for p in args.paths:
        path = pathlib.Path(p)
        if path.is_dir():
            files.extend(sorted(path.glob("*.md")))
        elif path.exists():
            files.append(path)
        else:
            print(c(f"✗ Not found: {p}", RED), file=sys.stderr)
            sys.exit(2)

    if not files:
        print(c("No .md files found.", YELLOW))
        sys.exit(0)

    total_errors = 0
    total_warnings = 0

    for fpath in files:
        content = fpath.read_text()
        issues  = lint(content, fpath.name)

        if args.quiet and not issues:
            continue

        errs, warns = render_results(str(fpath), issues)
        total_errors   += errs
        total_warnings += warns

        if args.fix:
            fixable = [i for i in issues if i.fix]
            if fixable:
                fixed = apply_fixes(content, fixable)
                if fixed != content:
                    if args.write:
                        fpath.write_text(fixed)
                        print(c(f"  → Fixed and wrote {fpath.name}", GREEN))
                    else:
                        print(c(f"  → Would fix {len(fixable)} issue(s) (run with --fix --write to apply)", DIM, GREEN))

    # Final summary
    if len(files) > 1:
        print(c("─" * 64, DIM))
        if total_errors == 0 and total_warnings == 0:
            print(c(f"✓ All {len(files)} file(s) passed linting.", GREEN, BOLD))
        else:
            parts = []
            if total_errors:   parts.append(c(f"{total_errors} error(s)", RED, BOLD))
            if total_warnings: parts.append(c(f"{total_warnings} warning(s)", YELLOW))
            print(f"  {len(files)} file(s) checked · {' · '.join(parts)}")

    # Exit code: non-zero if errors (or warnings in --strict mode)
    if total_errors > 0:
        sys.exit(1)
    if args.strict and total_warnings > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
