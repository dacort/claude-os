---
profile: medium
priority: normal
status: pending
agent: claude
depends_on: [workshop-v3-packages]
created: "2026-06-11T06:11:00Z"
---

# Workshop v3: dispatcher SA override, maintenance sessions, credit granting (plan tasks 5-7)

## Description
Implement Tasks 5 through 7 of docs/plans/2026-06-10-workshop-v3-chores-before-dessert.md. This depends on the packages from plan tasks 1-4 being merged (task workshop-v3-packages). Task 5 adds a per-task ServiceAccount override to queue.Task and the dispatcher job spec. Task 6 creates controller/creative/maintenance.go and wires the decision table into Workshop.CheckIdle via startSession, with the EnableMaintenance setter so nil dependencies preserve v2 behavior. Task 7 changes OnJobFinished to accept the parsed TaskResult, grants at most one credit per verified maintenance session, and reorders the watcher callback in main.go so result parsing happens before the workshop notification — grep for all OnJobFinished call sites including tests and update them. Follow the plan's TDD steps exactly, commit per task, run go build ./... and go test ./... and go vet ./... before pushing to main.
