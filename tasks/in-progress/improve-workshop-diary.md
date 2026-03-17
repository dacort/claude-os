---
profile: small
priority: normal
status: pending
target_repo: dacort/claude-os
created: "2026-03-17T00:44:39Z"
---

# Improve Workshop Diary with Cached Summaries

## Description

The OctoClaude status page (https://dacort.github.io/claude-os/) workshop diary section currently just scrapes raw YAML frontmatter, which isn't readable or interesting. We need engaging one-line summaries of what each workshop session explored/built.

### What to build

**1. Create the summary cache file: `knowledge/workshop-summaries.json`**

```json
{
  "workshop-20260315-164128": "Built a field guide for future workshop sessions, documenting creative tools and patterns",
  "workshop-20260314-193745": "Explored code citation patterns and wrote a poetry generator inspired by git commits"
}
```

**2. Seed the cache with ALL existing workshop sessions**

Read each `tasks/completed/workshop-*.md` file. Look at the Worker Logs and Summary sections to understand what the session actually did. Write a one-line engaging summary (10-20 words) that captures the creative spirit — what was explored, built, or discovered. Do this for every workshop session. Commit the seeded cache.

For failed workshop sessions in `tasks/failed/workshop-*.md`, include them too with a brief note (e.g., "Session ended early due to rate limiting").

**3. Update `tasks/scheduled/status-page.md`**

Add instructions to the scheduled task description telling the worker to:

- Read `knowledge/workshop-summaries.json` at the start of each run
- Check for any `workshop-*` tasks in completed/failed that aren't in the cache
- For new unsummarized sessions only: read the task file, write a one-line summary, append to the JSON cache, and commit it
- Use the cached summaries (not raw frontmatter) when generating the Workshop Diary section of the status page
- Display summaries grouped by day, most recent first, last 7 days only

### Example good summaries

- "Built a field guide documenting creative tools and workshop patterns"
- "Created a homelab pulse monitor with ASCII art status display"  
- "Explored the concept of agent memory through letters between sessions"
- "Designed a weekly digest generator to summarize system activity"

### Constraints

- Summaries must be high-level — NO secrets, tokens, API details, or sensitive implementation specifics
- Keep each summary to one line, 10-20 words
- Capture the creative/exploratory spirit of the workshop
- The JSON file lives in `knowledge/` so it persists in git across runs
- Only the FIRST run (seeding) will be expensive — subsequent runs only summarize 1-2 new sessions
