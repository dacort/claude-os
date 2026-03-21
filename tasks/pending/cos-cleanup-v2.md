---
profile: small
priority: normal
status: pending
agent: claude
target_repo: dacort/claude-os
created: "2026-03-21T04:11:39Z"
---

# Move cos CLI out of controller/ and add .gitignore for binaries

## Description

Two cleanup items:

1. **Move `controller/cmd/cos/main.go` to `cmd/cos/main.go`** — the cos CLI is a separate binary, not part of the controller module. It should live at the repo root as its own Go module (or at minimum its own `cmd/` directory). Update any import paths if needed. Make sure `go build ./cmd/cos/` works from the repo root.

2. **Add a `.gitignore`** at the repo root to ignore compiled Go binaries. At minimum ignore `/cos` and `/cmd/cos/cos` so the built binary never gets committed.

Keep it simple — just the move + gitignore. Don't restructure anything else.
