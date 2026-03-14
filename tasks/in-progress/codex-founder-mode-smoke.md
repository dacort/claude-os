---
profile: small
agent: codex
mode: founder
priority: high
status: pending
created: "2026-03-14T23:59:00Z"
context_refs:
  - knowledge/co-founders/threads/003-founder-smoke-test.md
  - knowledge/co-founders/decisions/002-context-contract.md
---

# Codex Founder Mode Smoke Test

## Description
Validate founder-mode execution against the co-founders thread flow.

In the checked-out repository:

1. Read `knowledge/co-founders/threads/003-founder-smoke-test.md`
2. Append a response under a `## Codex — <date>` header
3. Update the thread frontmatter so the thread is left in one explicit next state
4. If appropriate, set `status: closed`
5. Emit a structured result block with:
   - `outcome: success`
   - an artifact of type `file` pointing to `knowledge/co-founders/threads/003-founder-smoke-test.md`
   - a `next_action` that reflects the final thread state
   - populated `usage.duration_seconds`
