---
profile: small
priority: creative
status: failed
---

# Workshop: cloud-burst-pool-matching

## Results

## Outcome

- Outcome: success | failure | partial
- Agent: codex
- Model: string

## Summary

string

## Usage

- Tokens in: 0
- Tokens out: 0
- Duration (s): 0

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "cloud-burst-pool-matching",
  "agent": "codex",
  "model": "string",
  "outcome": "success | failure | partial",
  "summary": "string",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 0
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: cloud-burst-pool-matching
Profile: medium
Agent: codex
Mode: execution
Started: 2026-06-13T10:59:16Z
Context: /workspace/task-context.json
Auth: Codex OAuth (ChatGPT subscription)
Cloning context repo: https://github.com/dacort/cloud-burst-controller.git -> /workspace/cloud-burst-controller
Cloning into '/workspace/cloud-burst-controller'...
Running task via codex...
---
Reading additional input from stdin...
OpenAI Codex v0.120.0 (research preview)
--------
workdir: /workspace/cloud-burst-controller
model: gpt-5.3-codex
provider: openai
approval: never
sandbox: danger-full-access
reasoning effort: none
reasoning summaries: none
session id: 019ec0a2-d748-7331-bc3b-3a9fe7c1606f
--------
user
You are Codex running inside Claude OS.
Use the existing repository checkout and follow the task contract exactly.

Mode: execution
Task ID: cloud-burst-pool-matching
Title: Fix burst pool matching: specific pools are shadowed by general-burst

Description:
Found while trying to run the M9g benchmark (claude-os issue #9, talos-homelab
PR #4). Two bugs prevent any pod from ever reaching the m9g-burst pool:
### Bug 1 (this repo): catch-all pool shadows specific pools
`MatchPodToPool` in `internal/controller/matching.go` sorts pools
alphabetically and returns the FIRST match. `general-burst` sorts before
`m9g-burst` and its only matchRule is the `burst.homelab.dev/cloud`
toleration — which every burst pod has. So general-burst captures everything
and specific pools are unreachable.
Fix: prefer the most specific match instead of alphabetical order. Suggested:
score each matching pool (e.g. +1 per matched NodeAffinityLabel, +1 per
matched Resource rule; tolerations alone score 0) and pick the highest score;
tie-break alphabetically for determinism. A pod with
`burst.homelab.dev/instance-class: m9g` affinity then routes to m9g-burst
while plain burst pods still land on general-burst. Update
`internal/controller/matching_test.go` (see
`TestMatchPodToPool_MultiplePoolsFirstAlphabeticalWins` — its behavior will
change; replace it with specificity tests covering both routing cases).
### Bug 2 (talos-homelab): benchmark Job uses the wrong affinity key
`benchmarks/benchmark-m9g.yaml` requires
`burst.homelab.dev/pool: m9g-burst`, but the m9g pool's matchRules look for
`burst.homelab.dev/instance-class: m9g` (the README documents the right
key). Open a separate PR against dacort/talos-homelab changing the
benchmark's nodeAffinity to
`burst.homelab.dev/instance-class In [m9g]`. Keep it out of infra/ paths.
### Context / already handled — do NOT redo these
- The missing `general-burst-talos-config` secret has been created on the
cluster (copied from `talos-worker-config`). No action needed.
- You have NO cluster access from worker pods — do not attempt kubectl.
CI is your verification gate: `go test ./...` must pass.
- After your PRs merge, dacort's brain session will re-run the benchmark and
post results to claude-os issue #9. Mention that handoff in your PR
description and reference talos-homelab issue #5.

Repository:
- URL: https://github.com/dacort/cloud-burst-controller.git
- Ref: main
- Workdir: /workspace/cloud-burst-controller

Autonomy:
- can_merge: true
- can_create_issues: true
- can_create_tasks: false
- can_push: true
- ci_is_approval_gate: true

Constraints:
- This repo is PUBLIC — never commit secrets
- If tests fail, fix them before merging
- Before finishing, re-read the task and verify every instruction was addressed — do not drop trailing items from multi-part requests

Execution requirements:
- Do the work directly in the checked-out repository.
- Keep the adapter contract thin: do not invent extra policy beyond the task contract.
- If you cannot determine token counts, set usage.tokens_in and usage.tokens_out to 0.
- If founder mode applies, leave the thread in an explicit next state.

Before exiting, emit exactly one structured result block to stdout with no code fences and these exact delimiters:
===RESULT_START===
{"version":"1","task_id":"cloud-burst-pool-matching","agent":"codex","model":"string","outcome":"success | failure | partial","summary":"string","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":0},"failure":null,"next_action":null}
===RESULT_END===

Rules for the result block:
- artifacts is required; use [] when there are none.
- outcome must be one of success, failure, or partial.
- decision is an artifact type, not an outcome.
- failure.reason, when present, must be one of: tests_failed, timeout, rate_limited, git_push_failed, context_error, agent_error.
- next_action is optional, but founder mode should usually set it.
ERROR: {"type":"error","status":400,"error":{"type":"invalid_request_error","message":"The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account."}}
ERROR: {"type":"error","status":400,"error":{"type":"invalid_request_error","message":"The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account."}}
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 1
Push exit: 0
Finished: 2026-06-13T10:59:19Z

=== CLAUDE_OS_USAGE ===
{"task_id":"cloud-burst-pool-matching","agent":"codex","profile":"medium","duration_seconds":3,"exit_code":1,"finished_at":"2026-06-13T10:59:19Z"}
=== END_CLAUDE_OS_USAGE ===

