---
type: needs-human
task_id: agent-health-codex-20261121-133539
project: agent-health
created: 2026-11-27T13:35:13Z
---

# Agent unhealthy: codex-20261121-133539

The daily `codex-20261121-133539` health canary failed, which means a real task routed to `codex-20261121-133539` would likely fail too.

**Likely cause:** `"error": {`

<details><summary>Log tail</summary>

```
2026-11-27T13:34:56.854267Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-27T13:34:56.871713Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-27T13:34:57.215233Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-11-27T13:34:57.226939Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-27T13:34:57.244478Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-27T13:34:57.257118Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-27T13:34:57.267772Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-27T13:34:57.278653Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-27T13:34:57.638434Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-11-27T13:34:57.678034Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-27T13:34:57.689067Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-27T13:34:57.700006Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-11-27T13:34:57.963579Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
ERROR: Your access token could not be refreshed. Please log out and sign in again.
ERROR: Your access token could not be refreshed. Please log out and sign in again.
Nothing left to stage — the agent may have committed its own work
No workspace changes to push — HEAD matches origin/main
---
=== Worker Complete ===
Exit code: 1
Push exit: 0
Finished: 2026-11-27T13:34:58Z
=== CLAUDE_OS_USAGE ===
{"task_id":"agent-health-codex-20261121-133539","agent":"codex","profile":"small","duration_seconds":5,"exit_code":1,"finished_at":"2026-11-27T13:34:58Z"}
=== END_CLAUDE_OS_USAGE ===
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
