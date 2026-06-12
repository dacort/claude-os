---
profile: medium
priority: high
status: pending
target_repo: dacort/cloud-burst-controller
created: "2026-06-12T20:06:57Z"
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
