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

task_id_value = task.get("id", "") or "unknown"
parts.extend([
    "",
    "Execution requirements:",
    "- Do the work directly in the checked-out repository.",
    "- Keep the adapter contract thin: do not invent extra policy beyond the task contract.",
    "- If you cannot determine token counts, set usage.tokens_in and usage.tokens_out to 0.",
    "- If founder mode applies, leave the thread in an explicit next state.",
    "",
    "REQUIRED: Before exiting, emit exactly one structured result block to stdout.",
    "Use these exact delimiters (no code fences, no extra text between them):",
    "  ===RESULT_START===",
    "  <single line of JSON with REAL values — see field guide below>",
    "  ===RESULT_END===",
    "",
    "Field guide — fill in REAL values, do NOT copy these descriptions:",
    '  version    → always the string "1"',
    '  task_id    → always "%s"' % task_id_value,
    '  agent      → always "codex"',
    "  model      → the model name you are actually running (e.g. \"gpt-4o\", \"gpt-4o-mini\")",
    '  outcome    → exactly one of: "success", "failure", or "partial"',
    "  summary    → 1-2 sentences describing what you actually did and the result",
    "  artifacts  → JSON array; each entry is {\"type\":\"commit\",\"ref\":\"<hash>\"} or {\"type\":\"pr\",\"url\":\"<url>\"}; use [] if none",
    "  usage      → {\"tokens_in\":<int>, \"tokens_out\":<int>, \"duration_seconds\":<int>}; use 0 if unknown",
    "  failure    → null on success; on failure: {\"reason\":\"<one of: tests_failed|timeout|rate_limited|git_push_failed|context_error|agent_error>\",\"detail\":\"<what went wrong>\",\"retryable\":<true|false>}",
    "  next_action → null unless in founder mode",
    "",
    "Example of a valid SUCCESS result (with a different task — do not copy values, write your own):",
    "===RESULT_START===",
    '{"version":"1","task_id":"example-task-xyz","agent":"codex","model":"gpt-4o","outcome":"success","summary":"Updated the Go controller timeout to 30s and added a retry loop. All tests pass.","artifacts":[{"type":"commit","ref":"a1b2c3d"}],"usage":{"tokens_in":2500,"tokens_out":450,"duration_seconds":62},"failure":null,"next_action":null}',
    "===RESULT_END===",
    "",
    "Example of a valid FAILURE result (do not copy — write your own based on what actually happened):",
    "===RESULT_START===",
    '{"version":"1","task_id":"example-task-xyz","agent":"codex","model":"gpt-4o","outcome":"failure","summary":"Could not complete the task: tests failed after applying the patch to main.go.","artifacts":[],"usage":{"tokens_in":1800,"tokens_out":200,"duration_seconds":30},"failure":{"reason":"tests_failed","detail":"go test ./... exited with code 2","retryable":true},"next_action":null}',
    "===RESULT_END===",
])

print("\n".join(parts))
