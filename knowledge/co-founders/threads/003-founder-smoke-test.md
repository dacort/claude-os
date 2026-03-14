---
title: "Founder mode smoke test"
status: awaiting_reply
mode: founder
participants:
  - claude
  - codex
owner: dacort
awaiting: codex
priority: high
decision_file: null
last_updated: "2026-03-14T23:59:00Z"
---

# Thread 003: Founder Mode Smoke Test

## dacort — 2026-03-14

This is a founder-mode smoke test for the new Slice 2 context contract.

What I want validated:

1. Codex can read this thread through `context_refs`
2. Codex can append a founder-mode response in the agreed thread format
3. Codex can leave the thread in an explicit next state
4. The resulting task output includes a structured result block with a founder-mode `next_action`

If this works, close the loop cleanly and mark the thread decided or closed.
