### Accomplished

**Task 8 — main.go wiring (complete):**
- Added `controller/backlog` and `controller/ledger` imports to `controller/main.go`
- Added the chores-before-dessert wiring block after `NewWorkshop(...)`: constructs
  `ledger.New(filepath.Join(gitSyncer.LocalPath(), "state", "credits.json"), ...)` and
  `backlog.NewClient("dacort", "claude-os", githubToken)`, calls `workshop.EnableMaintenance`
  gated on `workshop != nil && githubToken != ""`
- Seeded `state/credits.json` with `{"credits": 0, "history": []}`
- All 14 controller test packages pass (`go build ./... && go test ./... && go vet ./...` all clean)
- Pushed to main as commit `a619026`

**Task 10 — docs (complete) + labels (blocked):**
- Created `CLAUDE.md` at repo root with Workshop v3 section (backlog, credits, SA, homelab PR rules)
- Pushed alongside Task 8 in the same commit

**Label creation blocked:**
- `gh label create octo-approved` and `gh label create "priority:high"` both return HTTP 403
- The GITHUB_TOKEN is a fine-grained PAT with `admin:true` repo permissions but lacks
  `issues:write` scope — label management requires that scope
- Labels do not yet exist in dacort/claude-os

### Tried and didn't work

- `gh label create` — HTTP 403, fine-grained PAT scope limitation
- `gh api --method POST /repos/dacort/claude-os/labels` — same 403

### Current state

Code is deployed (commit `a619026` on main). The feature is inert because:
1. No `octo-approved` label exists yet (blocked by token scope)
2. RBAC (Task 9 — talos-homelab PR) is not merged yet

The controller will log "workshop: maintenance mode enabled" on next pod restart
(if GITHUB_TOKEN is set), but `ApprovedIssues()` will return empty until the label
is created and applied to at least one issue.

### First thing next time

Create the two labels manually (dacort needs to do this, or a token with issues:write):

```bash
gh label create octo-approved --repo dacort/claude-os \
  --description "dacort-approved for autonomous maintenance work" --color 1D76DB

gh label create "priority:high" --repo dacort/claude-os \
  --description "worked before other approved issues" --color D93F0B
```

Then check if Task 9 (talos-homelab RBAC PR) has been merged by dacort.
