#!/usr/bin/env python3
"""Build the Codex instruction block from the claude-os context contract.

Usage: codex-prompt.py <context_file> <task_title> <task_description> <workdir>

Reads a task-context.json envelope and prints a structured instruction block
that Codex can follow. Called by entrypoint.sh's codex adapter path.

Previously this was a Python heredoc embedded in build_codex_instruction_block()
inside entrypoint.sh. Extracted in session 45 to make it unit-testable and to
remove the 130-line embedded script from the bash entry point.
"""

import json
import pathlib
import sys

context_path = pathlib.Path(sys.argv[1])
fallback_title = sys.argv[2]
fallback_description = sys.argv[3]
fallback_workdir = sys.argv[4]

if context_path.exists():
    envelope = json.loads(context_path.read_text())
else:
    envelope = {
        "version": "0",
        "mode": "execution",
        "task": {
            "id": "",
            "title": fallback_title,
            "description": fallback_description,
            "profile": "",
            "priority": "",
            "agent": "codex",
            "created": ""
        },
        "repo": {
            "url": "",
            "ref": "",
            "workdir": fallback_workdir
        },
        "autonomy": {
            "can_merge": False,
            "can_create_issues": False,
            "can_create_tasks": False,
            "can_push": False,
            "ci_is_approval_gate": True
        },
        "context_refs": [],
        "constraints": [],
        "founder": None
    }

task = envelope.get("task", {})
repo = envelope.get("repo", {})
autonomy = envelope.get("autonomy", {})
founder = envelope.get("founder")
mode = envelope.get("mode", "execution")
workdir = repo.get("workdir") or fallback_workdir
base_dir = pathlib.Path(workdir)

parts = [
    "You are Codex running inside Claude OS.",
    "Use the existing repository checkout and follow the task contract exactly.",
    "",
    f"Mode: {mode}",
    f"Task ID: {task.get('id', '') or 'unknown'}",
    f"Title: {task.get('title', '') or fallback_title}",
    "",
    "Description:",
    task.get("description", "") or fallback_description or "(no description provided)",
    "",
    "Repository:",
    f"- URL: {repo.get('url', '') or '(not provided)'}",
    f"- Ref: {repo.get('ref', '') or '(not provided)'}",
    f"- Workdir: {workdir}",
    "",
    "Autonomy:"
]

for key in ("can_merge", "can_create_issues", "can_create_tasks", "can_push", "ci_is_approval_gate"):
    if key in autonomy:
        parts.append(f"- {key}: {str(bool(autonomy.get(key))).lower()}")

constraints = envelope.get("constraints") or []
if constraints:
    parts.extend(["", "Constraints:"])
    for item in constraints:
        parts.append(f"- {item}")

if founder:
    parts.extend(["", "Founder context:"])
    for key in ("thread_id", "thread_path", "respond_in_thread", "extract_decision_if_reached", "spawn_execution_tasks_if_needed"):
        if key in founder:
            value = founder.get(key)
            if isinstance(value, bool):
                value = str(value).lower()
            parts.append(f"- {key}: {value}")

context_refs = envelope.get("context_refs") or []
if context_refs:
    parts.extend(["", "Referenced context files:"])
    for ref in context_refs:
        parts.append(f"- {ref}")

    for ref in context_refs:
        ref_path = base_dir / ref
        parts.extend(["", f"### Context File: {ref}"])
        if ref_path.is_file():
            try:
                parts.append(ref_path.read_text())
            except Exception as exc:
                parts.append(f"(failed to read {ref}: {exc})")
        else:
            parts.append(f"(missing file at {ref_path})")

parts.extend([
    "",
    "Execution requirements:",
    "- Do the work directly in the checked-out repository.",
    "- Keep the adapter contract thin: do not invent extra policy beyond the task contract.",
    "- If you cannot determine token counts, set usage.tokens_in and usage.tokens_out to 0.",
    "- If founder mode applies, leave the thread in an explicit next state.",
    "",
    "Before exiting, emit exactly one structured result block to stdout with no code fences and these exact delimiters:",
    "===RESULT_START===",
    '{"version":"1","task_id":"%s","agent":"codex","model":"string","outcome":"success | failure | partial","summary":"string","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":0},"failure":null,"next_action":null}' % (task.get("id", "") or "unknown"),
    "===RESULT_END===",
    "",
    "Rules for the result block:",
    "- artifacts is required; use [] when there are none.",
    "- outcome must be one of success, failure, or partial.",
    "- decision is an artifact type, not an outcome.",
    "- failure.reason, when present, must be one of: tests_failed, timeout, rate_limited, git_push_failed, context_error, agent_error.",
    "- next_action is optional, but founder mode should usually set it."
])

print("\n".join(parts))
