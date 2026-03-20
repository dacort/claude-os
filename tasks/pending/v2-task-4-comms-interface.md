---
profile: small
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
created: "2026-03-20T17:35:00Z"
---

# v2 Task 4: Comms channel interface and FileChannel

## Description

Create the `controller/comms/` package with the generic Channel interface and FileChannel implementation.

### New Files

**`controller/comms/channel.go`** — Interface and fan-out manager:

```go
package comms

type MessageType string
const (
    NeedsHuman     MessageType = "needs-human"
    ProjectUpdate  MessageType = "project-update"
    DecisionNeeded MessageType = "decision-needed"
)

type Channel interface {
    Notify(ctx context.Context, msg Message) error
    Poll(ctx context.Context) ([]Response, error)
    Close(ctx context.Context, id string) error
}

type Message struct {
    ID, Title, Body, Project, TaskID string
    Type     MessageType
    Mentions []string
}

type Response struct {
    MessageID, Author, Body string
    Resolved bool
}
```

Plus a `Manager` struct that fans out Notify to all channels and merges Poll responses.

**`controller/comms/file.go`** — FileChannel that writes blocked task files to a directory:
- `Notify` writes `tasks/blocked/<task-id>.md` with YAML frontmatter (type, task_id, project, created)
- Dedup: skip if file already exists
- `Poll` returns nil (file channel is write-only for now)
- `Close` deletes the file

**`controller/comms/comms_test.go`** — Tests:
- `TestFileChannel_Notify` — write a blocked file, verify it exists with correct content
- `TestFileChannel_Dedup` — notify twice, verify only one file created

### TDD
- Write tests first, run to fail, implement, run to pass
- Commit: `feat: comms channel interface with FileChannel implementation`
