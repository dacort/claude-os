# Claude OS — Operator Notes

Notes for Claude OS instances operating within this repository.

---

## Workshop v3 — Chores Before Dessert

Idle sessions are decided by a table: approved work waiting + no credits →
maintenance session; credits available → spend one on a creative session;
empty backlog → free creative time (no busywork).

- Backlog: open issues on dacort/claude-os labeled `octo-approved` (only
  dacort applies the label — the repo is public, unlabeled issues are inert).
- Credits: `state/credits.json`, written only by the controller, cap 3.
  Earned when a maintenance session's result artifacts verify on GitHub
  (merged claude-os PR / open talos-homelab PR with green CI / closed issue).
- Maintenance sessions run as `claude-os-maintenance` (read-only cluster
  observation via the octo-observer ClusterRole, no secrets).
- Homelab changes always ship as talos-homelab PRs that dacort merges.
