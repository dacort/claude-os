---
profile: small
agent: claude
priority: normal
status: scheduled
schedule: "0 */6 * * *"
max_concurrent: 1
created: "2026-03-16T00:00:00Z"
---

# OctoClaude Status Page

Generate the OctoClaude status page by analyzing completed and failed tasks.

## Description

Generate and deploy the OctoClaude status page using `projects/status-page.py`.

### Step 1: Update workshop summary cache

Before running the script, check `knowledge/workshop-summaries.json` for any workshop tasks
not yet in the cache:

1. Load `knowledge/workshop-summaries.json` (the cache). If it doesn't exist, treat it as empty.
2. Collect all `workshop-*` task IDs from both `tasks/completed/` and `tasks/failed/`.
3. For any task ID **not** in the cache:
   - Read the task file (Worker Logs and Summary sections).
   - Write a one-line summary (10–20 words) capturing the creative spirit — what was explored, built, or discovered.
     For failed sessions (credit/token errors), use a brief note like "Session ended early due to rate limiting".
   - Add the new `"task-id": "summary"` entry to the JSON cache.
4. If the cache was updated, commit the changes to main before proceeding.

### Step 2: Generate and deploy

```bash
python3 projects/status-page.py --deploy
```

The script parses all task files, reads the workshop cache, generates a self-contained HTML
status page, and pushes it to the `gh-pages` branch.

### Constraints

- NO secrets, tokens, or sensitive info in output
- Workshop summaries must be abstract/high-level only
- HTML must be fully self-contained (no external CDN)
