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
