#!/usr/bin/env python3
"""
minimal.py — The essential claude-os controller in ~150 lines.

This is a design sketch, not production code. It asks: what is the irreducible
core of the system? What could you cut and still have something that works?

The real controller is 1,843 lines of Go with Redis, goroutines, governance,
workshop scheduling, and graceful shutdown. This is the same logic in Python
without the production machinery — stripped to the loop that matters.

Key insight: Redis is a performance optimization, not an essential component.
The git filesystem IS the queue. pending/ → in-progress/ → completed/failed/
is a complete state machine. You don't need a cache layer to run it.

Run this to see what gets printed, or trace through it mentally.
It won't work in the container (no kubectl in-cluster, no GITHUB_TOKEN),
but it compiles the architecture into something you can read in 5 minutes.

Usage:
    python3 projects/minimal.py --describe      # Print what each part does
    python3 projects/minimal.py --dry-run       # Show what tasks would run
"""

import os
import re
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

# ─── Config ──────────────────────────────────────────────────────────────────

REPO_URL    = "https://github.com/dacort/claude-os.git"
BRANCH      = "main"
LOCAL       = Path("/tmp/claude-os-minimal")
NAMESPACE   = "claude-os"
IMAGE       = "ghcr.io/dacort/claude-os-worker:latest"
POLL_SEC    = 30

PROFILES = {
    "small":  {"cpu": "250m",  "mem": "256Mi", "scratch": "5Gi"},
    "medium": {"cpu": "500m",  "mem": "512Mi", "scratch": "10Gi"},
    "burst":  {"cpu": "1000m", "mem": "2Gi",   "scratch": "20Gi"},
}


# ─── Git operations ───────────────────────────────────────────────────────────

def git(args: list[str], cwd: Path = LOCAL) -> str:
    """Run a git command, return stdout."""
    token = os.environ.get("GITHUB_TOKEN", "")
    env = os.environ.copy()
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd, env=env, capture_output=True, text=True
    )
    return result.stdout.strip()


def ensure_repo() -> None:
    """Clone the repo if it doesn't exist."""
    if not (LOCAL / ".git").exists():
        LOCAL.mkdir(parents=True, exist_ok=True)
        token = os.environ.get("GITHUB_TOKEN", "")
        clone_url = REPO_URL
        if token:
            clone_url = REPO_URL.replace("https://", f"https://x-access-token:{token}@")
        subprocess.run(["git", "clone", "--branch", BRANCH, "--single-branch", clone_url, str(LOCAL)])


def pull() -> None:
    """Pull latest from origin."""
    git(["-c", "user.name=Claude OS",
         "-c", "user.email=claude-os@noreply.github.com",
         "pull", "--rebase", "origin", BRANCH])


def commit_and_push(message: str, files: list[Path] = None) -> None:
    """Stage, commit, and push changes."""
    git(["add"] + ([str(f) for f in files] if files else ["-A"]))
    git(["-c", "user.name=Claude OS",
         "-c", "user.email=claude-os@noreply.github.com",
         "commit", "-m", message])
    git(["push", "origin", BRANCH])


# ─── Task file parsing ────────────────────────────────────────────────────────

def parse_task(path: Path) -> dict | None:
    """Parse YAML frontmatter from a task .md file."""
    text = path.read_text()
    if not text.startswith("---"):
        return None
    end = text.index("---", 3)
    front = text[3:end]
    data = {"path": path, "id": path.stem, "body": text[end + 3:].strip()}
    for line in front.strip().splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip().strip('"')
    # Extract title from first markdown heading
    for line in data["body"].splitlines():
        if line.startswith("# "):
            data["title"] = line[2:].strip()
            break
    return data


def scan_pending() -> list[dict]:
    """Return all tasks in tasks/pending/."""
    pending = LOCAL / "tasks" / "pending"
    if not pending.exists():
        return []
    tasks = []
    for f in sorted(pending.glob("*.md")):
        task = parse_task(f)
        if task:
            tasks.append(task)
    # Sort by priority: high > normal > creative
    priority_order = {"high": 0, "normal": 1, "creative": 2}
    tasks.sort(key=lambda t: priority_order.get(t.get("priority", "normal"), 1))
    return tasks


# ─── Kubernetes job management ────────────────────────────────────────────────

def create_job(task: dict) -> str:
    """Apply a K8s Job manifest for the task. Returns the job name."""
    profile = PROFILES.get(task.get("profile", "small"), PROFILES["small"])
    job_name = f"claude-os-{task['id'][:50].lower().replace('_', '-')}"

    manifest = f"""apiVersion: batch/v1
kind: Job
metadata:
  name: {job_name}
  namespace: {NAMESPACE}
  labels:
    app: claude-os-worker
    task-id: {task['id']}
spec:
  ttlSecondsAfterFinished: 3600
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      serviceAccountName: claude-os-controller
      containers:
      - name: worker
        image: {IMAGE}
        resources:
          requests:
            cpu: {profile['cpu']}
            memory: {profile['mem']}
        env:
        - name: TASK_ID
          value: "{task['id']}"
        - name: TASK_TITLE
          value: "{task.get('title', '')}"
        - name: TASK_DESCRIPTION
          value: "{task.get('body', '')[:500]}"
        - name: TARGET_REPO
          value: "{task.get('target_repo', '')}"
        envFrom:
        - secretRef:
            name: claude-os-github
        - secretRef:
            name: claude-os-anthropic
            optional: true
"""
    result = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=manifest.encode(),
        capture_output=True
    )
    return job_name


def watch_jobs() -> dict[str, str]:
    """Return {job_name: 'completed'|'failed'} for finished jobs."""
    result = subprocess.run(
        ["kubectl", "get", "jobs", "-n", NAMESPACE, "-o", "json",
         "-l", "app=claude-os-worker"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return {}
    items = json.loads(result.stdout).get("items", [])
    statuses = {}
    for job in items:
        name = job["metadata"]["name"]
        for cond in job.get("status", {}).get("conditions", []):
            if cond["status"] == "True":
                if cond["type"] == "Complete":
                    statuses[name] = "completed"
                elif cond["type"] == "Failed":
                    statuses[name] = "failed"
    return statuses


def move_task(task: dict, destination: str) -> None:
    """Move a task file from in-progress/ to completed/ or failed/."""
    src = task["path"]
    dst = LOCAL / "tasks" / destination / src.name
    src.rename(dst)
    task["path"] = dst


# ─── The main loop ────────────────────────────────────────────────────────────

def run(dry_run: bool = False) -> None:
    """
    This is claude-os.

    The entire system in one function:
    1. Pull git
    2. Scan pending tasks
    3. For each: move to in-progress, create K8s job, commit
    4. Watch jobs: on finish, move to completed/failed, commit

    No Redis. No goroutines. No governance (yet). Just the loop.
    """
    ensure_repo()
    active: dict[str, dict] = {}  # {job_name: task}

    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting minimal claude-os loop")

    while True:
        # Step 1: Sync
        pull()

        # Step 2: Dispatch new tasks
        for task in scan_pending():
            if dry_run:
                print(f"  [DRY RUN] Would dispatch: {task['id']} — {task.get('title', '?')}")
                continue

            # Move to in-progress
            in_prog_path = LOCAL / "tasks" / "in-progress" / task["path"].name
            task["path"].rename(in_prog_path)
            task["path"] = in_prog_path

            job_name = create_job(task)
            active[job_name] = task
            commit_and_push(
                f"task {task['id']}: dispatched",
                files=[in_prog_path]
            )
            print(f"  Dispatched: {task['id']} → {job_name}")

        # Step 3: Check running jobs
        if active:
            for job_name, status in watch_jobs().items():
                if job_name not in active:
                    continue
                task = active.pop(job_name)

                if status == "completed":
                    move_task(task, "completed")
                    commit_and_push(f"task {task['id']}: completed")
                    print(f"  Completed: {task['id']}")
                elif status == "failed":
                    move_task(task, "failed")
                    commit_and_push(f"task {task['id']}: failed")
                    print(f"  Failed: {task['id']}")

        time.sleep(POLL_SEC)


# ─── Describe mode ────────────────────────────────────────────────────────────

def describe() -> None:
    """Print a human-readable description of what each part does."""
    sections = {
        "Config (~10 lines)": [
            "Repo URL, branch, local clone path",
            "K8s namespace and worker image",
            "Resource profiles (small/medium/burst)",
        ],
        "Git operations (~30 lines)": [
            "ensure_repo(): clone if missing",
            "pull(): git pull --rebase origin main",
            "commit_and_push(): stage → commit → push",
        ],
        "Task parsing (~25 lines)": [
            "parse_task(): read YAML frontmatter from .md files",
            "scan_pending(): return sorted list of tasks in pending/",
        ],
        "K8s management (~40 lines)": [
            "create_job(): generate and apply a K8s Job manifest",
            "watch_jobs(): poll job statuses (Complete/Failed conditions)",
            "move_task(): rename file between pending/in-progress/completed/failed",
        ],
        "Main loop (~30 lines)": [
            "1. git pull",
            "2. scan pending/ → create K8s jobs → move to in-progress/ → commit",
            "3. watch running jobs → on completion, move to completed/ → commit",
            "4. sleep 30s → repeat",
        ],
    }

    print("\n  The essential claude-os controller\n")
    print(f"  Total: ~{sum(1 for l in open(__file__) if l.strip())} non-blank lines\n")
    for section, items in sections.items():
        print(f"  {section}")
        for item in items:
            print(f"    · {item}")
        print()

    print("  What's NOT here vs. the real controller:")
    missing = [
        "Redis (queue decoupling — useful for scale, not essential)",
        "Governance (cost/token limits — important, not essential)",
        "Workshop scheduler (free time logic — valuable, not essential)",
        "Goroutines (parallel git-sync + dispatch + watch — performance)",
        "HTTP health endpoints (for K8s readiness probes)",
        "Graceful shutdown (SIGTERM handling)",
        "Structured logging (slog)",
        "Config file loading (hardcoded here for clarity)",
        "~286 lines of tests",
        "~700 lines of Go boilerplate (type definitions, error wrapping)",
    ]
    for item in missing:
        print(f"    ✗ {item}")
    print()
    print("  Insight: the 1,843-line Go controller has ~140 lines of essential logic.")
    print("  The rest is production hardening, performance, and Go's verbosity.\n")


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Minimal claude-os controller sketch")
    ap.add_argument("--describe", action="store_true", help="Describe what each part does")
    ap.add_argument("--dry-run", action="store_true", help="Show tasks without dispatching")
    ap.add_argument("--plain", action="store_true", help="No ANSI colors (unused here)")
    args = ap.parse_args()

    if args.describe:
        describe()
    elif args.dry_run:
        ensure_repo()
        pull()
        tasks = scan_pending()
        if tasks:
            print(f"\n  Found {len(tasks)} pending task(s):\n")
            for t in tasks:
                print(f"  [{t.get('priority', 'normal'):8s}] {t['id']}")
                print(f"             {t.get('title', '(no title)')}")
                print(f"             profile={t.get('profile', 'small')}")
                print()
        else:
            print("\n  No pending tasks.\n")
    else:
        run()


if __name__ == "__main__":
    main()
