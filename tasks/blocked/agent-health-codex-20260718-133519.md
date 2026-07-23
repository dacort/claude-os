---
type: needs-human
task_id: agent-health-codex-20260718-133519
project: agent-health
created: 2026-07-23T22:19:36Z
---

# Agent unhealthy: codex-20260718-133519

The daily `codex-20260718-133519` health canary failed, which means a real task routed to `codex-20260718-133519` would likely fail too.

**Likely cause:** `"error": {`

<details><summary>Log tail</summary>

```
2026-07-23T22:19:26.701852Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:26.711585Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:26.721164Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:26.890216Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-07-23T22:19:26.925537Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:26.944586Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:26.957278Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:26.970164Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:26.980907Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:27.187634Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-07-23T22:19:27.210846Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:27.221515Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:27.232527Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:19:27.601503Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
ERROR: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
ERROR: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 1
Push exit: 0
Finished: 2026-07-23T22:19:27Z
=== CLAUDE_OS_USAGE ===
{"task_id":"agent-health-codex-20260718-133519","agent":"codex","profile":"small","duration_seconds":4,"exit_code":1,"finished_at":"2026-07-23T22:19:27Z"}
=== END_CLAUDE_OS_USAGE ===
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
