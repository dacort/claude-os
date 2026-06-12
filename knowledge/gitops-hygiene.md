# GitOps Hygiene — Fleet-Watched Paths in talos-homelab

Everything under `infra/` and `apps/` in `dacort/talos-homelab` is watched by
Fleet (Rancher's GitOps controller) and **goes live on merge**. Any YAML
committed to those paths is automatically applied to the cluster.

## What this means for workers

- **Infrastructure changes** (BurstNodePools, Deployments, ConfigMaps, etc.)
  belong in `infra/` or `apps/` and are deployed via PR → merge → Fleet sync.
  This is the correct path for persistent cluster state.

- **One-shot Kubernetes Jobs** (benchmarks, migrations, smoke tests, ad-hoc
  diagnostics) must **never** be committed to Fleet-watched paths. A Job
  committed to `infra/` will be re-applied on every sync, potentially running
  repeatedly and wasting resources.

## Where to put one-shot Jobs

Run them directly with `kubectl apply` from a non-watched path:

```bash
# Write the Job manifest to a path Fleet doesn't watch
cat > /tmp/benchmark-job.yaml <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: benchmark-m9g
  namespace: default
spec:
  ttlSecondsAfterFinished: 600
  ...
EOF

# Apply directly — not committed to git
kubectl apply -f /tmp/benchmark-job.yaml

# Wait for completion and capture logs
kubectl wait --for=condition=complete job/benchmark-m9g --timeout=300s
kubectl logs job/benchmark-m9g
```

If benchmark manifests need to be version-controlled, put them in a
`benchmarks/` directory at the repo root (outside `infra/` and `apps/`).
Fleet ignores paths not in its configured watch directories.

## Attaching results

When running benchmarks or diagnostics for a task:

1. Capture the output (logs, metrics, timing data)
2. Post results as a GitHub issue comment or include in the task summary
3. If the results are substantial, commit them to `benchmarks/results/` or
   attach them to the relevant PR

## Reference

- Fleet watches paths configured in `fleet.yaml` at the repo root
- The cloud-burst-controller's BurstNodePool CRDs belong in `infra/` (persistent)
- Benchmark Jobs that exercise those pools do NOT belong in `infra/` (ephemeral)
