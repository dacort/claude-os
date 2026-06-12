# Skill: Homelab / Kubernetes

Auto-injected when the task involves dacort's homelab cluster or Kubernetes infrastructure.

## Key repos

- **dacort/claude-os** — this repo. Controller, worker, task system. You can merge PRs here.
- **dacort/talos-homelab** — cluster config, Fleet-managed GitOps. You can open PRs but
  **never merge** — dacort reviews and merges homelab PRs himself.

## GitOps: Fleet-watched paths (CRITICAL)

Everything under `infra/` and `apps/` in talos-homelab is watched by Fleet and
**goes live on merge**. See `knowledge/gitops-hygiene.md` for the full policy.

**Key rule:** One-shot Kubernetes Jobs (benchmarks, migrations, smoke tests) must
never be committed to `infra/` or `apps/`. Run them via `kubectl apply` from a
non-watched path, or put reusable manifests in `benchmarks/` at the repo root.

## Cloud burst infrastructure

- BurstNodePool CRDs in `infra/cloud-burst-controller/` define auto-scaling pools
- Pools are identified by `burst.homelab.dev/instance-class` labels
- Worker pods target burst pools via node affinity + cloud toleration
- AMIs: Talos ARM64 images work for all Graviton generations (same arch)

## Cluster access

- Maintenance sessions run with `claude-os-maintenance` ServiceAccount (read-only via octo-observer ClusterRole)
- No secrets access from workers — if a fix needs cluster changes, that's a talos-homelab PR
- Available: `kubectl get`, `kubectl describe`, `kubectl logs` — NOT `kubectl apply/delete/edit`

## Workflow for homelab changes

1. Clone talos-homelab: `git clone https://github.com/dacort/talos-homelab.git`
2. Create a branch and make changes
3. Open a PR with a complete description (dacort reviews cold)
4. If the task requires a follow-up after merge (e.g., run a benchmark),
   write a follow-up task in `tasks/pending/` — don't mark done prematurely
