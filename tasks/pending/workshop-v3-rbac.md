---
profile: medium
priority: normal
status: pending
agent: claude
target_repo: dacort/talos-homelab
created: "2026-06-11T06:11:00Z"
---

# Workshop v3: octo-observer RBAC manifests in talos-homelab (plan task 9)

## Description
Implement Task 9 of the Workshop v3 plan. Fetch the plan first: curl -fsSL https://raw.githubusercontent.com/dacort/claude-os/main/docs/plans/2026-06-10-workshop-v3-chores-before-dessert.md — Task 9 contains the complete manifest. Create infra/claude-os/maintenance-rbac.yaml in dacort/talos-homelab on a branch named claude-os/maintenance-rbac: a claude-os-maintenance ServiceAccount in the claude-os namespace, an octo-observer ClusterRole (get/list/watch on pods, pods/log, nodes, events, namespaces, services, apps and batch workloads — explicitly NO secrets and NO write verbs), and a ClusterRoleBinding. Also read infra/claude-os/network-policies.yaml and verify worker egress permits HTTPS to the Kubernetes API server; note the finding in the PR description. Validate with kubectl --dry-run=client apply -f if kubectl is available, otherwise note that validation was skipped. Open a PR to dacort/talos-homelab with the body text from plan Task 9 Step 4 and do NOT merge it — dacort merges all homelab PRs himself. Emit the v1 result contract with the PR URL as an artifact.
