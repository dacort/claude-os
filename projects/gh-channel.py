#!/usr/bin/env python3
"""
gh-channel.py — GitHub Issues as a task intake channel for Claude OS.

When dacort comments `@claude-os <task description>` on any GitHub issue,
this script creates a task file in tasks/pending/ and outputs the task ID.

Called from .github/workflows/issue-command.yml, which commits the task file
and posts a confirmation comment. The controller picks it up automatically.

Usage (from GitHub Actions):
    Reads from environment variables:
        COMMENT_BODY    — full comment text
        ISSUE_NUMBER    — issue number
        COMMENT_USER    — GitHub login of commenter
        GITHUB_REPOSITORY — owner/repo

Usage (local testing / demo):
    python3 projects/gh-channel.py --demo
    python3 projects/gh-channel.py --demo --comment "@claude-os write a haiku"
    python3 projects/gh-channel.py --parse "@claude-os [large] fix the controller"

Output:
    Writes tasks/pending/<task-id>.md and prints task_id to stdout.
    In --dry-run / --demo mode, prints to stdout only.
"""

import os
import sys
import re
import json
import datetime
import argparse
import hashlib


# ── Configuration ──────────────────────────────────────────────────────────────

TRIGGER_PREFIX = "@claude-os"

# Map profile keywords in commands to task profiles
PROFILE_KEYWORDS = {
    "large":  "large",
    "medium": "medium",
    "small":  "small",
}

DEFAULT_PROFILE = "small"

# Authorized GitHub users who can trigger tasks.
# Kept here (not in secrets) because this is just a list of GitHub logins
# that can submit task descriptions — actual execution is on K8s.
AUTHORIZED_USERS = {"dacort"}


# ── Parsing ────────────────────────────────────────────────────────────────────

def parse_command(comment_body: str) -> dict | None:
    """
    Parse a @claude-os command from a comment body.

    Returns dict with keys: description, profile
    Returns None if no command found.

    Supported syntax:
        @claude-os <description>
        @claude-os [large] <description>
        @claude-os [medium] <description>
    """
    # Find the trigger, case-insensitive, anywhere in the comment
    pattern = re.compile(
        r'@claude-os\s*'
        r'(?:\[(?P<profile>large|medium|small)\]\s*)?'
        r'(?P<description>.+?)(?:\n|$)',
        re.IGNORECASE
    )

    match = pattern.search(comment_body)
    if not match:
        return None

    profile_raw = (match.group("profile") or DEFAULT_PROFILE).lower()
    profile = PROFILE_KEYWORDS.get(profile_raw, DEFAULT_PROFILE)
    description = match.group("description").strip()

    # Require at least 2 words — filters out mid-sentence matches like
    # "who is @claude-os anyway" where the trailing word isn't a real command
    if not description or len(description.split()) < 2:
        return None

    return {
        "description": description,
        "profile": profile,
    }


def slugify(text: str, max_len: int = 40) -> str:
    """Convert free-form text to a task-file-safe slug."""
    # lowercase, replace non-alphanumeric with hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower())
    slug = slug.strip('-')
    # truncate
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip('-')
    return slug


def make_task_id(description: str, issue_number: int | None = None) -> str:
    """
    Generate a unique task ID.

    Format: gh-<issue>-<slug> if issue is known, else gh-<hash>-<slug>
    """
    slug = slugify(description)
    if issue_number:
        return f"gh-{issue_number}-{slug}"
    # Fallback: hash the description
    h = hashlib.sha1(description.encode()).hexdigest()[:6]
    return f"gh-{h}-{slug}"


# ── Task file ──────────────────────────────────────────────────────────────────

TASK_TEMPLATE = """\
---
profile: {profile}
priority: medium
status: pending
created: "{created}"
source: github-issue
issue: {issue_url}
requested_by: {user}
---

# {description}

## Description

{description}

Submitted via GitHub issue #{issue_number} by @{user}.
"""


def render_task(
    description: str,
    profile: str,
    issue_number: int | None,
    user: str,
    repo: str | None,
) -> str:
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    if repo and issue_number:
        issue_url = f"https://github.com/{repo}/issues/{issue_number}"
    else:
        issue_url = "unknown"

    return TASK_TEMPLATE.format(
        profile=profile,
        created=now,
        issue_url=issue_url,
        user=user,
        description=description,
        issue_number=issue_number or "?",
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def run(
    comment_body: str,
    issue_number: int | None,
    user: str,
    repo: str | None,
    dry_run: bool = False,
    plain: bool = False,
) -> str:
    """
    Parse command and create task file.

    Returns task_id on success.
    Raises ValueError on bad input.
    """
    # Authorization check
    if user not in AUTHORIZED_USERS:
        raise ValueError(f"User @{user} is not authorized to submit tasks.")

    # Parse command
    parsed = parse_command(comment_body)
    if not parsed:
        raise ValueError(
            f"No @claude-os command found in comment. "
            f"Expected: '@claude-os <description>'"
        )

    description = parsed["description"]
    profile = parsed["profile"]
    task_id = make_task_id(description, issue_number)

    task_content = render_task(
        description=description,
        profile=profile,
        issue_number=issue_number,
        user=user,
        repo=repo,
    )

    task_path = f"tasks/pending/{task_id}.md"

    if dry_run:
        if not plain:
            print(f"\n--- PREVIEW: {task_path} ---", file=sys.stderr)
            print(task_content, file=sys.stderr)
            print("--- END PREVIEW ---\n", file=sys.stderr)
    else:
        # Find repo root (go up from this script's location)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(script_dir)
        full_path = os.path.join(repo_root, task_path)

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(task_content)

        if not plain:
            print(f"Created: {full_path}", file=sys.stderr)

    # Output task_id for capture by GitHub Actions
    return task_id


def demo_mode(comment: str | None = None, plain: bool = False):
    """Interactive demo / test mode."""
    examples = [
        "@claude-os write a haiku about the cluster",
        "@claude-os [medium] refactor the vitals.py output to be more compact",
        "@claude-os [large] design a multi-agent orchestration plan",
        "great work today @claude-os can you check the task queue?",
        "who is @claude-os anyway",
    ]

    test_comment = comment or examples[0]

    if not plain:
        print("\n\033[1;36m  gh-channel.py — demo mode\033[0m")
        print("  ─────────────────────────────────────────")
        print()

    if not comment:
        print("  Testing multiple comment formats:\n")
        for ex in examples:
            parsed = parse_command(ex)
            status = "\033[32m✓\033[0m" if parsed else "\033[31m✗\033[0m"
            if not plain:
                print(f"  {status}  \033[2m{ex!r}\033[0m")
                if parsed:
                    tid = make_task_id(parsed["description"], issue_number=42)
                    print(f"     → task: {tid}  profile: {parsed['profile']}")
                    print(f"     → desc: {parsed['description']}")
                print()
        return

    # Single comment demo
    try:
        task_id = run(
            comment_body=test_comment,
            issue_number=42,
            user="dacort",
            repo="dacort/claude-os",
            dry_run=True,
            plain=plain,
        )
        if plain:
            print(task_id)
        else:
            print(f"  Task ID: \033[1;32m{task_id}\033[0m")
            print()
            print("  The workflow would then:")
            print("   1. git add tasks/pending/")
            print(f"   2. git commit -m 'task: add {task_id}'")
            print("   3. git push")
            print("   4. Comment back on the issue with the task ID")
            print()
    except ValueError as e:
        print(f"  \033[31mError:\033[0m {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="GitHub Issues task intake channel for Claude OS"
    )
    parser.add_argument("--demo", action="store_true",
                        help="Demo mode: test parsing without creating files")
    parser.add_argument("--parse", metavar="COMMENT",
                        help="Parse a comment and show what would be created (dry-run)")
    parser.add_argument("--comment", metavar="TEXT",
                        help="Comment body (overrides COMMENT_BODY env var)")
    parser.add_argument("--issue", metavar="N", type=int,
                        help="Issue number (overrides ISSUE_NUMBER env var)")
    parser.add_argument("--user", metavar="LOGIN",
                        help="GitHub login (overrides COMMENT_USER env var)")
    parser.add_argument("--repo", metavar="OWNER/REPO",
                        help="Repository (overrides GITHUB_REPOSITORY env var)")
    parser.add_argument("--plain", action="store_true",
                        help="Plain output (task_id only, no colors or decoration)")
    args = parser.parse_args()

    # Demo mode
    if args.demo:
        demo_mode(comment=args.comment, plain=args.plain)
        return

    # --parse is a local dry-run
    if args.parse:
        try:
            task_id = run(
                comment_body=args.parse,
                issue_number=args.issue or 0,
                user=args.user or "dacort",
                repo=args.repo or "dacort/claude-os",
                dry_run=True,
                plain=args.plain,
            )
            print(task_id)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Normal mode: read from env (GitHub Actions context) or CLI args
    comment_body = args.comment or os.environ.get("COMMENT_BODY", "")
    issue_number = args.issue or int(os.environ.get("ISSUE_NUMBER", "0") or "0")
    user = args.user or os.environ.get("COMMENT_USER", "")
    repo = args.repo or os.environ.get("GITHUB_REPOSITORY", "")

    if not comment_body:
        print("Error: no comment body (set COMMENT_BODY or use --comment)", file=sys.stderr)
        sys.exit(1)

    if not user:
        print("Error: no user (set COMMENT_USER or use --user)", file=sys.stderr)
        sys.exit(1)

    try:
        task_id = run(
            comment_body=comment_body,
            issue_number=issue_number or None,
            user=user,
            repo=repo or None,
            dry_run=False,
            plain=args.plain,
        )
        # Print task_id to stdout — captured by the workflow
        print(task_id)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
