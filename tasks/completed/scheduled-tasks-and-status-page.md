---
profile: medium
priority: normal
status: completed
target_repo: dacort/claude-os
created: "2026-03-16T20:53:56Z"
---

# Implement Scheduled Tasks & OctoClaude Status Page

## Description

Implement two features designed together: a cron-based scheduled task system for the controller, and a status page as its first customer.

### Full spec

The complete spec is in the backchannel repo at `docs/specs/2026-03-16-recurring-tasks-and-status-page.md` in `dacort/my-octopus-teacher`. Since you may not have access to that repo, here is the full implementation plan:

### Part 1: Scheduled Tasks (Controller Changes)

**Overview:** Add a scheduler package to the controller that re-enqueues tasks on a cron schedule.

**Task file format:** Scheduled tasks live in `tasks/scheduled/` with a `schedule` field in frontmatter:

```yaml
---
profile: small
priority: normal
status: scheduled
schedule: "0 9 * * *"          # standard 5-field cron expression (UTC)
max_concurrent: 1              # don't stack if previous run is still going
created: "2026-03-16T00:00:00Z"
---
```

**New package: `controller/scheduler/scheduler.go`**

- Cron expression parsing via `github.com/robfig/cron/v3`
- Redis state per scheduled task:
  - `claude-os:scheduled:<task-id>:next_run` — Unix timestamp
  - `claude-os:scheduled:<task-id>:last_run` — Unix timestamp  
  - `claude-os:scheduled:<task-id>:running` — bool (prevents stacking)
- Tick loop (every 60s): check `now >= next_run && !running`, enqueue a copy if ready
- Spawned task IDs: `<base-id>-<YYYYMMDD-HHMMSS>` to keep them unique
- No backfill on missed runs — just calculate next future run time
- Governance integration: scheduled tasks respect token budgets (skip run if budget exhausted)

**Git sync changes:**
- Extend `SyncOnce()` to scan `tasks/scheduled/` directory
- Parse scheduled task files (same parser, new directory)
- Register/deregister tasks with the scheduler (idempotent)
- If a scheduled task file is deleted from git, deregister it

**Watcher changes:**
- On task completion, notify scheduler to clear `running` flag
- Map spawned task ID back to parent scheduled task (strip timestamp suffix)
- Calculate and set next `next_run`

**Wire into main.go:**
- Start scheduler tick loop as a new goroutine alongside existing loops
- Pass scheduler reference to watcher for completion callbacks

**Tests required:**
- Cron expression parsing and next-run calculation
- Skip-if-running logic
- Governance blocking behavior
- Registration/deregistration lifecycle
- Spawned task ID generation and parent mapping
- Completion callback and next-run recalculation

### Part 2: Status Page (First Scheduled Task)

**After the scheduler is working**, create `tasks/scheduled/status-page.md`:

```yaml
---
profile: small
priority: normal
status: scheduled
schedule: "0 */6 * * *"
max_concurrent: 1
created: "2026-03-16T00:00:00Z"
---

# OctoClaude Status Page

## Description
Generate the OctoClaude status page by analyzing completed and failed tasks.

### Data gathering
- Parse all files in tasks/completed/ and tasks/failed/ (YAML frontmatter)
- Extract: task ID, title, agent, model, profile, priority, created timestamp, completion timestamp, status, duration
- Identify workshop sessions (task IDs starting with "workshop-")
- Summarize workshop activity (high-level, no secrets)

### Output
- Generate a single index.html with inline CSS and JS
- Sections: system vitals, usage charts (last 14 days by agent/model/type), recent activity, workshop diary
- Octopus-themed, dark mode, self-contained (no external CDN)
- Commit to the gh-pages branch of dacort/claude-os
- Set up gh-pages branch if it doesn't exist

### Design guidelines
- Fun octopus personality (ASCII art or SVG)
- "Current mood" based on recent activity
- Task streak counter
- Mobile-friendly
- Keep it lightweight and charming

### Constraints
- NO secrets, tokens, or sensitive info
- Workshop summaries must be abstract/high-level only
- HTML must be fully self-contained
```

### Implementation order

1. Scheduler package with tests
2. Git sync integration for `tasks/scheduled/`
3. Watcher integration (completion callbacks)
4. Wire into main.go, deploy
5. Create status-page.md scheduled task
6. Set up gh-pages branch, verify first run
7. Enable GitHub Pages on dacort/claude-os

### Key decisions
- Host status page on `dacort/claude-os` gh-pages (already public)
- 14-day historical window for usage charts
- No live API endpoint needed — git-derived data is sufficient
- Use `robfig/cron/v3` for cron parsing (MIT, battle-tested)

### Important constraints
- This repo is PUBLIC — never commit secrets
- Tests must pass before merging (CI is the approval gate)
- The scheduled task directory `tasks/scheduled/` is new — create it
