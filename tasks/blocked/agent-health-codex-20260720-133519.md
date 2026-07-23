---
type: needs-human
task_id: agent-health-codex-20260720-133519
project: agent-health
created: 2026-07-23T22:19:22Z
---

# Agent unhealthy: codex-20260720-133519

The daily `codex-20260720-133519` health canary failed, which means a real task routed to `codex-20260720-133519` would likely fail too.

**Likely cause:** `"error": {`

<details><summary>Log tail</summary>

```
2026-07-23T22:19:06.712788Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:06.723792Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:06.938379Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-07-23T22:19:06.969723Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:06.990001Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:07.001969Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:07.012507Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:07.024912Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:07.225722Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-07-23T22:19:07.250333Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:07.268326Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:07.287925Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:07.499629Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
ERROR: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
ERROR: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:07.516097Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 1
Push exit: 0
Finished: 2026-07-23T22:19:07Z
=== CLAUDE_OS_USAGE ===
{"task_id":"agent-health-codex-20260720-133519","agent":"codex","profile":"small","duration_seconds":4,"exit_code":1,"finished_at":"2026-07-23T22:19:07Z"}
=== END_CLAUDE_OS_USAGE ===
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
