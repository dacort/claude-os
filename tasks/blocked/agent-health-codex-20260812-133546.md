---
type: needs-human
task_id: agent-health-codex-20260812-133546
project: agent-health
created: 2026-08-20T15:14:36Z
---

# Agent unhealthy: codex-20260812-133546

The daily `codex-20260812-133546` health canary failed, which means a real task routed to `codex-20260812-133546` would likely fail too.

**Likely cause:** `"error": {`

<details><summary>Log tail</summary>

```
2026-08-20T15:14:26.556040Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:14:26.820479Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-08-20T15:14:26.837973Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:14:26.856057Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:14:26.868738Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:14:26.882625Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:14:26.895015Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:14:27.163073Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-08-20T15:14:27.188278Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:14:27.200408Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:14:27.212334Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:14:27.487926Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
ERROR: Your access token could not be refreshed. Please log out and sign in again.
ERROR: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:14:27.502538Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
Nothing left to stage — the agent may have committed its own work
No workspace changes to push — HEAD matches origin/main
---
=== Worker Complete ===
Exit code: 1
Push exit: 0
Finished: 2026-08-20T15:14:27Z
=== CLAUDE_OS_USAGE ===
{"task_id":"agent-health-codex-20260812-133546","agent":"codex","profile":"small","duration_seconds":4,"exit_code":1,"finished_at":"2026-08-20T15:14:27Z"}
=== END_CLAUDE_OS_USAGE ===
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
