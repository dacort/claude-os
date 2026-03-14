---
profile: small
agent: codex
mode: execution
priority: normal
created: "2026-03-14T23:59:00Z"
context_refs:
  - knowledge/co-founders/decisions/002-context-contract.md
---

# Codex Slice 2 Smoke Test

## Description
Confirm the Slice 2 context contract is working end to end.

In the claude-os repo:
1. Read the context contract decision in knowledge/co-founders/decisions/002-context-contract.md
2. Create a small file at knowledge/co-founders/decisions/002-smoke-test.md
3. The file should contain:
   - one sentence confirming Codex received the JSON context contract
   - the task mode
   - the working directory
4. Commit the file to the current branch if allowed by the task contract
5. Emit a structured result block with:
   - outcome: success
   - one artifact of type file pointing to knowledge/co-founders/decisions/002-smoke-test.md
   - summary describing what was verified
   - usage with duration_seconds populated
