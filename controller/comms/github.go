package comms

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"time"
)

const taskIDMarkerFmt = "<!-- claude-os-task-id:%s -->"

var taskIDPattern = regexp.MustCompile(`<!-- claude-os-task-id:(.+?) -->`)

// GitHubChannel opens/polls/closes GitHub Issues for async communication with
// humans. Each Notify call creates one Issue; Poll detects owner replies or
// closures; Close closes the issue.
type GitHubChannel struct {
	owner   string
	repo    string
	token   string
	baseURL string
	client  *http.Client
}

// NewGitHubChannel creates a GitHubChannel for owner/repo authenticated with
// token (a GitHub PAT with issues:write scope).
func NewGitHubChannel(owner, repo, token string) *GitHubChannel {
	return &GitHubChannel{
		owner:   owner,
		repo:    repo,
		token:   token,
		baseURL: "https://api.github.com",
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

// formatIssueBody builds the GitHub Issue body for msg, embedding a hidden
// HTML comment marker so the issue can later be matched back to its task ID.
func formatIssueBody(msg Message) string {
	var sb strings.Builder

	sb.WriteString(fmt.Sprintf("**Project:** %s\n", msg.Project))
	sb.WriteString(fmt.Sprintf("**Task ID:** %s\n", msg.TaskID))

	if len(msg.Mentions) > 0 {
		mentions := make([]string, len(msg.Mentions))
		for i, m := range msg.Mentions {
			mentions[i] = "@" + strings.TrimPrefix(m, "@")
		}
		sb.WriteString(fmt.Sprintf("**CC:** %s\n", strings.Join(mentions, " ")))
	}

	sb.WriteString("\n")
	sb.WriteString(msg.Body)
	sb.WriteString("\n\n")
	sb.WriteString(fmt.Sprintf(taskIDMarkerFmt, msg.TaskID))

	return sb.String()
}

// extractTaskID parses the hidden HTML comment marker from an issue body and
// returns the embedded task ID. Returns "" if no marker is found.
func extractTaskID(body string) string {
	m := taskIDPattern.FindStringSubmatch(body)
	if m == nil {
		return ""
	}
	return strings.TrimSpace(m[1])
}

// Notify creates a GitHub Issue for msg with labels "needs-human" and
// "project:<name>". If an open issue for this task ID already exists the call
// is a no-op (dedup via hidden HTML comment marker).
func (g *GitHubChannel) Notify(ctx context.Context, msg Message) error {
	existing, err := g.findOpenIssue(ctx, msg.TaskID)
	if err != nil {
		return fmt.Errorf("comms/github: check existing: %w", err)
	}
	if existing != 0 {
		return nil // already open
	}

	payload := map[string]interface{}{
		"title":  msg.Title,
		"body":   formatIssueBody(msg),
		"labels": []string{string(msg.Type), "project:" + msg.Project},
	}

	if _, err := g.apiPost(ctx, fmt.Sprintf("/repos/%s/%s/issues", g.owner, g.repo), payload); err != nil {
		return fmt.Errorf("comms/github: create issue: %w", err)
	}
	return nil
}

// Poll lists issues with the needs-human label and returns resolved Responses
// for issues that have been closed or that have a comment from the repo owner.
func (g *GitHubChannel) Poll(ctx context.Context) ([]Response, error) {
	path := fmt.Sprintf("/repos/%s/%s/issues?labels=needs-human&state=all&per_page=50", g.owner, g.repo)
	data, err := g.apiGet(ctx, path)
	if err != nil {
		return nil, fmt.Errorf("comms/github: list issues: %w", err)
	}

	var issues []githubIssue
	if err := json.Unmarshal(data, &issues); err != nil {
		return nil, fmt.Errorf("comms/github: parse issues: %w", err)
	}

	var responses []Response
	for _, issue := range issues {
		taskID := extractTaskID(issue.Body)
		if taskID == "" {
			continue
		}

		// Closed issue — the human resolved it.
		if issue.State == "closed" {
			responses = append(responses, Response{
				MessageID: taskID,
				Author:    issue.ClosedBy.Login,
				Body:      "(issue closed)",
				Resolved:  true,
			})
			continue
		}

		// Open issue — check for a comment from the repo owner.
		comments, err := g.listComments(ctx, issue.Number)
		if err != nil {
			return nil, fmt.Errorf("comms/github: list comments for #%d: %w", issue.Number, err)
		}
		for _, c := range comments {
			if c.User.Login == g.owner {
				responses = append(responses, Response{
					MessageID: taskID,
					Author:    c.User.Login,
					Body:      c.Body,
					Resolved:  true,
				})
				break
			}
		}
	}

	return responses, nil
}

// Close finds the open GitHub Issue for id and closes it.
// Returns nil if no matching issue is found (idempotent).
func (g *GitHubChannel) Close(ctx context.Context, id string) error {
	number, err := g.findOpenIssue(ctx, id)
	if err != nil {
		return fmt.Errorf("comms/github: find issue: %w", err)
	}
	if number == 0 {
		return nil // nothing to close
	}

	patch := map[string]string{"state": "closed"}
	if _, err := g.apiPatch(ctx, fmt.Sprintf("/repos/%s/%s/issues/%d", g.owner, g.repo, number), patch); err != nil {
		return fmt.Errorf("comms/github: close issue #%d: %w", number, err)
	}
	return nil
}

// findOpenIssue searches open issues with the needs-human label for one that
// embeds taskID in the hidden comment marker. Returns issue number or 0.
func (g *GitHubChannel) findOpenIssue(ctx context.Context, taskID string) (int, error) {
	path := fmt.Sprintf("/repos/%s/%s/issues?labels=needs-human&state=open&per_page=100", g.owner, g.repo)
	data, err := g.apiGet(ctx, path)
	if err != nil {
		return 0, err
	}

	var issues []githubIssue
	if err := json.Unmarshal(data, &issues); err != nil {
		return 0, err
	}

	for _, issue := range issues {
		if extractTaskID(issue.Body) == taskID {
			return issue.Number, nil
		}
	}
	return 0, nil
}

// listComments fetches all comments for the given issue number.
func (g *GitHubChannel) listComments(ctx context.Context, number int) ([]githubComment, error) {
	path := fmt.Sprintf("/repos/%s/%s/issues/%d/comments", g.owner, g.repo, number)
	data, err := g.apiGet(ctx, path)
	if err != nil {
		return nil, err
	}

	var comments []githubComment
	if err := json.Unmarshal(data, &comments); err != nil {
		return nil, err
	}
	return comments, nil
}

// --- HTTP helpers ---

func (g *GitHubChannel) apiGet(ctx context.Context, path string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, g.baseURL+path, nil)
	if err != nil {
		return nil, err
	}
	return g.doRequest(req)
}

func (g *GitHubChannel) apiPost(ctx context.Context, path string, body interface{}) ([]byte, error) {
	return g.apiRequestWithBody(ctx, http.MethodPost, path, body)
}

func (g *GitHubChannel) apiPatch(ctx context.Context, path string, body interface{}) ([]byte, error) {
	return g.apiRequestWithBody(ctx, http.MethodPatch, path, body)
}

func (g *GitHubChannel) apiRequestWithBody(ctx context.Context, method, path string, body interface{}) ([]byte, error) {
	encoded, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequestWithContext(ctx, method, g.baseURL+path, bytes.NewReader(encoded))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	return g.doRequest(req)
}

func (g *GitHubChannel) doRequest(req *http.Request) ([]byte, error) {
	req.Header.Set("Authorization", "Bearer "+g.token)
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")

	resp, err := g.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("GitHub API %s %s: status %d: %s",
			req.Method, req.URL.Path, resp.StatusCode, data)
	}
	return data, nil
}

// --- GitHub API response types ---

type githubIssue struct {
	Number   int        `json:"number"`
	Title    string     `json:"title"`
	Body     string     `json:"body"`
	State    string     `json:"state"`
	ClosedBy githubUser `json:"closed_by"`
}

type githubComment struct {
	Body string     `json:"body"`
	User githubUser `json:"user"`
}

type githubUser struct {
	Login string `json:"login"`
}
