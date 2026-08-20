---
type: needs-human
task_id: agent-health-codex-20260814-133546
project: agent-health
created: 2026-08-20T15:14:06Z
---

# Agent unhealthy: codex-20260814-133546

The daily `codex-20260814-133546` health canary failed, which means a real task routed to `codex-20260814-133546` would likely fail too.

**Likely cause:** `"error": {`

<details><summary>Log tail</summary>

```
2026-08-20T15:13:56.565757Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:56.884018Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-08-20T15:13:56.926705Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:56.946006Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:56.958026Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:56.969057Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:56.979501Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:57.313458Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-08-20T15:13:57.352926Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:57.362757Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:57.373674Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:57.683397Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
ERROR: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:57.700008Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
ERROR: Your access token could not be refreshed. Please log out and sign in again.
Nothing left to stage — the agent may have committed its own work
No workspace changes to push — HEAD matches origin/main
---
=== Worker Complete ===
Exit code: 1
Push exit: 0
Finished: 2026-08-20T15:13:57Z
=== CLAUDE_OS_USAGE ===
{"task_id":"agent-health-codex-20260814-133546","agent":"codex","profile":"small","duration_seconds":4,"exit_code":1,"finished_at":"2026-08-20T15:13:57Z"}
=== END_CLAUDE_OS_USAGE ===
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
