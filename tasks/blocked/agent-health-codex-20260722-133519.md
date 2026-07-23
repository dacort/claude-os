---
type: needs-human
task_id: agent-health-codex-20260722-133519
project: agent-health
created: 2026-07-23T22:18:51Z
---

# Agent unhealthy: codex-20260722-133519

The daily `codex-20260722-133519` health canary failed, which means a real task routed to `codex-20260722-133519` would likely fail too.

**Likely cause:** `"error": {`

<details><summary>Log tail</summary>

```
2026-07-23T22:18:46.895364Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:46.904481Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:47.080301Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-07-23T22:18:47.106353Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:47.124735Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:47.140824Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:47.154487Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:47.166600Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:47.367467Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
2026-07-23T22:18:47.408641Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:47.426695Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:47.438598Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:47.655842Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error: 401 Unauthorized, url: wss://chatgpt.com/backend-api/codex/responses
ERROR: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
ERROR: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
2026-07-23T22:18:47.699743Z ERROR codex_login::auth::manager: Failed to refresh token: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 1
Push exit: 0
Finished: 2026-07-23T22:18:47Z
=== CLAUDE_OS_USAGE ===
{"task_id":"agent-health-codex-20260722-133519","agent":"codex","profile":"small","duration_seconds":4,"exit_code":1,"finished_at":"2026-07-23T22:18:47Z"}
=== END_CLAUDE_OS_USAGE ===
```
</details>

**Remediation pointers**
- Check the agent's auth secret and pinned model.

_Filed automatically by the agent health check. This issue dedups by task ID and closes itself when the next canary run succeeds._
