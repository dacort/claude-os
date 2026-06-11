// Package backlog selects approved work for Workshop maintenance sessions
// and verifies result artifacts against GitHub (spec 2026-06-10, sections
// 2 and 4). Only issues carrying ApprovedLabel are ever returned — the repo
// is public, and the label (applicable only by users with triage permission)
// is the gate that keeps strangers from injecting work.
package backlog

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sort"
	"time"
)

// ApprovedLabel marks an issue as approved by dacort for autonomous work.
const ApprovedLabel = "octo-approved"

// priorityHighLabel sorts ahead of everything else; ties break oldest-first.
const priorityHighLabel = "priority:high"

// Issue is an approved, workable GitHub issue.
type Issue struct {
	Number    int
	Title     string
	Body      string
	URL       string
	Labels    []string
	CreatedAt time.Time
}

func (i Issue) highPriority() bool {
	for _, l := range i.Labels {
		if l == priorityHighLabel {
			return true
		}
	}
	return false
}

// Client talks to the GitHub REST API. baseURL is overridable in tests.
type Client struct {
	owner   string
	repo    string
	token   string
	baseURL string
	http    *http.Client
}

func NewClient(owner, repo, token string) *Client {
	return &Client{
		owner:   owner,
		repo:    repo,
		token:   token,
		baseURL: "https://api.github.com",
		http:    &http.Client{Timeout: 30 * time.Second},
	}
}

// NewClientForTest builds a Client against a fake GitHub base URL.
func NewClientForTest(owner, repo, token, baseURL string) *Client {
	c := NewClient(owner, repo, token)
	c.baseURL = baseURL
	return c
}

// ApprovedIssues returns open issues labeled ApprovedLabel, sorted
// priority:high first, then oldest first. PRs (which GitHub's issues API
// also returns) are excluded.
func (c *Client) ApprovedIssues(ctx context.Context) ([]Issue, error) {
	url := fmt.Sprintf("%s/repos/%s/%s/issues?labels=%s&state=open&per_page=50",
		c.baseURL, c.owner, c.repo, ApprovedLabel)

	var raw []struct {
		Number      int       `json:"number"`
		Title       string    `json:"title"`
		Body        string    `json:"body"`
		HTMLURL     string    `json:"html_url"`
		CreatedAt   time.Time `json:"created_at"`
		PullRequest *struct{} `json:"pull_request"`
		Labels      []struct {
			Name string `json:"name"`
		} `json:"labels"`
	}
	if err := c.getJSON(ctx, url, &raw); err != nil {
		return nil, err
	}

	var issues []Issue
	for _, r := range raw {
		if r.PullRequest != nil {
			continue
		}
		labels := make([]string, 0, len(r.Labels))
		for _, l := range r.Labels {
			labels = append(labels, l.Name)
		}
		issues = append(issues, Issue{
			Number: r.Number, Title: r.Title, Body: r.Body,
			URL: r.HTMLURL, Labels: labels, CreatedAt: r.CreatedAt,
		})
	}

	sort.SliceStable(issues, func(a, b int) bool {
		if issues[a].highPriority() != issues[b].highPriority() {
			return issues[a].highPriority()
		}
		return issues[a].CreatedAt.Before(issues[b].CreatedAt)
	})
	return issues, nil
}

func (c *Client) getJSON(ctx context.Context, url string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("github API %s: status %d", url, resp.StatusCode)
	}
	return json.NewDecoder(resp.Body).Decode(out)
}
