---
profile: medium
priority: high
status: pending
target_repo: dacort/cloud-burst-controller
agent: claude
agent_required: claude
created: "2026-06-12T22:40:37Z"
---

# Fix burst pool matching: specific pools are shadowed by general-burst

## Description

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
- Duration (s): 546

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "cloud-burst-pool-matching-v2",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 546
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: cloud-burst-pool-matching-v2
Profile: medium
Agent: claude
Mode: execution
Started: 2026-06-12T22:41:23Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/cloud-burst-controller.git -> /workspace/cloud-burst-controller
Cloning into '/workspace/cloud-burst-controller'...
Running task via claude...
---
Here's a summary of what was accomplished:

---

## Summary

### Bug 1 — `cloud-burst-controller`: Specificity-based pool matching ✅

**File changed:** `internal/controller/matching.go`

Replaced the alphabetical-first-match logic in `MatchPodToPool` with a **specificity scoring** system:
- Each pool is scored: **+1 per `NodeAffinityLabel` entry** + **+1 per `Resource` rule**; toleration-only pools score 0
- The highest-scoring matching pool wins; equal scores still tie-break alphabetically for determinism
- Added `poolSpecificityScore()` helper

Result: a pod with `burst.homelab.dev/instance-class: m9g` affinity now routes to `m9g-burst` (score 1) instead of `general-burst` (score 0).

**Tests updated** (`matching_test.go`):
- Removed `TestMatchPodToPool_MultiplePoolsFirstAlphabeticalWins` (behaviour has intentionally changed)
- Added `TestMatchPodToPool_SpecificPoolWinsOverGeneral` — m9g pod → m9g-burst pool
- Added `TestMatchPodToPool_PlainBurstPodRoutesToGeneralPool` — plain burst pod → general-burst
- Added `TestMatchPodToPool_EqualScoreTieBreaksAlphabetically` — alphabetical tie-break still works

All 8 matching tests + full `go test ./...` suite pass. Committed as `06aa9ef`. **Note: push to remote is blocked** — the worker's PAT is read-only for `cloud-burst-controller`. The commit is ready in the local workspace for the harness to sync.

---

### Bug 2 — `talos-homelab`: Correct affinity key in benchmark ✅

**PR opened:** https://github.com/dacort/talos-homelab/pull/6

Changed `benchmarks/benchmark-m9g.yaml` node affinity from:
```yaml
key: burst.homelab.dev/pool
values: ["m9g-burst"]
```
to:
```yaml
key: burst.homelab.dev/instance-class  
values: ["m9g"]
```

The PR description references talos-homelab issue #5 and notes that after both PRs merge, dacort's brain session should re-run the benchmark and post results to claude-os issue #9.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-06-12T22:50:29Z
===RESULT_START===
{"version":"1","task_id":"cloud-burst-pool-matching-v2","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":546},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"cloud-burst-pool-matching-v2","agent":"claude","profile":"medium","duration_seconds":546,"exit_code":0,"finished_at":"2026-06-12T22:50:29Z"}
=== END_CLAUDE_OS_USAGE ===

