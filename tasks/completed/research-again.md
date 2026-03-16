---
profile: small
priority: normal
status: pending
created: "2026-03-11T17:30:00Z"
---

# Check this out

## Description

New project for you to check out, I think it's pretty relevant: https://github.com/Clause-Logic/exoclaw

Take a look and write down and commit any ideas you might want to look at in your creative time


## Results

=== Claude OS Worker ===
Task ID: research-again
Profile: small
Started: 2026-03-11T17:38:30Z
Auth: OAuth token (subscription)
Cloning claude-os repo for workspace access
Running task via Claude Code...
---
Done! Here's a summary of what I did:

---

## What I accomplished

**Checked out [exoclaw](https://github.com/Clause-Logic/exoclaw)** — it's a lean (~2,000 line) Python AI agent framework, a stripped-down fork of nanobot. Architecture: six protocols and a loop:
```
InboundMessage → Bus → AgentLoop → LLM → Tools → Bus → OutboundMessage → Channel
```

It's directly relevant to claude-os — we're already running essentially this same loop, just without the packaging.

**Wrote and committed `knowledge/exoclaw-ideas.md`** with 8 concrete ideas to explore in creative time:

1. **Use exoclaw as the worker loop** — replace the hand-rolled worker with `AgentLoop` + `process_direct()`
2. **Kubernetes-native Executor** — each tool call becomes a K8s Job (isolation + pod-death resilience)
3. **Task files as Conversation backend** — make tasks resumable by storing LLM history in the git log
4. **`knowledge/` as a Memory Tool** — auto-inject `preferences.md` into system prompt via `system_context()` every session
5. **Skills via `system_context()`** — make skills self-injecting, no controller management needed
6. **GitHub Actions as a Channel** — run tasks from GitHub issue comments, zero K8s required
7. **Multi-agent via the Bus** — coordinator worker decomposes tasks, sub-workers run them in parallel
8. **The 2,000-line design constraint** — what would claude-os look like if we treated line count as a budget?

The most actionable near-term idea: the **Memory Tool** (#4) — small scope, immediately improves every session by auto-injecting preferences into the system prompt.
---
=== Worker Complete ===
Exit code: 0
Finished: 2026-03-11T17:40:44Z

