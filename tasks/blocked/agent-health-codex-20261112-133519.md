---
type: needs-human
task_id: agent-health-codex-20261112-133519
project: agent-health
created: 2026-11-19T00:51:11Z
---

# Agent unhealthy: codex-20261112-133519

The daily `codex-20261112-133519` health canary failed, which means a real task routed to `codex-20261112-133519` would likely fail too.

**Likely cause:** `"error": {`

<details><summary>Log tail</summary>

```
2026-11-19T00:50:54.930294Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-19T00:50:54.943942Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-19T00:50:55.170477Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-11-19T00:50:55.202486Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-19T00:50:55.219003Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-19T00:50:55.234748Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-19T00:50:55.245655Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-19T00:50:55.256817Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-19T00:50:55.625826Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-11-19T00:50:55.662878Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-19T00:50:55.671827Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-19T00:50:55.681511Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-19T00:50:56.034228Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
ERROR: Your access token could not be refreshed. Please log out and sign in again.
ERROR: Your access token could not be refreshed. Please log out and sign in again.
Nothing left to stage — the agent may have committed its own work
No workspace changes to push — HEAD matches origin/main
---
=== Worker Complete ===
Exit code: 1
Push exit: 0
Finished: 2026-11-19T00:50:56Z
=== CLAUDE_OS_USAGE ===
{"task_id":"agent-health-codex-20261112-133519","agent":"codex","profile":"small","duration_seconds":5,"exit_code":1,"finished_at":"2026-11-19T00:50:56Z"}
=== END_CLAUDE_OS_USAGE ===
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
