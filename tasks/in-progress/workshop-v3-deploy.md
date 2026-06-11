---
profile: medium
priority: normal
status: pending
agent: claude
depends_on: [workshop-v3-wiring]
created: "2026-06-11T06:11:00Z"
---

# Workshop v3: main.go wiring, seed state, labels, docs (plan tasks 8 and 10)

## Description
Implement Task 8 and Task 10 of docs/plans/2026-06-10-workshop-v3-chores-before-dessert.md. Task 8: construct the ledger (state/credits.json via gitSyncer.LocalPath and CommitAndPush) and backlog client in controller/main.go, call workshop.EnableMaintenance gated on GITHUB_TOKEN, seed state/credits.json with zero credits, build and test everything, push to main — CI deploys it. The feature is inert until an issue carries the octo-approved label, so deploying first is safe. Task 10: create the octo-approved and priority:high labels with gh label create as specified in the plan, and add the Workshop v3 section to CLAUDE.md in this repo using the text from plan Task 10 Step 1. Do NOT apply the octo-approved label to any issue — only dacort approves work. Emit the v1 result contract listing your PR or commits as artifacts.
