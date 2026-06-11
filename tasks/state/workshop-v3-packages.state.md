### Accomplished

Tasks 1-4 of the chores-before-dessert plan implemented and pushed to main:

- **Task 1** (`controller/creative/decide.go`): Session decision table — already committed by a prior instance (commit `166a713`). Tests pass.
- **Task 2** (`controller/ledger/ledger.go`): Git-backed credit ledger with cap 3, earn/spend/persist semantics. 5 tests pass. Committed `100ebd1`.
- **Task 3** (`controller/backlog/backlog.go`, `backlog_test.go`): GitHub client fetching `octo-approved` issues, with priority:high / oldest-first sorting, PR filtering. 2 tests pass. Committed `130a9a6`.
- **Task 4** (`controller/backlog/verify.go`, `verify_test.go`): Artifact verification — merged home-repo PRs, open foreign-repo PRs with green CI, closed issues all earn credit; commits/files/garbage URLs earn nothing. 7 tests pass. Committed `3e8d188`.

Full `go build ./...` and `go test ./...` green across all 14 packages before pushing.

### Tried and didn't work

Nothing failed. Task 1 was pre-committed; the test file for Task 2 (ledger_test.go) was also already there. Only the implementation files needed writing.

### Current state

All 4 tasks done, committed, pushed to main. CI gate pending — `3e8d188` is on main.

Tasks 5-10 remain (per-task SA override, maintenance sessions in Workshop, credit granting, main.go wiring, RBAC, docs).

### First thing next time

Check CI status for `3e8d188` first (`gh run list --branch main --limit 5`). If green, move to Task 5: add `ServiceAccount string` field to `controller/queue/queue.go` Task struct and implement the dispatcher override in `controller/dispatcher/dispatcher.go`.
