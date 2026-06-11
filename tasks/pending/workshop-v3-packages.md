---
profile: medium
priority: normal
status: pending
agent: claude
created: "2026-06-11T06:11:00Z"
---

# Workshop v3: decision table, ledger, and backlog packages (plan tasks 1-4)

## Description
Implement Tasks 1 through 4 of the implementation plan at docs/plans/2026-06-10-workshop-v3-chores-before-dessert.md (read the spec at docs/specs/2026-06-10-workshop-v3-chores-before-dessert.md for context first). The plan contains complete code and TDD steps — follow them exactly, in order: Task 1 creates controller/creative/decide.go (session decision table), Task 2 creates controller/ledger (credit ledger, cap 3), Task 3 creates controller/backlog (octo-approved issue fetching), Task 4 adds controller/backlog/verify.go (GitHub artifact verification). Write each failing test first, run it, implement, run again, commit after each task with the commit messages given in the plan. Run go build ./... and go test ./... before finishing. Push to main when green (CI is the gate). Emit the v1 result contract with your commits as artifacts.
