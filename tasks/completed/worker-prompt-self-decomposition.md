---
profile: small
priority: creative
status: completed
---

# Workshop: worker-prompt-self-decomposition

## Results

## Outcome

- Outcome: success
- Agent: claude
- Model: claude-opus-4-6

## Summary

Task completed without an explicit structured result block.

## Usage

- Tokens in: 0
- Tokens out: 0
- Duration (s): 621

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "worker-prompt-self-decomposition",
  "agent": "claude",
  "model": "claude-opus-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 621
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: worker-prompt-self-decomposition
Profile: medium
Agent: claude
Mode: execution
Started: 2026-06-12T18:29:25Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
Here's a summary of what I accomplished:

---

## Summary

Three changes committed directly to main (non-breaking, all tests green):

### 1. Self-decomposition rule in worker prompt

**`worker/entrypoint.sh`** — Added a "Task Decomposition Across External Gates" section to the system prompt that every worker receives. It instructs workers to:
- Complete the current phase, then write a follow-up task file in `tasks/pending/` with `depends_on` frontmatter
- Never mark the overall request done when only phase one is delivered
- Re-read the original task before finishing to verify every instruction was addressed

**`controller/dispatcher/context.go`** — Added a backstop constraint to `constraintsForMode()`: *"Before finishing, re-read the task and verify every instruction was addressed — do not drop trailing items from multi-part requests"*

### 2. GitOps hygiene knowledge doc

**`knowledge/gitops-hygiene.md`** — Documents that `infra/` and `apps/` in talos-homelab are Fleet-watched and go live on merge. One-shot Jobs must never be committed there — run them via `kubectl apply` from a non-watched path.

**`knowledge/skills/homelab-kubernetes/`** — New skill that auto-injects this context (plus cluster access rules and the homelab PR workflow) when a task matches homelab/talos/burst/benchmark keywords.

### 3. Profile auto-sizing fix (the triage question)

**Why issue #9 got `profile: small`**: `gh-channel.py` hardcoded `DEFAULT_PROFILE = "small"` with no intelligence. The triage system (Haiku API / heuristic fallback) recommends models and agents but never overrides the profile field.

**Fix in `projects/gh-channel.py`**: Added `auto_size_profile()` with keyword heuristics. Issue #9's exact text now auto-sizes to `medium` (matches "benchmark", "talos-homelab", "open a PR"). Explicit `[small]`/`[medium]`/`[large]` tags in the `@claude-os` command still win.
No workspace changes to commit
--- Skill harvest check ---
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-06-12T18:39:46Z
===RESULT_START===
{"version":"1","task_id":"worker-prompt-self-decomposition","agent":"claude","model":"claude-opus-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":621},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"worker-prompt-self-decomposition","agent":"claude","profile":"medium","duration_seconds":621,"exit_code":0,"finished_at":"2026-06-12T18:39:46Z"}
=== END_CLAUDE_OS_USAGE ===

