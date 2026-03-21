# cos CLI — HTTP Protocol Spec

*API contract between the `cos` CLI and the Claude OS controller.*
*Downstream consumers: cos-server (implements these endpoints) and cos-client (calls them).*

---

## Base URL

All endpoints are prefixed with `/api/v1`. The controller already serves on
`cfg.Server.Port` (default 8080) — these endpoints join the existing mux
alongside `/healthz` and `/readyz`.

---

## Common Conventions

**Content-Type:** `application/json` for all request and response bodies.

**Error format:** Every non-2xx response returns:

```json
{
  "error": "short machine-readable code",
  "message": "Human-readable explanation."
}
```

Error codes are lowercase snake_case strings (not HTTP status codes repeated).

**Standard error codes:**

| HTTP Status | Error Code | When |
|-------------|-----------|------|
| 400 | `invalid_request` | Malformed JSON, missing required fields, invalid enum value |
| 404 | `not_found` | Task ID doesn't exist in Redis |
| 500 | `internal_error` | Redis down, unexpected failure |

**Timestamps:** RFC 3339 with UTC timezone (`2026-03-21T14:02:33Z`). Zero-value times are omitted (Go `omitempty` on `time.Time` pointer or check `.IsZero()`).

**Nullability:** Optional fields are omitted from JSON when empty/zero, not set to `null`.

---

## Endpoints

### GET /api/v1/status

System-wide snapshot. This is the primary endpoint — it aggregates queue state,
governance, and agent health into a single response.

**Query parameters:** None required.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `recent` | int | 5 | Number of recently finished tasks to include (max 50) |

**Response: 200 OK**

```json
{
  "controller": {
    "version": "0.4.0"
  },
  "queue": {
    "pending": 2,
    "running": 1,
    "blocked": 0
  },
  "governance": {
    "tokens_used_today": 42180,
    "tokens_limit_today": 200000,
    "burst_spend_today": 0.45,
    "burst_budget_today": 5.00
  },
  "agents": {
    "claude": {
      "status": "ok"
    },
    "codex": {
      "status": "rate_limited",
      "rate_limited_until": "2026-03-21T14:40:00Z"
    }
  },
  "running": [
    {
      "id": "cos-server",
      "title": "Add cos API endpoints to the controller",
      "agent": "claude",
      "profile": "medium",
      "started_at": "2026-03-21T13:58:21Z"
    }
  ],
  "pending": [
    {
      "id": "cos-client",
      "title": "Build the cos CLI binary",
      "priority": 10,
      "profile": "medium",
      "created_at": "2026-03-21T13:55:00Z"
    }
  ],
  "recent": [
    {
      "id": "cos-design",
      "title": "Design the cos CLI: UX, protocol, and data shapes",
      "outcome": "success",
      "duration_seconds": 150,
      "finished_at": "2026-03-21T14:00:31Z"
    }
  ]
}
```

**Implementation notes:**
- `queue` counts come from: pending = `ZCARD claude-os:queue`, running = `SCARD claude-os:running`, blocked = sum of all `SCARD claude-os:plan:*:blocked` (or track a global counter).
- `governance` reads from the daily token and burst Redis keys.
- `agents` checks rate-limit keys for each known agent (claude, codex, gemini). Include TTL for rate-limited agents so the CLI can show remaining time.
- `running` iterates `SMEMBERS claude-os:running` and fetches each task.
- `pending` reads `ZREVRANGE claude-os:queue 0 -1` and fetches each task.
- `recent` requires a new mechanism: the controller should maintain a bounded list (`LPUSH`/`LTRIM` on `claude-os:recent`, capped at 50). Push task IDs on completion. The status handler reads the last N and fetches task details.

---

### GET /api/v1/tasks/{id}

Full detail for a single task.

**Response: 200 OK**

```json
{
  "id": "cos-design",
  "title": "Design the cos CLI: UX, protocol, and data shapes",
  "description": "Design the terminal UX and HTTP protocol...",
  "target_repo": "github.com/dacort/claude-os",
  "profile": "small",
  "agent": "claude",
  "model": "claude-opus-4-6",
  "priority": 10,
  "status": "completed",
  "task_type": "subtask",
  "plan_id": "cos-cli-20260321",
  "depends_on": [],
  "created_at": "2026-03-21T13:55:00Z",
  "started_at": "2026-03-21T13:58:01Z",
  "finished_at": "2026-03-21T14:00:31Z",
  "tokens_used": 20000,
  "duration_seconds": 150,
  "result": {
    "outcome": "success",
    "summary": "Designed cos CLI UX and HTTP protocol spec.",
    "artifacts": [
      {"type": "file", "path": "knowledge/plans/cos-cli-20260321/ux-design.md"},
      {"type": "file", "path": "knowledge/plans/cos-cli-20260321/protocol.md"}
    ]
  },
  "plan_progress": {
    "completed": 1,
    "total": 3
  }
}
```

**Field notes:**
- `result` is the parsed `TaskResult` if available, otherwise `null`. For tasks still running or pending, this field is absent.
- `plan_progress` is included only when `plan_id` is set. Fetched via `Queue.PlanProgress()`.
- The `description` field may be long. The CLI truncates in table views but shows full text in `cos task`.

**Response: 404 Not Found**

```json
{
  "error": "not_found",
  "message": "Task \"nonexistent-task\" not found."
}
```

---

### GET /api/v1/tasks/{id}/logs

Fetch logs for a task. For running tasks, supports streaming via SSE.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `tail` | int | 0 | Return only the last N lines (0 = all) |
| `follow` | bool | false | Stream new lines as they arrive (SSE) |

#### Non-streaming response (completed tasks, or `follow=false`): 200 OK

```json
{
  "task_id": "cos-design",
  "status": "completed",
  "lines": [
    {"ts": "2026-03-21T13:58:01Z", "text": "Cloning github.com/dacort/claude-os..."},
    {"ts": "2026-03-21T13:58:03Z", "text": "Reading protocol spec..."},
    {"ts": "2026-03-21T14:00:31Z", "text": "Done."}
  ]
}
```

If log lines don't have parseable timestamps, `ts` is omitted and `text` contains the raw line.

#### Streaming response (`follow=true`, task is running): 200 OK, `Content-Type: text/event-stream`

```
data: {"ts":"2026-03-21T14:02:33Z","text":"Cloning github.com/dacort/claude-os..."}

data: {"ts":"2026-03-21T14:02:35Z","text":"Reading protocol spec..."}

event: done
data: {"status":"completed","outcome":"success"}
```

- Each `data:` line is a JSON log line (same shape as the `lines` array entries).
- A `done` event is sent when the task finishes, with the final status.
- The client should handle the SSE connection dropping (controller restart, network) by reconnecting and using `tail` to avoid duplicates.

**Implementation notes:**
- For completed/failed tasks: logs are stored on the task's `Result` field or can be fetched from the K8s pod logs (if the job/pod still exists within the TTL window). If logs are unavailable, return an empty `lines` array.
- For running tasks: use the Kubernetes `pods/log` API with `follow=true` to stream. The controller proxies the K8s log stream as SSE events.
- Log retrieval is best-effort. Jobs are cleaned up after 1 hour. If logs are gone, say so:

```json
{
  "task_id": "old-task",
  "status": "completed",
  "lines": [],
  "message": "Logs no longer available (job cleaned up)."
}
```

**Response: 404 Not Found** — same as task detail.

---

### POST /api/v1/tasks

Create a new task and enqueue it.

**Request body:**

```json
{
  "title": "Fix the broken vitals test",
  "description": "The vitals.py test is failing because...",
  "target_repo": "github.com/dacort/claude-os",
  "profile": "small",
  "priority": "normal",
  "agent": "claude"
}
```

| Field | Type | Required | Default | Validation |
|-------|------|----------|---------|------------|
| `title` | string | yes | — | 1-200 chars |
| `description` | string | no | same as title | max 5000 chars |
| `target_repo` | string | yes | — | must match `owner/repo` or `github.com/owner/repo` |
| `profile` | string | no | `"small"` | one of: small, medium, large, burst, think |
| `priority` | string | no | `"normal"` | one of: creative, normal, high |
| `agent` | string | no | — (triage decides) | one of: claude, codex, gemini |
| `model` | string | no | — (profile default) | valid model identifier |
| `context_refs` | string[] | no | — | file paths for additional context |

**Response: 201 Created**

```json
{
  "id": "fix-the-broken-vitals-test-a1b2",
  "title": "Fix the broken vitals test",
  "status": "pending",
  "queue_position": 3,
  "created_at": "2026-03-21T14:05:00Z"
}
```

**ID generation:** Slugify the title (lowercase, hyphens, truncate to 40 chars) and append a 4-char random suffix to avoid collisions.

**Response: 400 Bad Request**

```json
{
  "error": "invalid_request",
  "message": "\"target_repo\" is required."
}
```

```json
{
  "error": "invalid_request",
  "message": "Invalid profile \"huge\". Valid profiles: small, medium, large, burst, think."
}
```

---

## Data Shapes Summary

### TaskSummary (used in status lists)

Minimal fields for table rendering. Different subsets for running/pending/recent:

```
Running:  {id, title, agent, profile, started_at}
Pending:  {id, title, priority, profile, created_at}
Recent:   {id, title, outcome, duration_seconds, finished_at}
```

### TaskDetail (used in `cos task`)

Full `queue.Task` struct serialized as JSON, plus:
- `result`: parsed `TaskResult` (if available)
- `plan_progress`: `{completed, total}` (if part of a plan)

### LogEntry

```json
{"ts": "2026-03-21T14:02:33Z", "text": "log line content"}
```

`ts` is optional — omitted when the line has no parseable timestamp.

---

## Versioning

The `/api/v1/` prefix allows future breaking changes under `/api/v2/`. Within v1, fields may be added but never removed or type-changed.

---

## Implementation Checklist for cos-server

1. Add a `cosapi` package (e.g., `controller/cosapi/handler.go`).
2. Register routes on the existing `http.ServeMux` in `main.go`.
3. Pass `*queue.Queue`, `*governance.Governor`, and `kubernetes.Interface` to the handler.
4. Add a `claude-os:recent` Redis list — push task IDs on completion in the watcher, `LTRIM` to 50.
5. For `/tasks/{id}/logs`: fetch from K8s pod logs API. The dispatcher already tracks job-to-task mappings.
6. Add tests using `httptest` (same pattern as `triage_test.go`).
7. No new dependencies — stdlib `net/http` + existing Redis client.

## Implementation Checklist for cos-client

1. Create `cmd/cos/main.go` in the controller module.
2. Use `flag` package — no cobra/viper.
3. Read `CONTROLLER_URL` from env (default `http://localhost:8080`).
4. Each subcommand is a function: `runStatus()`, `runLog()`, `runTask()`, `runRun()`.
5. `--json` on every subcommand writes compact JSON to stdout and exits.
6. ANSI colors via inline escape codes. Respect `NO_COLOR` env var.
7. SSE client for `cos log --follow` is just line-by-line reading of the HTTP response body.
8. Build with: `go build -o cos ./cmd/cos/`
