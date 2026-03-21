# cos CLI — UX Design

*Design document for the `cos` terminal interface to Claude OS.*
*Downstream consumers: cos-server (Go endpoints) and cos-client (Go CLI binary).*

---

## Principles

1. **Start lean.** Ship `status` first. Add `log` and `run` when status works end-to-end.
2. **Default to human-readable.** Pretty terminal output with ANSI colors. `--json` flag on every subcommand for machine-readable output.
3. **No config files.** Single env var `CONTROLLER_URL` (default: `http://localhost:8080`). Port-forward or ingress handles the rest.
4. **Fail clearly.** Connection errors, auth failures, and empty states all get one-line messages, not stack traces.

---

## Commands

### `cos status`

The primary command. Shows a snapshot of the system right now.

```
$ cos status

  Claude OS                              controller v0.4.0
  ─────────────────────────────────────────────────────────

  Queue        2 pending · 1 running · 0 blocked
  Tokens       42,180 / 200,000 today (21%)
  Agents       claude: ok · codex: rate-limited (38m remaining)

  Running
  ┌──────────────────────┬──────────┬─────────┬──────────┐
  │ Task                 │ Agent    │ Profile │ Duration │
  ├──────────────────────┼──────────┼─────────┼──────────┤
  │ cos-server           │ claude   │ medium  │ 4m 12s   │
  └──────────────────────┴──────────┴─────────┴──────────┘

  Pending
  ┌──────────────────────┬──────────┬──────────┬──────────┐
  │ Task                 │ Priority │ Profile  │ Waiting  │
  ├──────────────────────┼──────────┼──────────┼──────────┤
  │ cos-client           │ normal   │ medium   │ 4m 12s   │
  │ update-docs          │ creative │ small    │ 22m      │
  └──────────────────────┴──────────┴──────────┴──────────┘

  Recent (last 5)
  ┌──────────────────────┬─────────┬──────────┬──────────┐
  │ Task                 │ Outcome │ Duration │ Finished │
  ├──────────────────────┼─────────┼──────────┼──────────┤
  │ cos-design           │ success │ 2m 30s   │ 3m ago   │
  │ fix-vitals-bug       │ success │ 1m 45s   │ 1h ago   │
  │ deploy-dashboard     │ failed  │ 8m 02s   │ 2h ago   │
  └──────────────────────┴─────────┴──────────┴──────────┘
```

**Sections:**
- **Header**: Controller version and system name.
- **Summary line**: Queue depth by status + token budget usage + agent health.
- **Running**: Currently executing tasks with elapsed time.
- **Pending**: Queued tasks in priority order.
- **Recent**: Last N completed/failed tasks (default 5, configurable via `--recent N`).

**Flags:**
- `--json` — output the full status response as JSON.
- `--recent N` — how many recent tasks to show (default 5, max 50).
- `--watch` — re-poll every 5 seconds and redraw (stretch goal, not v1).

**Empty states:**
```
$ cos status

  Claude OS                              controller v0.4.0
  ─────────────────────────────────────────────────────────

  Queue        empty
  Tokens       0 / 200,000 today (0%)
  Agents       claude: ok · codex: ok

  No running tasks. No recent activity.
```

**Error states:**
```
$ cos status
  error: cannot reach controller at http://localhost:8080 (connection refused)
  hint: is the controller running? try: kubectl port-forward svc/controller 8080:8080 -n claude-os
```

---

### `cos log <task-id>`

Stream or fetch logs for a task. Uses Server-Sent Events for running tasks, returns full logs for completed ones.

```
$ cos log cos-server
  cos-server (running · 4m 12s)
  ─────────────────────────────
  [2026-03-21 14:02:33] Cloning github.com/dacort/claude-os...
  [2026-03-21 14:02:35] Reading protocol spec...
  [2026-03-21 14:03:01] Implementing /api/v1/status endpoint...
  ...
  (streaming — ctrl-c to stop)
```

For completed tasks:
```
$ cos log cos-design
  cos-design (completed · 2m 30s · success)
  ──────────────────────────────────────────
  [2026-03-21 13:58:01] Starting task...
  ...
  [2026-03-21 14:00:31] Done.

  Result: success
  Summary: Designed cos CLI UX and HTTP protocol spec.
  Artifacts: knowledge/plans/cos-cli-20260321/ux-design.md, protocol.md
```

**Flags:**
- `--json` — output log lines as JSON (one object per line, NDJSON).
- `--tail N` — show only the last N lines (default: all for completed, stream for running).
- `--no-follow` — for running tasks, fetch current snapshot instead of streaming.

**Error states:**
```
$ cos log nonexistent-task
  error: task "nonexistent-task" not found
```

---

### `cos run <title> [flags]`

File a new task. Intentionally minimal — most tasks should still come through git, but this is useful for quick one-offs.

```
$ cos run "Fix the broken vitals test" --repo github.com/dacort/claude-os --profile small
  Created task: fix-the-broken-vitals-test-a1b2
  Status: pending (position 3 in queue)
```

**Flags:**
- `--repo` — target repository (required).
- `--profile` — resource profile: small, medium, large, burst (default: small).
- `--priority` — normal, high, creative (default: normal).
- `--agent` — force a specific agent: claude, codex, gemini.
- `--description` or `-d` — task description (if omitted, title is used as description).
- `--json` — output created task as JSON.

**Validation:**
- Title is required (positional arg).
- `--repo` is required.
- Invalid profile/priority/agent values are rejected with a helpful message listing valid options.

---

### `cos task <task-id>`

Show detailed info for a single task.

```
$ cos task cos-design

  cos-design
  ──────────
  Status:      completed (success)
  Profile:     small (claude-opus-4-6)
  Agent:       claude
  Plan:        cos-cli-20260321 (1/3 complete)
  Created:     2026-03-21 13:57:30 UTC
  Started:     2026-03-21 13:58:01 UTC
  Finished:    2026-03-21 14:00:31 UTC
  Duration:    2m 30s
  Tokens:      15,200 in / 4,800 out

  Artifacts
  - file: knowledge/plans/cos-cli-20260321/ux-design.md
  - file: knowledge/plans/cos-cli-20260321/protocol.md

  Summary
  Designed cos CLI UX and HTTP protocol spec.
```

**Flags:**
- `--json` — output full task object as JSON.

---

## Session Model

There is no session. `cos` is stateless. Every invocation is a single HTTP request (or SSE stream for `cos log`). No login, no tokens, no cookies.

Authentication is deferred to v2. For v1, the controller is only reachable via `kubectl port-forward` or cluster-internal networking, which provides implicit auth. When auth is needed later, a simple bearer token via `CONTROLLER_TOKEN` env var is the likely path.

---

## Output Conventions

| Concern | Convention |
|---------|-----------|
| Colors | Green = success/ok, Red = failed/error, Yellow = pending/warning, Cyan = running, Dim = metadata |
| Time | Relative for <24h ("3m ago"), absolute for older ("2026-03-20 09:15 UTC") |
| Duration | Human-friendly: "2m 30s", "1h 12m", "45s" |
| Numbers | Comma-separated thousands: "42,180" |
| Tables | Box-drawing characters. No table for 0 rows — use a prose empty-state message |
| Truncation | Task titles truncated to 40 chars with "..." in tables. Full title in `cos task` |
| `--json` | Compact JSON to stdout. No ANSI. No decoration. Pipe-friendly |
| Errors | "error: " prefix to stderr. Optional "hint: " line below with actionable advice |
| Exit codes | 0 = success, 1 = user error (bad args), 2 = connection/server error |

---

## Command Summary

| Command | Purpose | HTTP Method | Endpoint |
|---------|---------|-------------|----------|
| `cos status` | System snapshot | GET | `/api/v1/status` |
| `cos log <id>` | Task logs | GET | `/api/v1/tasks/{id}/logs` |
| `cos run <title>` | Create task | POST | `/api/v1/tasks` |
| `cos task <id>` | Task detail | GET | `/api/v1/tasks/{id}` |

---

## What's NOT in v1

- **`cos cancel <id>`** — kill a running task. Useful but needs careful design around plan dependencies.
- **`cos plan`** — show plan progress. Can be inferred from `cos task` for now.
- **`cos watch`** — TUI dashboard. The `--watch` flag on status is sufficient.
- **Auth** — deferred until the controller is exposed outside the cluster.
- **Shell completion** — nice-to-have, not blocking.
