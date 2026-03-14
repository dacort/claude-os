#!/usr/bin/env python3
"""
multiagent.py — Multi-agent coordination proof-of-concept

Demonstrates the Bus/Coordinator/Worker architecture from knowledge/orchestration-design.md.
This is a STANDALONE SIMULATION — no K8s, no Claude API, no Redis.
Workers run as real Python threads with a shared message bus.

The demo task: "Audit the claude-os system"
Coordinator decomposes this into 5 parallel subtasks, workers run them simultaneously,
results are aggregated into a unified report.

Markers like [LLM CALL] show where real Claude API calls would replace rule-based logic
in a production implementation.

Usage:
    python3 projects/multiagent.py
    python3 projects/multiagent.py --serial     # Compare: run same tasks serially
    python3 projects/multiagent.py --plain      # No ANSI colors
    python3 projects/multiagent.py --verbose    # Show message bus traffic

Architecture demonstrated:
    Coordinator → decomposes task → Bus → Workers (parallel) → Bus → Coordinator → Report

From knowledge/orchestration-design.md, Session 7, updated Session 14.
This POC exists to prove the design before building it in the Go controller.
"""

import threading
import queue as qmod
import time
import sys
import os
import glob
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ──────────────────────────────────────────────────────────────────────────────
# Color helpers
# ──────────────────────────────────────────────────────────────────────────────

PLAIN = "--plain" in sys.argv


def c(code: str, text: str) -> str:
    if PLAIN:
        return text
    return f"\033[{code}m{text}\033[0m"


def cyan(t):     return c("36", t)
def green(t):    return c("32", t)
def yellow(t):   return c("33", t)
def dim(t):      return c("2", t)
def bold(t):     return c("1", t)
def magenta(t):  return c("35", t)
def red(t):      return c("31", t)
def blue(t):     return c("34", t)


# ──────────────────────────────────────────────────────────────────────────────
# Message Bus
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Message:
    """A unit of work or response on the Bus."""
    task_id: str           # unique ID for this subtask
    sender: str            # who sent it
    recipient: str         # who should receive it
    content: str           # human-readable description of the work
    payload: dict = field(default_factory=dict)   # structured params
    result: Any = None     # filled in by worker
    error: Optional[str] = None
    sent_at: float = field(default_factory=time.time)
    done_at: Optional[float] = None


class Bus:
    """
    Thread-safe message bus. Workers register by name and get a private inbox.

    In production: this maps to Redis sorted-set queue + Pub/Sub for notifications.
    Here: Python queues, one per named recipient.
    """
    def __init__(self, verbose: bool = False):
        self._inboxes: dict[str, qmod.Queue] = {}
        self._lock = threading.Lock()
        self._verbose = verbose
        self._log: list[str] = []

    def register(self, name: str) -> qmod.Queue:
        with self._lock:
            inbox = qmod.Queue()
            self._inboxes[name] = inbox
            return inbox

    def send(self, msg: Message) -> None:
        with self._lock:
            if msg.recipient not in self._inboxes:
                raise KeyError(f"No worker registered as '{msg.recipient}'")
            self._inboxes[msg.recipient].put(msg)
        if self._verbose:
            entry = dim(f"  bus  {msg.sender} → {msg.recipient}  [{msg.task_id}]")
            print(entry)
            self._log.append(entry)

    def get_log(self) -> list[str]:
        return self._log


# ──────────────────────────────────────────────────────────────────────────────
# Worker
# ──────────────────────────────────────────────────────────────────────────────

class Worker(threading.Thread):
    """
    A single-purpose agent. Receives tasks from the Bus, runs its handler,
    posts results back to the coordinator.

    In production: this is a K8s Job. One pod per task.
    Here: a Python thread.
    """
    def __init__(self, name: str, bus: Bus, handler: Callable[[Message], Any]):
        super().__init__(name=name, daemon=True)
        self.name_str = name
        self.bus = bus
        self.handler = handler
        self._inbox = bus.register(name)
        self.tasks_done = 0
        self.started_at: Optional[float] = None

    def run(self) -> None:
        self.started_at = time.time()
        while True:
            try:
                msg: Message = self._inbox.get(timeout=5.0)
                if msg.task_id == "__shutdown__":
                    break
                try:
                    result = self.handler(msg)
                    msg.result = result
                    msg.done_at = time.time()
                    msg.error = None
                except Exception as exc:
                    msg.error = str(exc)
                    msg.done_at = time.time()
                self.tasks_done += 1
                self.bus.send(Message(
                    task_id=msg.task_id,
                    sender=self.name_str,
                    recipient="coordinator",
                    content=f"result for {msg.task_id}",
                    result=msg.result,
                    error=msg.error,
                    done_at=msg.done_at,
                ))
            except qmod.Empty:
                break

    def shutdown(self) -> None:
        self._inbox.put(Message(
            task_id="__shutdown__",
            sender="coordinator",
            recipient=self.name_str,
            content="shutdown",
        ))


# ──────────────────────────────────────────────────────────────────────────────
# Coordinator
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SubTask:
    task_id: str
    worker: str
    description: str
    payload: dict = field(default_factory=dict)


class Coordinator:
    """
    Receives a high-level task, decomposes it, fans out to workers, collects results.

    [LLM CALL] In production, decompose() is a Claude Opus API call that returns
    a list of subtasks with assigned agents. Here: rule-based decomposition.
    """
    def __init__(self, bus: Bus, workers: list[str]):
        self.bus = bus
        self.workers = workers
        self._inbox = bus.register("coordinator")

    def decompose(self, task: str, repo_root: str) -> list[SubTask]:
        """
        [LLM CALL] This is where Opus would run.

        Real prompt would be:
            "Break '{task}' into subtasks, assign each to the best worker,
             return structured JSON with task_id, worker, description, payload."

        For this POC: hardcoded decomposition for 'audit claude-os'.
        """
        return [
            SubTask(
                task_id="audit-tasks",
                worker="scanner",
                description="Count task files by status",
                payload={"type": "tasks", "root": repo_root},
            ),
            SubTask(
                task_id="audit-tools",
                worker="scanner",  # same worker type, different task
                description="Inventory projects/ Python tools",
                payload={"type": "tools", "root": repo_root},
            ),
            SubTask(
                task_id="audit-sessions",
                worker="historian",
                description="Count workshop sessions and compute cadence",
                payload={"type": "sessions", "root": repo_root},
            ),
            SubTask(
                task_id="audit-controller",
                worker="analyst",
                description="Measure controller Go codebase size",
                payload={"type": "controller", "root": repo_root},
            ),
            SubTask(
                task_id="audit-knowledge",
                worker="analyst",
                description="Inventory knowledge/ documents",
                payload={"type": "knowledge", "root": repo_root},
            ),
        ]

    def run(self, task: str, repo_root: str, parallel: bool = True) -> dict:
        """
        Fan out subtasks to workers, collect results.
        Returns aggregated report dict.
        """
        subtasks = self.decompose(task, repo_root)
        start = time.time()

        if parallel:
            # Fan out: send all subtasks simultaneously
            for st in subtasks:
                self.bus.send(Message(
                    task_id=st.task_id,
                    sender="coordinator",
                    recipient=st.worker,
                    content=st.description,
                    payload=st.payload,
                ))

            # Fan in: collect results
            results = {}
            received = 0
            deadline = start + 30.0  # 30 second timeout
            while received < len(subtasks):
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                try:
                    msg: Message = self._inbox.get(timeout=remaining)
                    results[msg.task_id] = msg
                    received += 1
                except qmod.Empty:
                    break
        else:
            # Serial mode: send one, wait for result, then next
            results = {}
            for st in subtasks:
                self.bus.send(Message(
                    task_id=st.task_id,
                    sender="coordinator",
                    recipient=st.worker,
                    content=st.description,
                    payload=st.payload,
                ))
                # Wait for this specific result
                deadline = time.time() + 10.0
                while True:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        break
                    try:
                        msg: Message = self._inbox.get(timeout=remaining)
                        results[msg.task_id] = msg
                        break
                    except qmod.Empty:
                        break

        elapsed = time.time() - start
        return {"results": results, "elapsed": elapsed, "task_count": len(subtasks)}


# ──────────────────────────────────────────────────────────────────────────────
# Worker Handlers — actual work done on the claude-os repo
# ──────────────────────────────────────────────────────────────────────────────

def scanner_handler(msg: Message) -> dict:
    """Scanner worker: counts files in known directories."""
    root = msg.payload.get("root", ".")
    task_type = msg.payload.get("type")

    if task_type == "tasks":
        counts = {}
        for status in ("pending", "in-progress", "completed", "failed"):
            folder = os.path.join(root, "tasks", status)
            if os.path.isdir(folder):
                files = [f for f in os.listdir(folder) if f.endswith(".md")]
                counts[status] = len(files)
        total = sum(counts.values())
        return {
            "counts": counts,
            "total": total,
            "completion_rate": round(counts.get("completed", 0) / total * 100) if total else 0,
        }

    elif task_type == "tools":
        py_files = glob.glob(os.path.join(root, "projects", "*.py"))
        tools = []
        for path in sorted(py_files):
            name = os.path.basename(path)
            size = os.path.getsize(path)
            # Extract first docstring line for description
            try:
                with open(path) as f:
                    content = f.read(500)
                lines = content.strip().split("\n")
                desc = ""
                in_docstring = False
                for ln in lines[1:]:  # skip shebang
                    stripped = ln.strip()
                    if stripped.startswith('"""') and not in_docstring:
                        in_docstring = True
                        rest = stripped[3:].strip()
                        if rest and not rest.startswith('"""'):
                            desc = rest
                            break
                    elif in_docstring:
                        if stripped:
                            desc = stripped.rstrip(".")
                        break
            except Exception:
                desc = ""
            tools.append({"name": name, "size": size, "desc": desc[:60]})
        return {"tools": tools, "count": len(tools)}

    return {"error": f"unknown type: {task_type}"}


def historian_handler(msg: Message) -> dict:
    """Historian worker: analyzes session history and temporal patterns."""
    root = msg.payload.get("root", ".")
    task_type = msg.payload.get("type")

    if task_type == "sessions":
        completed = os.path.join(root, "tasks", "completed")
        sessions = []
        if os.path.isdir(completed):
            for fname in sorted(os.listdir(completed)):
                if fname.startswith("workshop-") and fname.endswith(".md"):
                    # Extract date from filename: workshop-YYYYMMDD-HHMMSS.md
                    m = re.search(r"workshop-(\d{8})-(\d{6})", fname)
                    if m:
                        sessions.append({
                            "id": fname[:-3],
                            "date": m.group(1),
                        })

        # Also look for field notes
        field_notes = glob.glob(os.path.join(root, "projects", "field-notes-session-*.md"))
        note_count = len(field_notes)

        # Session cadence: unique dates
        dates = sorted(set(s["date"] for s in sessions))
        cadence = {}
        for d in dates:
            count = sum(1 for s in sessions if s["date"] == d)
            cadence[d] = count

        return {
            "session_count": len(sessions),
            "field_note_count": note_count,
            "unique_dates": len(dates),
            "cadence": cadence,
            "first": sessions[0]["id"] if sessions else None,
            "latest": sessions[-1]["id"] if sessions else None,
        }

    return {"error": f"unknown type: {task_type}"}


def analyst_handler(msg: Message) -> dict:
    """Analyst worker: deeper structural analysis."""
    root = msg.payload.get("root", ".")
    task_type = msg.payload.get("type")

    if task_type == "controller":
        go_files = glob.glob(os.path.join(root, "controller", "**", "*.go"), recursive=True)
        total_lines = 0
        file_breakdown = []
        for path in sorted(go_files):
            try:
                with open(path) as f:
                    lines = f.readlines()
                line_count = len(lines)
                total_lines += line_count
                rel = os.path.relpath(path, os.path.join(root, "controller"))
                file_breakdown.append({"file": rel, "lines": line_count})
            except Exception:
                pass
        return {
            "total_lines": total_lines,
            "file_count": len(go_files),
            "files": sorted(file_breakdown, key=lambda x: x["lines"], reverse=True),
        }

    elif task_type == "knowledge":
        docs = []
        knowledge_root = os.path.join(root, "knowledge")
        if os.path.isdir(knowledge_root):
            for dirpath, dirnames, filenames in os.walk(knowledge_root):
                # Skip hidden dirs
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for fname in filenames:
                    if fname.endswith(".md") or fname.endswith(".yaml"):
                        full_path = os.path.join(dirpath, fname)
                        rel = os.path.relpath(full_path, knowledge_root)
                        size = os.path.getsize(full_path)
                        try:
                            with open(full_path) as f:
                                lines = len(f.readlines())
                        except Exception:
                            lines = 0
                        docs.append({"path": rel, "lines": lines, "size": size})
        return {
            "doc_count": len(docs),
            "docs": sorted(docs, key=lambda x: x["lines"], reverse=True),
            "total_lines": sum(d["lines"] for d in docs),
        }

    return {"error": f"unknown type: {task_type}"}


# ──────────────────────────────────────────────────────────────────────────────
# Report renderer
# ──────────────────────────────────────────────────────────────────────────────

def render_report(coord_output: dict, mode: str) -> None:
    results = coord_output["results"]
    elapsed = coord_output["elapsed"]
    task_count = coord_output["task_count"]

    W = 64
    bar = "─" * W

    def header(title: str) -> None:
        print(f"╭{bar}╮")
        pad = W - len(title) - 2
        print(f"│  {bold(title)}{' ' * pad}│")
        print(f"│{' ' * W}│")

    def section(title: str) -> None:
        print(f"├{bar}┤")
        pad = W - len(title) - 2
        print(f"│  {bold(title)}{' ' * pad}│")
        print(f"│{' ' * W}│")

    def row(label: str, value: str, indent: int = 2) -> None:
        prefix = " " * indent
        label_styled = cyan(label)
        # Compute visual length without ANSI
        label_len = len(label)
        value_len = len(value)
        pad = W - indent - label_len - value_len - 2
        if pad < 1:
            pad = 1
        print(f"│{prefix}{label_styled}{' ' * pad}{dim(value)}│")

    def blank() -> None:
        print(f"│{' ' * W}│")

    def footer() -> None:
        print(f"╰{bar}╯")

    # ── Header ──
    mode_label = "parallel" if mode == "parallel" else "serial"
    header(f"claude-os audit  [{mode_label} · {elapsed:.2f}s · {task_count} workers]")

    # ── Tasks ──
    section("TASK FILES")
    tasks_msg = results.get("audit-tasks")
    if tasks_msg and tasks_msg.result:
        r = tasks_msg.result
        counts = r.get("counts", {})
        for status in ("pending", "in-progress", "completed", "failed"):
            n = counts.get(status, 0)
            row(f"  {status}", str(n))
        blank()
        row("  total", str(r.get("total", 0)))
        row("  completion rate", f"{r.get('completion_rate', 0)}%")
    blank()

    # ── Tools ──
    section("PROJECTS/ TOOLS")
    tools_msg = results.get("audit-tools")
    if tools_msg and tools_msg.result:
        r = tools_msg.result
        row("  count", str(r.get("count", 0)))
        blank()
        tools = r.get("tools", [])
        for t in tools[:12]:  # show top 12 by name
            name = t["name"].replace(".py", "")
            desc = t["desc"]
            if desc:
                label = f"  {name}"
                label_len = len(label)
                desc_len = len(desc)
                pad = W - label_len - desc_len - 2
                if pad < 1:
                    pad = 1
                print(f"│{cyan(label)}{' ' * pad}{dim(desc)}│")
            else:
                print(f"│  {cyan(name)}{' ' * (W - len(name) - 4)}│")
        if len(tools) > 12:
            more = f"  ... and {len(tools) - 12} more"
            print(f"│{dim(more)}{' ' * (W - len(more))}│")
    blank()

    # ── Sessions ──
    section("WORKSHOP SESSIONS")
    sessions_msg = results.get("audit-sessions")
    if sessions_msg and sessions_msg.result:
        r = sessions_msg.result
        row("  sessions", str(r.get("session_count", 0)))
        row("  field notes", str(r.get("field_note_count", 0)))
        row("  active days", str(r.get("unique_dates", 0)))
        blank()
        cadence = r.get("cadence", {})
        for date, count in sorted(cadence.items()):
            bar_str = "█" * count
            row(f"  {date}", f"{bar_str}  {count}")
    blank()

    # ── Controller ──
    section("CONTROLLER (Go)")
    ctrl_msg = results.get("audit-controller")
    if ctrl_msg and ctrl_msg.result:
        r = ctrl_msg.result
        row("  total lines", str(r.get("total_lines", 0)))
        row("  files", str(r.get("file_count", 0)))
        blank()
        for f in r.get("files", [])[:6]:
            row(f"  {f['file']}", f"{f['lines']} lines")
    blank()

    # ── Knowledge ──
    section("KNOWLEDGE BASE")
    know_msg = results.get("audit-knowledge")
    if know_msg and know_msg.result:
        r = know_msg.result
        row("  documents", str(r.get("doc_count", 0)))
        row("  total lines", str(r.get("total_lines", 0)))
        blank()
        for doc in r.get("docs", [])[:6]:
            row(f"  {doc['path']}", f"{doc['lines']} lines")
    blank()

    # ── Timing ──
    section(f"TIMING  [{mode_label}]")
    row("  wall time", f"{elapsed:.3f}s")
    row("  tasks dispatched", str(task_count))
    if mode == "parallel":
        row("  concurrency", f"{task_count} workers · {task_count} threads")
        blank()
        note = "  Compare with --serial to see speedup"
        print(f"│{dim(note)}{' ' * (W - len(note))}│")
    else:
        row("  mode", "sequential — one task at a time")
        blank()
        note = "  Run without --serial to see parallel speedup"
        print(f"│{dim(note)}{' ' * (W - len(note))}│")
    blank()

    footer()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    serial_mode = "--serial" in sys.argv
    verbose = "--verbose" in sys.argv

    # Locate repo root (works whether run from repo root or projects/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir) if os.path.basename(script_dir) == "projects" else script_dir

    if verbose:
        print(dim(f"\n  repo root: {repo_root}\n"))

    # ── Build the Bus ──
    bus = Bus(verbose=verbose)

    # ── Spawn workers ──
    # Three worker types: scanner, historian, analyst
    # In production: these would be K8s Jobs, one per task, different images
    # Here: threads, one per role, handling tasks sequentially per role
    workers_map = {
        "scanner":   Worker("scanner",   bus, scanner_handler),
        "historian": Worker("historian", bus, historian_handler),
        "analyst":   Worker("analyst",   bus, analyst_handler),
    }

    for w in workers_map.values():
        w.start()

    # ── Coordinator ──
    coord = Coordinator(bus, list(workers_map.keys()))

    if verbose:
        print(dim("  coordinator: decomposing task..."))
        print()

    # [LLM CALL] In production: Opus decomposes this into subtasks dynamically
    task = "Audit the claude-os system"

    mode = "serial" if serial_mode else "parallel"
    output = coord.run(task, repo_root, parallel=not serial_mode)

    # ── Shutdown workers ──
    for w in workers_map.values():
        w.shutdown()
    for w in workers_map.values():
        w.join(timeout=2.0)

    # ── Render ──
    if verbose and bus.get_log():
        print()
        print(dim("  Bus message log:"))
        for entry in bus.get_log():
            print(entry)
        print()

    render_report(output, mode)


if __name__ == "__main__":
    main()
