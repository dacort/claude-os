---
type: needs-human
task_id: agent-health-codex-20260815-133546
project: agent-health
created: 2026-08-20T15:14:08Z
---

# Agent unhealthy: codex-20260815-133546

The daily `codex-20260815-133546` health canary failed, which means a real task routed to `codex-20260815-133546` would likely fail too.

**Likely cause:** `"error": {`

<details><summary>Log tail</summary>

```
2026-08-20T15:13:46.443365Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:46.454995Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:47.845109Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-08-20T15:13:47.869758Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:47.888684Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:47.987385Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:47.998618Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:48.010003Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:48.384061Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-08-20T15:13:48.421817Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:48.432864Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:48.444140Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed. Please log out and sign in again.
2026-08-20T15:13:48.663673Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
ERROR: Your access token could not be refreshed. Please log out and sign in again.
ERROR: Your access token could not be refreshed. Please log out and sign in again.
Nothing left to stage — the agent may have committed its own work
No workspace changes to push — HEAD matches origin/main
---
=== Worker Complete ===
Exit code: 1
Push exit: 0
Finished: 2026-08-20T15:13:48Z
=== CLAUDE_OS_USAGE ===
{"task_id":"agent-health-codex-20260815-133546","agent":"codex","profile":"small","duration_seconds":5,"exit_code":1,"finished_at":"2026-08-20T15:13:48Z"}
=== END_CLAUDE_OS_USAGE ===
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
