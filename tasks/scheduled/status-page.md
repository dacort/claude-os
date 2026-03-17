---
profile: small
priority: normal
status: scheduled
schedule: "0 */6 * * *"
max_concurrent: 1
created: "2026-03-16T00:00:00Z"
---

# OctoClaude Status Page

Generate the OctoClaude status page by analyzing completed and failed tasks.

## Description

Build and publish a self-contained status page for the Claude OS system.

### Data gathering

- Parse all files in tasks/completed/ and tasks/failed/ (YAML frontmatter)
- Extract: task ID, title, agent, model, profile, priority, created timestamp, completion timestamp, status, duration
- Identify workshop sessions (task IDs starting with "workshop-")
- Summarize workshop activity (high-level, no secrets)

### Workshop Diary — cached summaries

Workshop session summaries are stored in `knowledge/workshop-summaries.json`. Use this cache
to avoid re-reading every session file on each run.

**At the start of each run:**
1. Load `knowledge/workshop-summaries.json` (the cache). If it doesn't exist, treat it as empty.
2. Collect all `workshop-*` task IDs from both `tasks/completed/` and `tasks/failed/`.
3. For any task ID **not** in the cache:
   - Read the task file (Worker Logs and Summary sections).
   - Write a one-line summary (10–20 words) capturing the creative spirit — what was explored, built, or discovered.
     For failed sessions (credit/token errors), use a brief note like "Session ended early due to rate limiting".
   - Append the new `"task-id": "summary"` entry to the JSON cache file.
   - Commit the updated cache to main before generating the HTML.
4. When generating the Workshop Diary section of the status page, use **cached summaries only** — do not
   re-read task files for sessions already in the cache.

**Workshop Diary display rules:**
- Group by calendar day, most recent day first.
- Show only the last 7 days of workshop activity.
- Display each session as: time (HH:MM UTC) + one-line summary.
- Do not display raw YAML frontmatter.

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
