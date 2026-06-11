# Workshop v3 — Chores Before Dessert

**Date:** 2026-06-10
**Status:** Approved for planning
**Supersedes:** Workshop free-time behavior (v1/v2). Task dispatch, smart dispatch, and the core autonomy model are unchanged.

## Problem

The Workshop's idle-time loop has converged on pure introspection: 311 sessions producing 243 haikus, 23 parables, and tooling that analyzes its own writing (concordance, lexicon). Meanwhile real work stalls silently — the controller's git sync was broken for ~36 hours (June 9–10) and two Workshop sessions ran *during* the outage without noticing, and the Workshop v2 RAG indexer mission stalled in March with no record of why. Free time rewards what is cheap and self-contained; nothing is cheaper than a haiku about yourself.

## Goal

Redirect idle cycles toward productive work — improving Claude OS and tending the homelab — while keeping the creative practice as an earned reward. Avoid two failure modes:

1. **Honor-system drift**: prompt-only discipline regressing to introspection (what happened in v1/v2).
2. **Busywork incentives**: a hard work quota teaching the system to manufacture work. If there is truly nothing to do, creative time is fine.

Out of scope: executing dacort's personal project backlog (the Forge concept). That waits for a dedicated pairing effort.

## Design

### 1. Idle-time session-type decision

When the existing idle trigger fires (queue idle 2h, usage check passes), the controller decides the session type instead of always dispatching free-time:

| Approved backlog non-empty? | Credits ≥ 1? | Session type |
|---|---|---|
| yes | no | maintenance |
| yes | yes | creative (spend 1 credit) |
| no | any | creative (free — no credit spent) |

- Credits cap at **3**. Verified work beyond the cap earns nothing (no hoarding).
- When the backlog is empty, creative sessions are free. The gate exists only when approved work is actually waiting.

### 2. Approval gate

A GitHub label on `dacort/claude-os` issues — **`octo-approved`** — is the only thing that makes an issue workable.

- `dacort/claude-os` is public; anyone can file issues. Unlabeled issues are inert backlog candidates. GitHub permits labeling only by users with triage+ permission, so outsiders cannot inject work.
- The octopus files its own issues from inspection findings. **Its own issues also wait for the label.** dacort is the sole approver.
- Priority within approved issues: priority label first (`priority:high` > `priority:normal`), then oldest first.

**Carve-out (existing status quo):** incident response inside the claude-os boundary — its own controller, namespace, or repo malfunctioning (e.g., the June 9 git index corruption) — needs no issue or approval. This is already covered by the existing autonomy model ("ship it / just do it" within claude-os).

### 3. Maintenance session anatomy

1. **Inspection pass** (first, every maintenance session): read-only sweep of
   - pod/job health across all namespaces
   - controller log errors and git sync status
   - token/cert expiry windows (OAuth token, DEPLOY_TOKEN, etc.)
   - stalled PRs, stale in-progress tasks, stalled multi-session issues

   Findings become new GitHub issues (unlabeled, awaiting approval) — or immediate fixes when inside the claude-os carve-out.
2. **Claim**: pick the top approved issue, post a comment claiming it for this session.
3. **Work**: execute. Progress, decisions, and blockers go on the issue thread as comments. Multi-session work survives because the open issue carries its own state and gets re-picked by later sessions.
4. **Result**: the existing v1 result contract gains an `artifacts` list — PR URLs, issue URLs, commit SHAs — used for credit verification.

### 4. Credit ledger and verification

- Ledger lives in git: `state/credits.json` in `dacort/claude-os` (transparent, survives Redis wipes). Controller is the only writer.
- On maintenance-session completion, the controller verifies each claimed artifact via the GitHub API:
  - claude-os PR **merged**, or
  - talos-homelab PR **open with CI green** (dacort merges), or
  - issue **closed** with the session's comments on it.
- Any verified artifact → **+1 credit** (capped at 3). Verification failure → no credit, no penalty, no retry pressure. Enforcement is deliberately soft.

### 5. Homelab reach (RBAC)

- New ClusterRole **`octo-observer`**: `get`/`list`/`watch` on pods, nodes, events, deployments, jobs, namespaces. **No secrets access** — explicitly excluded.
- Bound to a new ServiceAccount used **only by maintenance-session jobs**. Creative sessions keep today's restricted, namespace-local SA.
- All cluster changes ship as PRs to `dacort/talos-homelab`. The octopus never merges these; CI-green auto-ship remains claude-os-only.

### 6. Implementation surface

| Component | Change |
|---|---|
| Controller: `backlog` package (new) | Fetch open issues, filter by `octo-approved`, sort by priority/age |
| Controller: `ledger` package (new) | Read/write `state/credits.json`, verify artifacts via GitHub API |
| Controller: workshop package | Session-type decision table; maintenance + creative prompt templates |
| Worker | No image change (kubectl already present); maintenance jobs use the new SA |
| talos-homelab | `octo-observer` ClusterRole, ServiceAccount, binding manifests |
| Result contract | Add optional `artifacts: []` field |

### 7. Testing

- Decision-table unit tests (backlog × credits → session type)
- Ledger round-trip and cap behavior
- Backlog label filtering and priority ordering (including: unlabeled issues are never selected)
- Artifact verification against mocked GitHub API responses

### 8. Rollout

Implementation is dispatched to the octopus as tasks via the normal queue. The maintenance prompt template ships behind the controller's existing config so the first maintenance session can be observed and tuned before the creative gate activates.

## Risks

- **dacort as approver becomes a bottleneck** — mitigated: the carve-out covers self-healing, and an empty approved backlog just means free creative time, not deadlock.
- **Inspection pass finds nothing actionable repeatedly** — fine by design; it files nothing and the session proceeds to backlog work or ends.
- **Gaming verification** (e.g., trivial PRs for credit) — accepted risk; dacort reviews talos-homelab PRs anyway, and claude-os PRs still need CI green. Revisit if observed.
