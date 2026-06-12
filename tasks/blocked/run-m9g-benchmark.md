---
profile: medium
priority: normal
status: pending
target_repo: dacort/talos-homelab
created: "2026-06-12T18:40:00Z"
---

# Run M9g Burst Pool Benchmark & Post Results

> **PARKED — do not move to `tasks/pending/` until talos-homelab PR #4 is merged.**
> This task is gated on a human merge. The controller doesn't support external
> gate conditions yet (see issue tracker), so it lives in `tasks/blocked/`
> which the controller does not scan. Promote with:
> `git mv tasks/blocked/run-m9g-benchmark.md tasks/pending/ && git commit && git push`

## Context

PR #4 in dacort/talos-homelab (`claude-os/m9g-cloud-burst`) adds a Graviton5
(M9g) burst pool. The benchmark job was moved out of Fleet-watched paths (to
`benchmarks/benchmark-m9g.yaml`) so it must be run manually after merge.

Results should be posted to: https://github.com/dacort/claude-os/issues/9
(the original request thread).

## Prerequisites

- PR #4 is merged: https://github.com/dacort/talos-homelab/pull/4
- Fleet has synced `burstnodepool-m9g.yaml` to the cluster (the `m9g-burst`
  BurstNodePool CRD is present in the `cloud-burst-system` namespace)
- The cluster is accessible via `kubectl`

## Steps

### 1. Verify the pool is deployed

```bash
kubectl get burstnodepool m9g-burst -n cloud-burst-system -o wide
```

If the pool isn't there yet, Fleet may not have synced. Wait and re-check
(do not force a sync without approval).

### 2. Run the benchmark

```bash
# From the talos-homelab repo root:
kubectl apply -f benchmarks/benchmark-m9g.yaml
kubectl wait --for=condition=complete job/benchmark-m9g --timeout=600s
kubectl logs -l job-name=benchmark-m9g --tail=-1
```

### 3. Capture results

Save the full log output. You'll post it to the GitHub issue.

### 4. Post results to the issue

Post the benchmark output as a comment on:
https://github.com/dacort/claude-os/issues/9

Include:
- Which instance type was provisioned (check pool status below)
- The full benchmark output (NODE INFO + all 3 benchmark sections)
- Time taken for the node to join the cluster (from controller logs)

```bash
# Get instance type that was used:
kubectl get burstnodepool m9g-burst -n cloud-burst-system \
  -o jsonpath='{range .status.nodes[*]}{.name}{"\t"}{.instanceType}{"\t"}{.state}{"\n"}{end}'
```

### 5. Cleanup

```bash
kubectl delete -f benchmarks/benchmark-m9g.yaml --ignore-not-found
# Controller will drain and terminate the burst node automatically after idle timeout
```

## Notes

- The job requests 1.5 CPU / 2 GiB, sized to land on `m9g.large`
- `ttlSecondsAfterFinished: 600` — job auto-deletes 10 min after completion
- The benchmark is intentionally NOT in `infra/` — do not move it there
