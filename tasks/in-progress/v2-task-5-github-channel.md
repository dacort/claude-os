---
profile: small
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
depends_on:
  - v2-task-4-comms-interface
created: "2026-03-20T17:35:00Z"
---

# v2 Task 5: GitHubChannel implementation

## Description

Add GitHubChannel to the comms package — opens/polls/closes GitHub Issues for async communication.

### New File

**`controller/comms/github.go`** — GitHubChannel using net/http to GitHub REST API:

- `Notify`: creates a GitHub Issue with labels (needs-human, project:<name>). Dedup via HTML comment marker `<!-- claude-os-task-id:X -->` in body. Searches for existing open issue before creating.
- `Poll`: lists issues with `needs-human` label, checks for closed issues or owner comments, returns as resolved Responses.
- `Close`: finds and closes the issue by number.
- Helper `formatIssueBody(msg)`: formats body with project, task ID, mentions, and hidden task-id marker.
- Helper `extractTaskID(body)`: extracts task ID from HTML comment marker.

### Tests

Add to `controller/comms/comms_test.go`:
- `TestFormatIssueBody` — verify body contains project, task ID, @mention, and HTML marker
- `TestExtractTaskID` — verify extraction from body with marker
- `TestExtractTaskID_Missing` — verify empty string when no marker

### TDD
- Write tests first, implement, verify
- Commit: `feat: GitHubChannel for async comms via GitHub Issues`
