---
profile: medium
priority: normal
status: pending
created: "2026-06-12T18:29:01Z"
---

# Teach workers to self-decompose tasks across external gates

## Description

Incident motivating this: claude-os issue #9 asked for an M9g burst pool, a
benchmark run, and a follow-up learning task. The worker (dispatched as
profile: small) opened talos-homelab PR #4 and stopped — it never planned the
benchmark run past the merge gate, and it silently dropped the "create a
second task for yourself" instruction.

Make two changes in this repo:

### 1. Add a self-decomposition rule to the worker prompt

Find where the worker system prompt / task prompt template is assembled
(likely in the worker image entrypoint or the controller's job-spec
construction) and add a rule along these lines:

- If a task has phases separated by an external gate (a PR merge a human must
  perform, missing credentials, awaited input), complete the current phase,
  then WRITE A FOLLOW-UP TASK FILE in `tasks/pending/` describing the
  remaining work and what unblocks it (use `depends_on` frontmatter when the
  dependency is another task). Never mark the overall request done when only
  phase one is delivered.
- Before finishing, re-read the original task and verify EVERY instruction was
  addressed — multi-part requests must not lose trailing items.

### 2. Add a GitOps hygiene note to the knowledge base

Add a knowledge doc (e.g. `knowledge/gitops-hygiene.md`) stating: everything
under `infra/` and `apps/` in dacort/talos-homelab is Fleet-watched and goes
live on merge. One-shot Kubernetes Jobs must never be committed there — run
them with kubectl from a non-watched path (e.g. `benchmarks/`) and attach
logs to results. Reference this doc from the worker prompt if there is an
existing mechanism for surfacing knowledge docs.

Also worth a quick look: why did triage score issue #9's task as
profile: small? A multi-repo infra + benchmark + report task should land
medium or large. If it is a cheap fix in the triage heuristics, do it; if
not, file a GitHub issue so it is tracked.
