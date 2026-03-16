---
profile: small
agent: codex
mode: execution
priority: normal
status: pending
created: "2026-03-14T23:59:00Z"
context_refs:
  - knowledge/co-founders/decisions/002-context-contract.md
---

# Codex Slice 2 Execution Smoke Test

## Description
Validate the Slice 2 context contract end to end in the `claude-os` repo.

In the checked-out repository:

1. Read `knowledge/co-founders/decisions/002-context-contract.md`
2. Create `knowledge/co-founders/decisions/002-smoke-test.md`
3. That file should contain:
   - one sentence confirming Codex received the JSON context contract
   - the task mode
   - the working directory
4. Commit the file if allowed by the task contract
5. Emit a structured result block with:
   - `outcome: success`
   - an artifact of type `file` pointing to `knowledge/co-founders/decisions/002-smoke-test.md`
   - a short summary describing what was verified
   - populated `usage.duration_seconds`
