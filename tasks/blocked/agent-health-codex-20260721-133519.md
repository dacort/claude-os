---
type: needs-human
task_id: agent-health-codex-20260721-133519
project: agent-health
created: 2026-07-23T22:19:06Z
---

# Agent unhealthy: codex-20260721-133519

The daily `codex-20260721-133519` health canary failed, which means a real task routed to `codex-20260721-133519` would likely fail too.

**Likely cause:** `"error": {`

<details><summary>Log tail</summary>

```
2026-07-23T22:18:56.744506Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:56.754835Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:56.765147Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:56.950987Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-07-23T22:18:56.965310Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:57.007734Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:57.021260Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:57.033982Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:57.044960Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:57.366649Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-07-23T22:18:57.390256Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:57.400860Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:57.411709Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:57.633383Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
ERROR: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
ERROR: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 1
Push exit: 0
Finished: 2026-07-23T22:18:57Z
=== CLAUDE_OS_USAGE ===
{"task_id":"agent-health-codex-20260721-133519","agent":"codex","profile":"small","duration_seconds":4,"exit_code":1,"finished_at":"2026-07-23T22:18:57Z"}
=== END_CLAUDE_OS_USAGE ===
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
