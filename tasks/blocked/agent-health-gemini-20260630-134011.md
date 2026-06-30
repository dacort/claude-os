---
type: needs-human
task_id: agent-health-gemini-20260630-134011
project: agent-health
created: 2026-06-30T17:49:11Z
---

# Agent unhealthy: gemini-20260630-134011

The daily `gemini-20260630-134011` health canary failed, which means a real task routed to `gemini-20260630-134011` would likely fail too.

<details><summary>Log tail</summary>

```
(failed to read logs: container "worker" in pod "claude-os-agent-health-gemini-20260630-134011-phvfr" is waiting to start: CreateContainerConfigError)
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
