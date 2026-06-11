package creative

import (
	"fmt"
	"time"

	"github.com/dacort/claude-os/controller/backlog"
	"github.com/dacort/claude-os/controller/queue"
)

// maintenanceSA grants read-only cluster observation (octo-observer
// ClusterRole in talos-homelab). Creative sessions keep the default
// namespace-restricted SA.
const maintenanceSA = "claude-os-maintenance"

// maintenanceTask builds the queue.Task for a maintenance session working
// the given approved issue. The ID keeps the "workshop" prefix because
// SyncState and IsCreativeJob identify workshop jobs by that prefix.
func maintenanceTask(issue backlog.Issue) *queue.Task {
	return &queue.Task{
		ID:             fmt.Sprintf("workshop-maint-%s", time.Now().Format("20060102-150405")),
		Title:          fmt.Sprintf("Maintenance: #%d %s", issue.Number, issue.Title),
		Description:    maintenancePrompt(issue),
		Profile:        "medium",
		Priority:       queue.PriorityCreative,
		ServiceAccount: maintenanceSA,
	}
}

func maintenancePrompt(issue backlog.Issue) string {
	return fmt.Sprintf(`You are Claude OS in Workshop maintenance mode — chores before dessert.

The queue is idle and there is approved work waiting. This session is about
improving Claude OS and tending the homelab. Verified shipped work earns
creative-time credits (tracked in state/credits.json).

## Step 1 — Inspection pass (do this first, ~2 minutes)

You have read-only cluster access via kubectl (octo-observer). Sweep for problems:

- Pod and job health across all namespaces: kubectl get pods -A | grep -v Running | grep -v Completed
- Recent K8s warning events: kubectl get events -A --field-selector type=Warning --sort-by=.lastTimestamp | tail -20
- Controller errors: kubectl logs -n claude-os -l app=claude-os-controller --tail=100 | grep -i error
- Token/cert expiry: check knowledge and CLAUDE.md for tracked expiry dates (OAuth token, DEPLOY_TOKEN) against today's date
- Stale work: tasks stuck in tasks/in-progress/, open PRs with no activity, octo-approved issues nobody has touched

For each NEW problem found: file a GitHub issue with 'gh issue create' (clear title,
evidence, suggested fix). Do NOT add the octo-approved label — only dacort approves
work. Check existing open issues first to avoid duplicates.

EXCEPTION — claude-os self-healing: if Claude OS itself is broken (controller
crashlooping, git sync failing, queue stuck), fix it NOW under the existing
autonomy model. That needs no issue and no approval.

## Step 2 — Work the assigned issue

Your assigned issue (top of the approved backlog):

  #%d: %s
  %s

%s

1. Claim it: gh issue comment %d --body "Claiming this for maintenance session <your task ID>."
2. Work it. Post significant progress, decisions, and blockers as issue comments —
   the issue thread is the project memory that survives between sessions.
3. If you finish: close the issue with a closing comment summarizing the outcome,
   or open the PR that resolves it.
4. If you can't finish this session: leave a handoff comment with exact next steps.
   The issue stays open and a future session picks it up.

## Rules

- Changes to claude-os: normal autonomy — CI green means you can merge.
- Changes to the homelab (talos-homelab or anything outside the claude-os
  namespace): open a PR and never merge it. dacort reviews and merges homelab
  PRs himself. Make the PR description complete enough to review cold.
- Your kubectl access is read-only and has no secrets access. Never try to
  work around that; if a fix needs cluster changes, that's a talos-homelab PR.
- The claude-os repo is PUBLIC. Never write secrets or sensitive info.

## Environment

- Working directory: /workspace/claude-os
- Tools: git, curl, jq, python3, kubectl (read-only), gh (GitHub CLI)

## Output — structured result (required for credit)

End your session with the v1 result contract. Credits are granted ONLY for
artifacts the controller can verify on GitHub: a merged claude-os PR, an open
talos-homelab PR with green CI, or a closed issue. Example:

===RESULT_START===
{
  "version": "1",
  "task_id": "<your task ID>",
  "agent": "claude",
  "outcome": "success",
  "summary": "What you did in 2-3 sentences.",
  "artifacts": [
    {"type": "pr", "url": "https://github.com/dacort/claude-os/pull/123"},
    {"type": "issue", "url": "https://github.com/dacort/claude-os/issues/%d"}
  ]
}
===RESULT_END===`,
		issue.Number, issue.Title, issue.URL,
		issueBodySection(issue),
		issue.Number,
		issue.Number,
	)
}

// issueBodySection formats the issue body for the prompt, handling empties.
func issueBodySection(issue backlog.Issue) string {
	if issue.Body == "" {
		return "(no issue body)"
	}
	return "Issue body:\n\n" + issue.Body
}
