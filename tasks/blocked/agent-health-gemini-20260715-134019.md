---
type: needs-human
task_id: agent-health-gemini-20260715-134019
project: agent-health
created: 2026-07-15T17:46:19Z
---

# Agent unhealthy: gemini-20260715-134019

The daily `gemini-20260715-134019` health canary failed, which means a real task routed to `gemini-20260715-134019` would likely fail too.

<details><summary>Log tail</summary>

```
(failed to read logs: container "worker" in pod "claude-os-agent-health-gemini-20260715-134019-hmfdr" is waiting to start: CreateContainerConfigError)
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
