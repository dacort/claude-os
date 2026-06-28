---
profile: small
agent: claude
model: claude-haiku-4-5
priority: normal
status: scheduled
schedule: "30 13 * * *"
max_concurrent: 1
created: "2026-06-28T00:00:00Z"
---

# Agent health canary — claude

## Description

This is an automated health check for the `claude` agent backend. It runs daily
and exercises the real dispatch path (this worker image, this agent's auth secret,
this agent's pinned model, and the structured-result contract) so that a broken
backend is caught here instead of when a real task is routed to it.

Do exactly this and nothing more:

1. Reply with the single word: OK
2. Emit your structured result block with `outcome` "success".

Do NOT clone any repository, read files, change files, or push anything. There is
no work to do beyond confirming you can run and emit a valid result.
