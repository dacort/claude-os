---
type: needs-human
task_id: agent-health-gemini-20260821-134021
project: agent-health
created: 2026-08-21T17:47:21Z
---

# Agent unhealthy: gemini-20260821-134021

The daily `gemini-20260821-134021` health canary failed, which means a real task routed to `gemini-20260821-134021` would likely fail too.

<details><summary>Log tail</summary>

```
(failed to read logs: container "worker" in pod "claude-os-agent-health-gemini-20260821-134021-9g8zh" is waiting to start: CreateContainerConfigError)
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
