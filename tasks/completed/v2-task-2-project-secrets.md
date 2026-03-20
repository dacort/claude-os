---
profile: small
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
created: "2026-03-20T17:22:00Z"
---

# v2 Task 2: Per-project secret mounting in dispatcher

## Description

Add per-project K8s Secret mounting to the dispatcher so worker pods only see credentials for their project.

### Changes

1. **`controller/dispatcher/dispatcher.go`** — Add a new function after `agentSecrets()`:
   ```go
   func projectSecrets(projectName string) []corev1.EnvFromSource {
       if projectName == "" {
           return nil
       }
       optional := true
       return []corev1.EnvFromSource{{
           SecretRef: &corev1.SecretEnvSource{
               LocalObjectReference: corev1.LocalObjectReference{
                   Name: "claude-os-project-" + projectName,
               },
               Optional: &optional,
           },
           Prefix: "PROJECT_",
       }}
   }
   ```

2. In `CreateJob()`, after appending agent secrets to the container's `EnvFrom`, add:
   ```go
   if task.Project != "" {
       container.EnvFrom = append(container.EnvFrom, projectSecrets(task.Project)...)
   }
   ```

3. **Tests** in `controller/dispatcher/dispatcher_test.go`:
   - `TestProjectSecrets_WithProject` — assert returns 1 EnvFromSource with correct name, prefix, and optional=true
   - `TestProjectSecrets_WithoutProject` — assert returns nil for empty string

### TDD Flow
- Write failing tests first, run, implement, run, commit, push
- Commit message: `feat: mount per-project K8s secrets in worker pods`

## Results

## Outcome

- Outcome: success
- Agent: claude
- Model: claude-sonnet-4-6

## Summary

Task completed without an explicit structured result block.

## Usage

- Tokens in: 0
- Tokens out: 0
- Duration (s): 283

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "v2-task-2-project-secrets",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 283
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: v2-task-2-project-secrets
Profile: small
Agent: claude
Mode: execution
Started: 2026-03-20T17:25:03Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
That task notification is stale — it's from the initial failing test run (before the implementation), which was the expected TDD "red" phase. The tests have since passed and the code is already pushed to main. Nothing to act on here.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-20T17:29:45Z
===RESULT_START===
{"version":"1","task_id":"v2-task-2-project-secrets","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":283},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"v2-task-2-project-secrets","agent":"claude","profile":"small","duration_seconds":283,"exit_code":0,"finished_at":"2026-03-20T17:29:45Z"}
=== END_CLAUDE_OS_USAGE ===

