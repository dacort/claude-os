package backlog

import (
	"context"
	"fmt"
	"log/slog"
	"regexp"
	"strconv"

	"github.com/dacort/claude-os/controller/queue"
)

// artifactURLPattern matches github.com/{owner}/{repo}/(pull|issues)/{n}.
var artifactURLPattern = regexp.MustCompile(`github\.com/([^/]+)/([^/]+)/(pull|issues)/(\d+)`)

// VerifyArtifact reports whether an artifact meets a credit-worthy state
// (spec 2026-06-10, section 4):
//   - PR in the home repo (c.owner/c.repo): merged
//   - PR elsewhere (e.g. talos-homelab): open with all check runs green —
//     dacort merges those himself
//   - issue: closed
//
// Commits, files, and anything unparseable earn nothing. Verification
// failures are soft: false means "no credit", never an error surfaced up.
func (c *Client) VerifyArtifact(ctx context.Context, a queue.ResultArtifact) bool {
	m := artifactURLPattern.FindStringSubmatch(a.URL)
	if m == nil {
		return false
	}
	owner, repo, kind := m[1], m[2], m[3]
	num, _ := strconv.Atoi(m[4])

	switch kind {
	case "pull":
		return c.verifyPR(ctx, owner, repo, num)
	case "issues":
		var issue struct {
			State string `json:"state"`
		}
		url := fmt.Sprintf("%s/repos/%s/%s/issues/%d", c.baseURL, owner, repo, num)
		if err := c.getJSON(ctx, url, &issue); err != nil {
			slog.Warn("backlog: issue verification failed", "url", a.URL, "error", err)
			return false
		}
		return issue.State == "closed"
	}
	return false
}

func (c *Client) verifyPR(ctx context.Context, owner, repo string, num int) bool {
	var pr struct {
		Merged bool   `json:"merged"`
		State  string `json:"state"`
		Head   struct {
			SHA string `json:"sha"`
		} `json:"head"`
	}
	url := fmt.Sprintf("%s/repos/%s/%s/pulls/%d", c.baseURL, owner, repo, num)
	if err := c.getJSON(ctx, url, &pr); err != nil {
		slog.Warn("backlog: PR verification failed", "url", url, "error", err)
		return false
	}

	if owner == c.owner && repo == c.repo {
		// Home repo: CI-green auto-ship applies, so merged is the bar.
		return pr.Merged
	}

	// Foreign repo (talos-homelab): the octopus never merges; an open PR
	// with green checks is the deliverable.
	if pr.State != "open" {
		return pr.Merged // dacort may have merged it already — still counts
	}
	var checks struct {
		TotalCount int `json:"total_count"`
		CheckRuns  []struct {
			Status     string `json:"status"`
			Conclusion string `json:"conclusion"`
		} `json:"check_runs"`
	}
	url = fmt.Sprintf("%s/repos/%s/%s/commits/%s/check-runs", c.baseURL, owner, repo, pr.Head.SHA)
	if err := c.getJSON(ctx, url, &checks); err != nil {
		slog.Warn("backlog: check-run verification failed", "url", url, "error", err)
		return false
	}
	if checks.TotalCount == 0 {
		return false
	}
	for _, run := range checks.CheckRuns {
		if run.Status != "completed" || run.Conclusion != "success" {
			return false
		}
	}
	return true
}
