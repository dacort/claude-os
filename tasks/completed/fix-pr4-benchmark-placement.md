---
profile: medium
priority: high
status: pending
target_repo: dacort/talos-homelab
created: "2026-06-12T18:29:01Z"
---

# Address review feedback on talos-homelab PR #4 (M9g burst pool)

## Description

dacort left review feedback on your open PR:
https://github.com/dacort/talos-homelab/pull/4#issuecomment-4694119294

Summary of the problem: `infra/cloud-burst-controller/` is a Fleet bundle — the
sealab GitRepo (`clusters/sealab/gitrepo.yaml`) watches all of `infra/` and
`apps/`, so every manifest there is auto-applied on merge. Your
`benchmark-m9g.yaml` Job would run immediately on merge, and because it has
`ttlSecondsAfterFinished: 600`, every subsequent bundle re-sync would re-create
and re-run it, provisioning a new M9g burst node each time.

What to do on the existing PR branch (`claude-os/m9g-cloud-burst`):

1. Move `benchmark-m9g.yaml` to a new top-level `benchmarks/` directory
   (outside the Fleet-watched `infra`/`apps` paths).
2. Update the README usage instructions to apply it from the new path.
3. Leave `burstnodepool-m9g.yaml` where it is — declarative and idempotent,
   correct for the GitOps path.
4. Reply to dacort's comment on the PR confirming the change.

Do NOT merge the PR yourself — dacort will merge after reviewing the update.
After he merges, the benchmark still needs to be run; if you cannot run it in
this session, write a follow-up task file in dacort/claude-os
`tasks/pending/` to run the benchmark and post results to
https://github.com/dacort/claude-os/issues/9 once the pool is deployed.

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
- Duration (s): 188

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "fix-pr4-benchmark-placement",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 188
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: fix-pr4-benchmark-placement
Profile: medium
Agent: claude
Mode: execution
Started: 2026-06-12T18:29:15Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/talos-homelab.git -> /workspace/talos-homelab
Cloning into '/workspace/talos-homelab'...
Running task via claude...
---
All done. Here's a summary of everything accomplished:

---

## Summary

**Problem addressed:** `benchmark-m9g.yaml` was inside `infra/cloud-burst-controller/` — a Fleet-watched path. Fleet would have auto-applied the Job on merge, and after `ttlSecondsAfterFinished: 600` deleted it, every future bundle re-sync would re-create and re-run it, silently burning burst budget.

**Changes made on branch `claude-os/m9g-cloud-burst` (PR #4):**

1. **`benchmark-m9g.yaml` moved** from `infra/cloud-burst-controller/` → `benchmarks/` (new top-level directory, outside the `infra/` and `apps/` paths the sealab GitRepo watches). Added a header comment in the file explaining why it must stay outside Fleet-watched paths.

2. **README updated** — `infra/cloud-burst-controller/README.md` usage instructions now reference `benchmarks/benchmark-m9g.yaml`.

3. **`burstnodepool-m9g.yaml` left untouched** — declarative, idempotent, correct for GitOps.

4. **Replied to dacort's review comment** at [PR #4](https://github.com/dacort/talos-homelab/pull/4#issuecomment-4694144350) summarizing the fix.

5. **Follow-up benchmark task** created at `tasks/pending/run-m9g-benchmark.md` in dacort/claude-os with step-by-step instructions to run the benchmark after PR #4 merges and post results to dacort/talos-homelab#9.

**NOT merged** — waiting for dacort's review as requested.
No workspace changes to commit
--- Skill harvest check ---
[skill-harvest] New skill generated from task pattern: homelab-kubernetes
[skill-harvest] Matched 5 tasks → /workspace/claude-os/knowledge/skills/homelab-kubernetes
[skill-harvest] Future 'Homelab / Kubernetes' tasks will get contextual guidance.
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-06-12T18:32:23Z
===RESULT_START===
{"version":"1","task_id":"fix-pr4-benchmark-placement","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":188},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"fix-pr4-benchmark-placement","agent":"claude","profile":"medium","duration_seconds":188,"exit_code":0,"finished_at":"2026-06-12T18:32:23Z"}
=== END_CLAUDE_OS_USAGE ===

