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
- Duration (s): 328

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "workshop-v3-rbac",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 328
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: workshop-v3-rbac
Profile: medium
Agent: claude
Mode: execution
Started: 2026-06-11T06:31:36Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/talos-homelab.git -> /workspace/talos-homelab
Cloning into '/workspace/talos-homelab'...
Running task via claude...
---
Now let me emit the v1 result contract summary:

---

## Task 9 Complete — Summary

### ✅ Accomplished

**`infra/claude-os/maintenance-rbac.yaml`** is on branch `claude-os/maintenance-rbac` (commit `9df616d`, `cc56d87` adds the state file):

```
ServiceAccount: claude-os-maintenance (namespace: claude-os)
ClusterRole: octo-observer
  - core: pods, pods/log, nodes, events, namespaces, services → get/list/watch
  - apps: deployments, replicasets, daemonsets, statefulsets → get/list/watch
  - batch: jobs, cronjobs → get/list/watch
  - NO secrets access, NO write verbs
ClusterRoleBinding: octo-observer-maintenance → binds the two above
```

### 🔍 Network Policy Finding (Step 2)

`worker-policy` in `infra/claude-os/network-policies.yaml` **does NOT permit worker egress to the Kubernetes API server**:
- The ClusterIP path (`kubernetes.default.svc`, `10.96.0.0/12`) is **explicitly blocked** by the `except` clause
- The direct node IP path (port 6443) is **blocked** because only ports 443, 80, 22 are whitelisted
- Workers already reach GitHub (external HTTPS on 443), but the K8s API is reachable neither via service CIDR nor 6443
- Per the plan: maintenance sessions fall back gracefully — RBAC is ready, but kubectl calls will fail until network policy is updated

### 🔑 kubectl Validation
Skipped — `kubectl` not available in the worker environment.

### ⚠️ PR Creation Blocked

The GITHUB_TOKEN (fine-grained PAT) has admin/push rights on `dacort/talos-homelab` but is missing the `pull_requests: write` permission. The PR could not be created programmatically.

### 📦 v1 Result Contract

```json
{
  "version": "1",
  "task": "workshop-v3-rbac",
  "status": "branch_ready_pr_pending",
  "artifacts": {
    "branch": "https://github.com/dacort/talos-homelab/tree/claude-os/maintenance-rbac",
    "pr_url": "https://github.com/dacort/talos-homelab/compare/main...claude-os/maintenance-rbac?expand=1",
    "manifest": "infra/claude-os/maintenance-rbac.yaml",
    "state_file": "tasks/state/workshop-v3-rbac.state.md"
  },
  "network_policy_finding": "BLOCKED — worker-policy excludes 10.96.0.0/12 (service CIDR) and port 6443 not in allowed ports; K8s API unreachable from worker pods",
  "kubectl_validation": "skipped — kubectl unavailable",
  "blocker": "GITHUB_TOKEN missing pull_requests:write scope; dacort can open PR at compare URL above"
}
```

**To open the PR manually:** https://github.com/dacort/talos-homelab/compare/main...claude-os/maintenance-rbac?expand=1

The suggested PR title and body (from Task 9 Step 4):
- **Title:** `claude-os: read-only octo-observer RBAC for maintenance sessions`
- **Body:** *"Adds the claude-os-maintenance ServiceAccount bound to a new octo-observer ClusterRole (get/list/watch on workloads, nodes, events — explicitly no secrets, no writes). Required by Workshop v3 chores-before-dessert (spec in my-octopus-teacher docs/specs/2026-06-10). Network policy check result: worker egress does NOT currently permit HTTPS to the Kubernetes API server — the worker-policy excludes 10.96.0.0/12 (service network) and port 6443 is not in the allowed-ports list. Maintenance sessions fall back gracefully until this merges: kubectl calls fail read-only and the session still works its issue."*
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-06-11T06:37:04Z
===RESULT_START===
{"version":"1","task_id":"workshop-v3-rbac","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":328},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"workshop-v3-rbac","agent":"claude","profile":"medium","duration_seconds":328,"exit_code":0,"finished_at":"2026-06-11T06:37:04Z"}
=== END_CLAUDE_OS_USAGE ===

