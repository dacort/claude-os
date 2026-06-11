# Workshop v3 — Chores Before Dessert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Idle Workshop cycles dispatch maintenance sessions that work an approved GitHub-issue backlog; creative sessions are earned by verified shipped work (soft-gated, no busywork).

**Architecture:** The controller's existing idle trigger (`creative.Workshop.CheckIdle`) gains a decision table fed by two new packages: `backlog` (fetches `octo-approved` issues from GitHub and verifies result artifacts) and `ledger` (credit balance persisted to `state/credits.json` in the controller's git clone). Maintenance jobs run under a new `claude-os-maintenance` ServiceAccount bound to a read-only `octo-observer` ClusterRole. Credit is granted when the watcher's completion callback finds a GitHub-verified artifact in the session's structured result.

**Tech Stack:** Go 1.25 (`github.com/dacort/claude-os`), stdlib `net/http` + `httptest` for GitHub API (mirrors `controller/comms/github.go` — no new deps), K8s manifests in `dacort/talos-homelab`.

**Spec:** `docs/specs/2026-06-10-workshop-v3-chores-before-dessert.md` (in `dacort/my-octopus-teacher`)

**Working repo:** `dacort/claude-os` (controller code), `dacort/talos-homelab` (Task 9 only).

---

### Task 1: Session decision table

The pure function implementing the spec's decision table. No I/O, trivially testable.

**Files:**
- Create: `controller/creative/decide.go`
- Test: `controller/creative/decide_test.go`

- [ ] **Step 1: Write the failing test**

```go
package creative

import "testing"

func TestDecideSession(t *testing.T) {
	tests := []struct {
		name    string
		backlog int
		credits int
		want    SessionType
	}{
		{"work waiting, no credits -> maintenance", 3, 0, SessionMaintenance},
		{"work waiting, has credit -> spend on creative", 3, 1, SessionCreativeSpend},
		{"work waiting, max credits -> spend on creative", 1, 3, SessionCreativeSpend},
		{"empty backlog, no credits -> free creative", 0, 0, SessionCreativeFree},
		{"empty backlog, has credits -> free creative (no spend)", 0, 2, SessionCreativeFree},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := DecideSession(tt.backlog, tt.credits); got != tt.want {
				t.Errorf("DecideSession(%d, %d) = %v, want %v", tt.backlog, tt.credits, got, tt.want)
			}
		})
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /workspace/claude-os && go test ./controller/creative/ -run TestDecideSession -v`
Expected: FAIL (compile error: `SessionType` undefined)

- [ ] **Step 3: Write minimal implementation**

```go
package creative

// SessionType is the kind of idle-time session the controller dispatches.
type SessionType int

const (
	// SessionMaintenance works the approved issue backlog.
	SessionMaintenance SessionType = iota
	// SessionCreativeSpend is a creative session paid for with one earned credit.
	SessionCreativeSpend
	// SessionCreativeFree is a creative session granted because there is no
	// approved work waiting — the gate only exists when real work is pending.
	SessionCreativeFree
)

// DecideSession implements the chores-before-dessert decision table
// (spec 2026-06-10, section 1). approvedBacklog is the count of open
// octo-approved issues; credits is the current ledger balance.
func DecideSession(approvedBacklog, credits int) SessionType {
	if approvedBacklog == 0 {
		return SessionCreativeFree
	}
	if credits >= 1 {
		return SessionCreativeSpend
	}
	return SessionMaintenance
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `go test ./controller/creative/ -run TestDecideSession -v`
Expected: PASS (5 subtests)

- [ ] **Step 5: Commit**

```bash
git add controller/creative/decide.go controller/creative/decide_test.go
git commit -m "feat(creative): session decision table for chores-before-dessert"
```

---

### Task 2: Credit ledger package

Credits persisted to `state/credits.json` inside the controller's git clone, committed via an injected commit function (decoupled from gitsync). Cap of 3, append-only history for transparency.

**Files:**
- Create: `controller/ledger/ledger.go`
- Test: `controller/ledger/ledger_test.go`

- [ ] **Step 1: Write the failing test**

```go
package ledger

import (
	"os"
	"path/filepath"
	"testing"
)

func newTestLedger(t *testing.T) (*Ledger, *int) {
	t.Helper()
	commits := 0
	path := filepath.Join(t.TempDir(), "state", "credits.json")
	l := New(path, func(msg string) error {
		commits++
		return nil
	})
	return l, &commits
}

func TestMissingFileMeansZeroBalance(t *testing.T) {
	l, _ := newTestLedger(t)
	if got := l.Balance(); got != 0 {
		t.Errorf("Balance() on missing file = %d, want 0", got)
	}
}

func TestEarnAndSpend(t *testing.T) {
	l, commits := newTestLedger(t)

	if got := l.Earn("workshop-maint-1", "merged PR"); got != 1 {
		t.Errorf("Earn() = %d, want 1", got)
	}
	if !l.Spend("workshop-2") {
		t.Error("Spend() with balance 1 = false, want true")
	}
	if got := l.Balance(); got != 0 {
		t.Errorf("Balance() after earn+spend = %d, want 0", got)
	}
	if l.Spend("workshop-3") {
		t.Error("Spend() with balance 0 = true, want false")
	}
	if *commits != 2 {
		t.Errorf("commit calls = %d, want 2 (earn + successful spend)", *commits)
	}
}

func TestEarnCapsAtThree(t *testing.T) {
	l, _ := newTestLedger(t)
	for i := 0; i < 5; i++ {
		l.Earn("workshop-maint-x", "merged PR")
	}
	if got := l.Balance(); got != Cap {
		t.Errorf("Balance() after 5 earns = %d, want %d", got, Cap)
	}
}

func TestPersistsAcrossInstances(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credits.json")
	noop := func(string) error { return nil }

	l1 := New(path, noop)
	l1.Earn("s1", "merged PR")
	l1.Earn("s2", "issue closed")

	l2 := New(path, noop)
	if got := l2.Balance(); got != 2 {
		t.Errorf("Balance() from fresh instance = %d, want 2", got)
	}
}

func TestCorruptFileTreatedAsZero(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credits.json")
	if err := os.WriteFile(path, []byte("not json{"), 0o644); err != nil {
		t.Fatal(err)
	}
	l := New(path, func(string) error { return nil })
	if got := l.Balance(); got != 0 {
		t.Errorf("Balance() on corrupt file = %d, want 0", got)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./controller/ledger/ -v`
Expected: FAIL (package does not exist / `New` undefined)

- [ ] **Step 3: Write minimal implementation**

```go
// Package ledger tracks creative-time credits for the chores-before-dessert
// Workshop loop (spec 2026-06-10). State lives in a JSON file inside the
// controller's git clone so it is transparent and survives Redis wipes.
package ledger

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Cap is the maximum credit balance — no hoarding haiku vouchers.
const Cap = 3

// historyLimit bounds the audit trail kept in the state file.
const historyLimit = 20

// Entry is one credit change, kept for transparency.
type Entry struct {
	Time    time.Time `json:"time"`
	Delta   int       `json:"delta"`
	Session string    `json:"session"`
	Reason  string    `json:"reason"`
}

type state struct {
	Credits int     `json:"credits"`
	History []Entry `json:"history"`
}

// Ledger reads and writes the credit balance. commitFn is called after every
// successful write with a commit message (wired to gitsync.CommitAndPush in
// production); commit failures are logged, not fatal — the file write is the
// source of truth until the next push succeeds.
type Ledger struct {
	mu       sync.Mutex
	path     string
	commitFn func(message string) error
}

func New(path string, commitFn func(string) error) *Ledger {
	return &Ledger{path: path, commitFn: commitFn}
}

// Balance returns the current credit balance. Missing or corrupt state files
// read as zero — the ledger is forgiving by design.
func (l *Ledger) Balance() int {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.load().Credits
}

// Earn adds one credit (capped at Cap) and returns the new balance.
func (l *Ledger) Earn(session, reason string) int {
	l.mu.Lock()
	defer l.mu.Unlock()

	s := l.load()
	if s.Credits >= Cap {
		slog.Info("ledger: at cap, credit not added", "session", session, "cap", Cap)
		return s.Credits
	}
	s.Credits++
	l.append(&s, Entry{Time: time.Now().UTC(), Delta: +1, Session: session, Reason: reason})
	l.save(s, fmt.Sprintf("ledger: +1 credit (%s) — balance %d", session, s.Credits))
	return s.Credits
}

// Spend removes one credit for a creative session. Returns false (and writes
// nothing) if the balance is zero.
func (l *Ledger) Spend(session string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	s := l.load()
	if s.Credits <= 0 {
		return false
	}
	s.Credits--
	l.append(&s, Entry{Time: time.Now().UTC(), Delta: -1, Session: session, Reason: "creative session"})
	l.save(s, fmt.Sprintf("ledger: -1 credit (%s) — balance %d", session, s.Credits))
	return true
}

func (l *Ledger) load() state {
	data, err := os.ReadFile(l.path)
	if err != nil {
		return state{}
	}
	var s state
	if err := json.Unmarshal(data, &s); err != nil {
		slog.Warn("ledger: corrupt state file, treating as zero", "path", l.path, "error", err)
		return state{}
	}
	return s
}

func (l *Ledger) append(s *state, e Entry) {
	s.History = append(s.History, e)
	if len(s.History) > historyLimit {
		s.History = s.History[len(s.History)-historyLimit:]
	}
}

func (l *Ledger) save(s state, commitMsg string) {
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		slog.Error("ledger: marshal failed", "error", err)
		return
	}
	if err := os.MkdirAll(filepath.Dir(l.path), 0o755); err != nil {
		slog.Error("ledger: mkdir failed", "path", l.path, "error", err)
		return
	}
	if err := os.WriteFile(l.path, data, 0o644); err != nil {
		slog.Error("ledger: write failed", "path", l.path, "error", err)
		return
	}
	if l.commitFn != nil {
		if err := l.commitFn(commitMsg); err != nil {
			slog.Warn("ledger: commit failed (state file still written)", "error", err)
		}
	}
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `go test ./controller/ledger/ -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add controller/ledger/
git commit -m "feat(ledger): git-backed creative-time credit ledger, cap 3"
```

---

### Task 3: Backlog package — approved issue fetching

GitHub API client following the existing `controller/comms/github.go` pattern (raw `net/http`, injectable `baseURL` for `httptest`). The `labels=octo-approved` query parameter makes unlabeled issues structurally unselectable — the security property lives in the query, not in client-side filtering.

**Files:**
- Create: `controller/backlog/backlog.go`
- Test: `controller/backlog/backlog_test.go`

- [ ] **Step 1: Write the failing test**

```go
package backlog

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestApprovedIssuesQueriesLabelAndSorts(t *testing.T) {
	var gotQuery string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/repos/dacort/claude-os/issues" {
			t.Errorf("unexpected path %s", r.URL.Path)
		}
		gotQuery = r.URL.RawQuery
		// Out of order on purpose: normal-priority older issue, a PR (must be
		// skipped), a high-priority newer issue.
		json.NewEncoder(w).Encode([]map[string]any{
			{"number": 10, "title": "older normal", "html_url": "https://github.com/dacort/claude-os/issues/10",
				"created_at": "2026-06-01T00:00:00Z", "labels": []map[string]string{{"name": "octo-approved"}}},
			{"number": 11, "title": "a PR not an issue", "html_url": "https://github.com/dacort/claude-os/pull/11",
				"created_at": "2026-05-01T00:00:00Z", "labels": []map[string]string{{"name": "octo-approved"}},
				"pull_request": map[string]string{"url": "x"}},
			{"number": 12, "title": "newer but high", "html_url": "https://github.com/dacort/claude-os/issues/12",
				"created_at": "2026-06-08T00:00:00Z", "labels": []map[string]string{{"name": "octo-approved"}, {"name": "priority:high"}}},
		})
	}))
	defer srv.Close()

	c := NewClient("dacort", "claude-os", "test-token")
	c.baseURL = srv.URL

	issues, err := c.ApprovedIssues(context.Background())
	if err != nil {
		t.Fatalf("ApprovedIssues() error: %v", err)
	}

	for _, want := range []string{"labels=octo-approved", "state=open"} {
		if !contains(gotQuery, want) {
			t.Errorf("query %q missing %q", gotQuery, want)
		}
	}
	if len(issues) != 2 {
		t.Fatalf("got %d issues, want 2 (PR filtered out)", len(issues))
	}
	if issues[0].Number != 12 {
		t.Errorf("first issue = #%d, want #12 (priority:high beats age)", issues[0].Number)
	}
	if issues[1].Number != 10 {
		t.Errorf("second issue = #%d, want #10", issues[1].Number)
	}
}

func TestApprovedIssuesEmptyOnAPIError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer srv.Close()

	c := NewClient("dacort", "claude-os", "test-token")
	c.baseURL = srv.URL

	if _, err := c.ApprovedIssues(context.Background()); err == nil {
		t.Error("ApprovedIssues() on 403 = nil error, want error")
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./controller/backlog/ -v`
Expected: FAIL (package does not exist)

- [ ] **Step 3: Write minimal implementation**

```go
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `go test ./controller/backlog/ -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add controller/backlog/
git commit -m "feat(backlog): fetch octo-approved issues, priority/age ordering"
```

---

### Task 4: Backlog package — artifact verification

Verifies a session's claimed artifacts against GitHub per the spec: claude-os PR **merged**, foreign-repo PR (talos-homelab) **open with all check runs green**, issue **closed**. Anything else — commits, files, unparseable URLs — earns nothing.

**Files:**
- Create: `controller/backlog/verify.go`
- Test: `controller/backlog/verify_test.go`

- [ ] **Step 1: Write the failing test**

```go
package backlog

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/dacort/claude-os/controller/queue"
)

// verifyTestServer fakes the three GitHub endpoints VerifyArtifact uses.
func verifyTestServer(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	// Home-repo PR #5: merged.
	mux.HandleFunc("/repos/dacort/claude-os/pulls/5", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"merged": true, "state": "closed"})
	})
	// Home-repo PR #6: open, not merged.
	mux.HandleFunc("/repos/dacort/claude-os/pulls/6", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"merged": false, "state": "open"})
	})
	// Foreign-repo PR #7: open with green checks.
	mux.HandleFunc("/repos/dacort/talos-homelab/pulls/7", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{
			"merged": false, "state": "open",
			"head": map[string]string{"sha": "abc123"},
		})
	})
	mux.HandleFunc("/repos/dacort/talos-homelab/commits/abc123/check-runs", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{
			"total_count": 1,
			"check_runs":  []map[string]string{{"status": "completed", "conclusion": "success"}},
		})
	})
	// Issue #8: closed.
	mux.HandleFunc("/repos/dacort/claude-os/issues/8", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"state": "closed"})
	})
	return httptest.NewServer(mux)
}

func TestVerifyArtifact(t *testing.T) {
	srv := verifyTestServer(t)
	defer srv.Close()

	c := NewClient("dacort", "claude-os", "test-token")
	c.baseURL = srv.URL

	tests := []struct {
		name     string
		artifact queue.ResultArtifact
		want     bool
	}{
		{"merged home-repo PR", queue.ResultArtifact{Type: "pr", URL: "https://github.com/dacort/claude-os/pull/5"}, true},
		{"open home-repo PR not merged", queue.ResultArtifact{Type: "pr", URL: "https://github.com/dacort/claude-os/pull/6"}, false},
		{"open foreign PR with green CI", queue.ResultArtifact{Type: "pr", URL: "https://github.com/dacort/talos-homelab/pull/7"}, true},
		{"closed issue", queue.ResultArtifact{Type: "issue", URL: "https://github.com/dacort/claude-os/issues/8"}, true},
		{"bare commit earns nothing", queue.ResultArtifact{Type: "commit", Ref: "abc123"}, false},
		{"file earns nothing", queue.ResultArtifact{Type: "file", Path: "knowledge/x.md"}, false},
		{"garbage URL", queue.ResultArtifact{Type: "pr", URL: "https://example.com/nope"}, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := c.VerifyArtifact(context.Background(), tt.artifact); got != tt.want {
				t.Errorf("VerifyArtifact(%+v) = %v, want %v", tt.artifact, got, tt.want)
			}
		})
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./controller/backlog/ -run TestVerifyArtifact -v`
Expected: FAIL (`VerifyArtifact` undefined)

- [ ] **Step 3: Write minimal implementation**

```go
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `go test ./controller/backlog/ -v`
Expected: PASS (all tests including Task 3's)

- [ ] **Step 5: Commit**

```bash
git add controller/backlog/verify.go controller/backlog/verify_test.go
git commit -m "feat(backlog): GitHub artifact verification for credit grants"
```

---

### Task 5: Per-task ServiceAccount override in the dispatcher

Maintenance jobs need the `claude-os-maintenance` SA (cluster read access); everything else keeps `claude-os-worker`. One new optional field on `queue.Task`, one line in the job spec.

**Files:**
- Modify: `controller/queue/queue.go` (Task struct, ~line 39)
- Modify: `controller/dispatcher/dispatcher.go` (job spec, ~line 307)
- Test: `controller/dispatcher/dispatcher_test.go` (append)

- [ ] **Step 1: Add the field to queue.Task**

In `controller/queue/queue.go`, add to the `Task` struct after the `TriageVerdict` field:

```go
	// ServiceAccount optionally overrides the K8s ServiceAccount the worker
	// job runs as. Empty means the default "claude-os-worker". Maintenance
	// sessions use "claude-os-maintenance" for read-only cluster observation.
	ServiceAccount string `json:"service_account,omitempty"`
```

- [ ] **Step 2: Write the failing test**

Append to `controller/dispatcher/dispatcher_test.go`, following the existing test style in that file (fake clientset, construct dispatcher the same way neighboring tests do):

```go
func TestCreateJobServiceAccountOverride(t *testing.T) {
	// Mirror the setup of the nearest existing TestCreateJob* test in this
	// file for dispatcher construction (fake.NewSimpleClientset, profiles).
	d := newTestDispatcher(t) // use/extract the existing test helper pattern

	defaultTask := &queue.Task{ID: "sa-default", Title: "t", Profile: "small"}
	job, err := d.CreateJob(context.Background(), defaultTask)
	if err != nil {
		t.Fatal(err)
	}
	if got := job.Spec.Template.Spec.ServiceAccountName; got != "claude-os-worker" {
		t.Errorf("default SA = %q, want claude-os-worker", got)
	}

	maintTask := &queue.Task{ID: "sa-maint", Title: "t", Profile: "small",
		ServiceAccount: "claude-os-maintenance"}
	job, err = d.CreateJob(context.Background(), maintTask)
	if err != nil {
		t.Fatal(err)
	}
	if got := job.Spec.Template.Spec.ServiceAccountName; got != "claude-os-maintenance" {
		t.Errorf("override SA = %q, want claude-os-maintenance", got)
	}
}
```

Note: if `dispatcher_test.go` has no reusable helper, inline the same construction the existing tests use rather than inventing `newTestDispatcher`.

- [ ] **Step 3: Run test to verify it fails**

Run: `go test ./controller/dispatcher/ -run TestCreateJobServiceAccountOverride -v`
Expected: FAIL (override SA = "claude-os-worker")

- [ ] **Step 4: Implement the override**

In `controller/dispatcher/dispatcher.go`, before the `job := &batchv1.Job{` literal (~line 286), add:

```go
	serviceAccount := task.ServiceAccount
	if serviceAccount == "" {
		serviceAccount = "claude-os-worker"
	}
```

and change the hardcoded line in the pod spec:

```go
					ServiceAccountName: serviceAccount,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `go test ./controller/dispatcher/ ./controller/queue/ -v`
Expected: PASS (all tests in both packages)

- [ ] **Step 6: Commit**

```bash
git add controller/queue/queue.go controller/dispatcher/dispatcher.go controller/dispatcher/dispatcher_test.go
git commit -m "feat(dispatcher): per-task ServiceAccount override"
```

---

### Task 6: Maintenance sessions in the Workshop

Wire the decision table into `CheckIdle` and add the maintenance session dispatch with its prompt. The ledger/backlog dependencies are injected via a setter so existing constructor call sites and tests keep working; when unset, behavior is exactly v2.

**Files:**
- Create: `controller/creative/maintenance.go`
- Modify: `controller/creative/creative.go`
- Test: `controller/creative/maintenance_test.go`

- [ ] **Step 1: Write the failing test**

```go
package creative

import (
	"strings"
	"testing"

	"github.com/dacort/claude-os/controller/backlog"
)

func TestMaintenancePromptContainsContract(t *testing.T) {
	issue := backlog.Issue{
		Number: 42,
		Title:  "Fix the git index corruption recovery",
		Body:   "The controller clone corrupted on June 9.",
		URL:    "https://github.com/dacort/claude-os/issues/42",
	}
	p := maintenancePrompt(issue)

	for _, want := range []string{
		"#42",
		"Fix the git index corruption recovery",
		"https://github.com/dacort/claude-os/issues/42",
		"inspection",          // inspection pass comes first
		"octo-approved",       // explains the approval gate for filed issues
		"never merge",         // talos-homelab PRs are dacort's to merge
		"===RESULT_START===",  // structured result contract
		"artifacts",           // artifact list drives credit verification
	} {
		if !strings.Contains(strings.ToLower(p), strings.ToLower(want)) {
			t.Errorf("maintenancePrompt missing %q", want)
		}
	}
}

func TestMaintenanceTaskShape(t *testing.T) {
	issue := backlog.Issue{Number: 7, Title: "Tend the certs", URL: "https://github.com/dacort/claude-os/issues/7"}
	task := maintenanceTask(issue)

	if !strings.HasPrefix(task.ID, "workshop-maint-") {
		// The "workshop" ID prefix is what SyncState and IsCreativeJob key on —
		// breaking it would orphan sessions across controller restarts.
		t.Errorf("task ID %q must keep the workshop- prefix", task.ID)
	}
	if task.ServiceAccount != "claude-os-maintenance" {
		t.Errorf("ServiceAccount = %q, want claude-os-maintenance", task.ServiceAccount)
	}
	if task.Profile != "medium" {
		t.Errorf("Profile = %q, want medium", task.Profile)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./controller/creative/ -run TestMaintenance -v`
Expected: FAIL (`maintenancePrompt`, `maintenanceTask` undefined)

- [ ] **Step 3: Implement maintenance.go**

```go
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
- Stale work: tasks stuck in tasks/in-progress/, open PRs with no activity, approved issues nobody has touched

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
  namespace): open a PR and NEVER merge it. dacort reviews and merges homelab
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `go test ./controller/creative/ -run TestMaintenance -v`
Expected: PASS

- [ ] **Step 5: Wire the decision into the Workshop**

In `controller/creative/creative.go`:

**(a)** Add imports for `"github.com/dacort/claude-os/controller/backlog"` and `"github.com/dacort/claude-os/controller/ledger"`, and add fields to the `Workshop` struct (after `activeProject string`):

```go
	// Chores-before-dessert (v3). Both nil → pure v2 behavior.
	creditLedger  *ledger.Ledger
	backlogClient *backlog.Client
	activeType    SessionType // session type of the currently active job
```

**(b)** Add the setter (after `NewWorkshop`):

```go
// EnableMaintenance wires in the credit ledger and approved-issue backlog,
// activating the chores-before-dessert decision table. Without this call the
// Workshop behaves exactly as v2 (always free creative time).
func (w *Workshop) EnableMaintenance(l *ledger.Ledger, b *backlog.Client) {
	w.creditLedger = l
	w.backlogClient = b
}
```

**(c)** In `CheckIdle`, replace the final call `w.startCreativeTask(ctx)` with `w.startSession(ctx)`, and add:

```go
// startSession picks the session type per the decision table and dispatches.
func (w *Workshop) startSession(ctx context.Context) {
	if w.creditLedger == nil || w.backlogClient == nil {
		w.activeType = SessionCreativeFree
		w.startCreativeTask(ctx)
		return
	}

	issues, err := w.backlogClient.ApprovedIssues(ctx)
	if err != nil {
		// Fail open: GitHub being down shouldn't cancel the session. An
		// unreachable backlog is treated as empty (free creative time).
		slog.Warn("workshop: backlog fetch failed, treating as empty", "error", err)
		issues = nil
	}

	switch DecideSession(len(issues), w.creditLedger.Balance()) {
	case SessionMaintenance:
		w.activeType = SessionMaintenance
		w.startMaintenanceTask(ctx, issues[0])
	case SessionCreativeSpend:
		w.creditLedger.Spend("pending-session")
		w.activeType = SessionCreativeSpend
		slog.Info("workshop: spending 1 credit on creative session",
			"balance", w.creditLedger.Balance())
		w.startCreativeTask(ctx)
	case SessionCreativeFree:
		w.activeType = SessionCreativeFree
		w.startCreativeTask(ctx)
	}
}

// startMaintenanceTask dispatches a maintenance session for the given issue.
func (w *Workshop) startMaintenanceTask(ctx context.Context, issue backlog.Issue) {
	task := maintenanceTask(issue)
	job, err := w.dispatcher.CreateJob(ctx, task)
	if err != nil {
		slog.Error("workshop: failed to create maintenance job", "error", err)
		return
	}
	w.active = true
	w.activeJob = job.Name
	slog.Info("workshop: maintenance session started",
		"job", job.Name, "issue", issue.Number, "title", issue.Title)
}
```

- [ ] **Step 6: Run the full creative package tests**

Run: `go test ./controller/creative/ -v`
Expected: PASS (existing v2 tests unaffected — nil ledger/backlog preserves old behavior)

- [ ] **Step 7: Commit**

```bash
git add controller/creative/
git commit -m "feat(creative): maintenance sessions with chores-before-dessert decision"
```

---

### Task 7: Credit granting on session completion

When a maintenance session finishes, verify its claimed artifacts and grant at most one credit. This changes `OnJobFinished`'s signature to receive the parsed result, which requires reordering the watcher callback in `main.go` (it currently notifies the workshop *before* parsing the result).

**Files:**
- Modify: `controller/creative/creative.go` (`OnJobFinished`, ~line 191)
- Modify: `controller/main.go` (watcher callback, ~lines 464–510)
- Test: `controller/creative/maintenance_test.go` (append)

- [ ] **Step 1: Write the failing test**

Append to `controller/creative/maintenance_test.go`. Build the Workshop the same way existing tests in `creative_test.go` do (fake clientset); the key new pieces are a ledger on a temp path and a backlog client pointed at a verify stub:

```go
func TestMaintenanceCompletionGrantsCredit(t *testing.T) {
	// GitHub stub: PR 5 merged.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/repos/dacort/claude-os/pulls/5" {
			json.NewEncoder(w).Encode(map[string]any{"merged": true, "state": "closed"})
			return
		}
		http.NotFound(w, r)
	}))
	defer srv.Close()

	w := newTestWorkshop(t) // follow creative_test.go's construction pattern
	led := ledger.New(filepath.Join(t.TempDir(), "credits.json"), func(string) error { return nil })
	bc := backlog.NewClientForTest("dacort", "claude-os", "tok", srv.URL)
	w.EnableMaintenance(led, bc)

	// Simulate an active maintenance session.
	w.active = true
	w.activeJob = "claude-os-workshop-maint-x"
	w.activeType = SessionMaintenance

	result := &queue.TaskResult{
		Outcome: "success",
		Artifacts: []queue.ResultArtifact{
			{Type: "pr", URL: "https://github.com/dacort/claude-os/pull/5"},
			{Type: "pr", URL: "https://github.com/dacort/claude-os/pull/999"}, // 404s — ignored
		},
	}
	w.OnJobFinished("claude-os-workshop-maint-x", result)

	if got := led.Balance(); got != 1 {
		t.Errorf("Balance() after verified maintenance session = %d, want 1 (one credit per session, not per artifact)", got)
	}
}

func TestCreativeCompletionGrantsNothing(t *testing.T) {
	w := newTestWorkshop(t)
	led := ledger.New(filepath.Join(t.TempDir(), "credits.json"), func(string) error { return nil })
	bc := backlog.NewClientForTest("dacort", "claude-os", "tok", "http://127.0.0.1:0")
	w.EnableMaintenance(led, bc)

	w.active = true
	w.activeJob = "claude-os-workshop-x"
	w.activeType = SessionCreativeFree

	w.OnJobFinished("claude-os-workshop-x", &queue.TaskResult{
		Outcome:   "success",
		Artifacts: []queue.ResultArtifact{{Type: "pr", URL: "https://github.com/dacort/claude-os/pull/5"}},
	})

	if got := led.Balance(); got != 0 {
		t.Errorf("Balance() after creative session = %d, want 0", got)
	}
}
```

Also add the test-only constructor to `controller/backlog/backlog.go`:

```go
// NewClientForTest builds a Client against a fake GitHub base URL.
func NewClientForTest(owner, repo, token, baseURL string) *Client {
	c := NewClient(owner, repo, token)
	c.baseURL = baseURL
	return c
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./controller/creative/ -run TestMaintenanceCompletion -v`
Expected: FAIL (compile error: `OnJobFinished` takes 1 argument)

- [ ] **Step 3: Change OnJobFinished**

In `controller/creative/creative.go`, change the signature and add credit logic before the state reset:

```go
// OnJobFinished is called by the watcher when any job completes. result is
// the parsed v1 result contract, or nil if the worker emitted none.
func (w *Workshop) OnJobFinished(jobName string, result *queue.TaskResult) {
	if !w.active || w.activeJob != jobName {
		return
	}
	slog.Info("workshop: creative session completed", "job", jobName)

	// Chores-before-dessert: a maintenance session with at least one
	// GitHub-verified artifact earns one credit. Soft enforcement — failed
	// verification means no credit, nothing else.
	if w.activeType == SessionMaintenance && w.creditLedger != nil &&
		w.backlogClient != nil && result != nil {
		w.grantCreditIfVerified(jobName, result)
	}

	// Release any project lock we held, regardless of success/failure.
	if w.activeProject != "" && w.rdb != nil {
		clearProjectActive(context.Background(), w.rdb, w.activeProject)
		w.activeProject = ""
	}

	w.active = false
	w.activeJob = ""
	w.lastTask = time.Now() // Reset idle timer so we don't immediately re-enter
}

func (w *Workshop) grantCreditIfVerified(jobName string, result *queue.TaskResult) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	for _, a := range result.Artifacts {
		if w.backlogClient.VerifyArtifact(ctx, a) {
			balance := w.creditLedger.Earn(jobName, fmt.Sprintf("verified %s %s", a.Type, a.URL))
			slog.Info("workshop: credit earned", "session", jobName,
				"artifact", a.URL, "balance", balance)
			return // one credit per session, not per artifact
		}
	}
	slog.Info("workshop: no verifiable artifacts, no credit", "session", jobName)
}
```

Note the existing body of `OnJobFinished` is restructured with an early return instead of the old `if w.active && w.activeJob == jobName` wrapper — same semantics.

- [ ] **Step 4: Reorder the watcher callback in main.go**

In `controller/main.go` (~line 464), the callback currently calls `workshop.OnJobFinished(...)` first and parses the result afterwards. Restructure so parsing happens first:

```go
	jobWatcher := watcher.New(k8sClient, cfg.Worker.Namespace, func(taskID string, succeeded bool, logs string) {
		var parsedResult *queue.TaskResult
		if result := queue.ParseResult(logs); result != nil {
			parsedResult = result
		}

		// Notify workshop if this was a creative/maintenance job. Passing the
		// parsed result lets it verify artifacts and grant credits.
		if workshop != nil {
			workshop.OnJobFinished(fmt.Sprintf("claude-os-%s", taskID), parsedResult)
		}

		// Notify scheduler so the next run of a recurring task can proceed
		taskScheduler.OnTaskCompleted(ctx, taskID)

		if parsedResult != nil {
			slog.Info("task result (v1 contract)", ...)  // keep existing log + task save block, switching `result` to `parsedResult`
			...
		} else if usage := queue.ParseUsage(logs); usage != nil {
			...  // unchanged legacy branch
		}
		...  // rest of callback unchanged
	})
```

Keep every existing branch (legacy usage, blocker handling, task completion) intact — only the parse order and the `OnJobFinished` arguments change. Fix any other `OnJobFinished` call sites (`grep -rn "OnJobFinished" controller/`) — including existing tests in `creative_test.go`, which should pass `nil` as the new argument.

- [ ] **Step 5: Run the full test suite**

Run: `go build ./... && go test ./...`
Expected: PASS everywhere; `go vet ./...` clean

- [ ] **Step 6: Commit**

```bash
git add controller/
git commit -m "feat(creative): grant credits for verified maintenance artifacts"
```

---

### Task 8: Wire it all up in main.go

Construct the ledger and backlog client and enable maintenance mode — gated on the pieces it needs (GitHub token, git syncer).

**Files:**
- Modify: `controller/main.go` (after the Workshop is constructed; find `NewWorkshop(`)

- [ ] **Step 1: Add the wiring**

After the `workshop := creative.NewWorkshop(...)` construction in `controller/main.go`, add:

```go
	// Chores-before-dessert (Workshop v3): maintenance sessions work the
	// octo-approved issue backlog; verified shipped work earns creative time.
	if githubToken != "" {
		creditLedger := ledger.New(
			filepath.Join(gitSyncer.LocalPath(), "state", "credits.json"),
			func(msg string) error { return gitSyncer.CommitAndPush(msg) },
		)
		backlogClient := backlog.NewClient("dacort", "claude-os", githubToken)
		workshop.EnableMaintenance(creditLedger, backlogClient)
		slog.Info("workshop: maintenance mode enabled",
			"label", backlog.ApprovedLabel, "credits", creditLedger.Balance())
	} else {
		slog.Warn("workshop: maintenance mode disabled, no GITHUB_TOKEN")
	}
```

Add `"path/filepath"`, `"github.com/dacort/claude-os/controller/backlog"`, and `"github.com/dacort/claude-os/controller/ledger"` to imports as needed. The owner/repo are deliberately the same hardcoded `dacort`/`claude-os` used elsewhere in main.go's GitHub wiring — follow whatever constant/variable main.go already uses for the comms channel if one exists.

- [ ] **Step 2: Build and test everything**

Run: `go build ./... && go test ./... && go vet ./...`
Expected: all green

- [ ] **Step 3: Add state/ to the repo**

```bash
mkdir -p state
printf '{\n  "credits": 0,\n  "history": []\n}\n' > state/credits.json
git add state/credits.json
```

- [ ] **Step 4: Commit and push (CI is the gate)**

```bash
git add controller/main.go state/
git commit -m "feat: wire chores-before-dessert maintenance mode into controller"
git push origin main
```

CI builds the image and auto-deploys via talos-homelab. Maintenance sessions stay inert until an issue carries the `octo-approved` label, so deploying first is safe.

---

### Task 9: RBAC — octo-observer ClusterRole and maintenance ServiceAccount

This is a **talos-homelab** change — per the spec's own rules it ships as a PR that dacort merges. Note: `infra/claude-os/rbac.yaml` currently defines `claude-os-worker` with no role bindings (workers don't touch the K8s API), so the new SA only needs the observer binding.

**Files:**
- Create: `infra/claude-os/maintenance-rbac.yaml` (in `dacort/talos-homelab`)
- Check: `infra/claude-os/network-policies.yaml`

- [ ] **Step 1: Write the manifest**

```yaml
# Read-only cluster observation for Workshop maintenance sessions
# (chores-before-dessert, spec 2026-06-10 in my-octopus-teacher).
# Deliberately NO access to secrets, and no write verbs anywhere.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: claude-os-maintenance
  namespace: claude-os
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: octo-observer
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "nodes", "events", "namespaces", "services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "daemonsets", "statefulsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: octo-observer-maintenance
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: octo-observer
subjects:
  - kind: ServiceAccount
    name: claude-os-maintenance
    namespace: claude-os
```

- [ ] **Step 2: Check the network policy allows API access**

Read `infra/claude-os/network-policies.yaml`. Maintenance pods carry the same `app=claude-os-worker` label as other workers, so they inherit the worker egress policy. Verify worker egress permits HTTPS to the K8s API server (the kubernetes service endpoint, port 443/6443). If the existing policy already allows general HTTPS egress (workers reach github.com today), no change is needed — note the finding in the PR description either way.

- [ ] **Step 3: Validate**

Run: `kubectl --dry-run=client apply -f infra/claude-os/maintenance-rbac.yaml`
Expected: 3 resources validated, no errors

- [ ] **Step 4: Open the PR (do NOT merge)**

```bash
cd ~/src/talos-homelab   # or the worker's clone
git checkout -b claude-os/maintenance-rbac
git add infra/claude-os/maintenance-rbac.yaml
git commit -m "feat(claude-os): octo-observer ClusterRole + maintenance ServiceAccount"
git push origin claude-os/maintenance-rbac
gh pr create --repo dacort/talos-homelab \
  --title "claude-os: read-only octo-observer RBAC for maintenance sessions" \
  --body "Adds the claude-os-maintenance ServiceAccount bound to a new octo-observer ClusterRole (get/list/watch on workloads, nodes, events — explicitly no secrets, no writes). Required by Workshop v3 chores-before-dessert (spec in my-octopus-teacher docs/specs/2026-06-10). Network policy check result: <fill in from Step 2>. Maintenance sessions fall back gracefully until this merges: kubectl calls fail read-only and the session still works its issue."
```

dacort merges this one — the homelab boundary applies to the octopus's own infra PRs too.

---

### Task 10: Documentation

**Files:**
- Modify: `CLAUDE.md` (in `dacort/claude-os` — operator notes)
- Modify: `~/src/my-octopus-teacher/CLAUDE.md` (backchannel — how dacort approves work)

- [ ] **Step 1: Document in claude-os CLAUDE.md**

Add a section (match the file's existing tone/format):

```markdown
## Workshop v3 — Chores Before Dessert

Idle sessions are decided by a table: approved work waiting + no credits →
maintenance session; credits available → spend one on a creative session;
empty backlog → free creative time (no busywork).

- Backlog: open issues on dacort/claude-os labeled `octo-approved` (only
  dacort applies the label — the repo is public, unlabeled issues are inert).
- Credits: `state/credits.json`, written only by the controller, cap 3.
  Earned when a maintenance session's result artifacts verify on GitHub
  (merged claude-os PR / open talos-homelab PR with green CI / closed issue).
- Maintenance sessions run as `claude-os-maintenance` (read-only cluster
  observation via the octo-observer ClusterRole, no secrets).
- Homelab changes always ship as talos-homelab PRs that dacort merges.
```

- [ ] **Step 2: Document the approval flow in the backchannel CLAUDE.md**

Add to `~/src/my-octopus-teacher/CLAUDE.md` under Brain Mode:

```markdown
### Approving Maintenance Work (Workshop v3)

The octopus works GitHub issues on dacort/claude-os labeled `octo-approved`.
To approve work: `gh issue edit <n> --repo dacort/claude-os --add-label octo-approved`
To check the credit balance: `cat /tmp/claude-os/state/credits.json` (after git pull)
Issues filed by inspection passes arrive unlabeled — review and label to greenlight.
```

- [ ] **Step 3: Create the label and commit docs**

```bash
gh label create octo-approved --repo dacort/claude-os \
  --description "dacort-approved for autonomous maintenance work" --color 1D76DB
gh label create "priority:high" --repo dacort/claude-os \
  --description "worked before other approved issues" --color D93F0B 2>/dev/null || true
```

Commit both CLAUDE.md changes in their respective repos (`docs: workshop v3 chores-before-dessert operator notes`).

---

## Self-Review Notes

- **Spec coverage:** decision table → Task 1/6; approval gate → Task 3 (server-side label query) + Task 10 (label creation); maintenance anatomy → Task 6 prompt; credit ledger + verification → Tasks 2/4/7; RBAC → Task 9; result contract `artifacts` → already exists in `queue.TaskResult` (no task needed); rollout-inert-until-labeled → Task 8 Step 4.
- **Type consistency:** `SessionType` (Task 1) used in Tasks 6–7; `backlog.Issue`/`Client` (Task 3) used in 4, 6, 7; `ledger.Ledger` (Task 2) used in 6–8; `queue.ResultArtifact` matches existing `controller/queue/queue.go:468`.
- **Known judgment calls:** credit spend happens at dispatch (preempted creative sessions still consume — acceptable, rare, soft system); backlog fetch error fails open to free creative time rather than blocking; `workshop-maint-` ID prefix preserves the `[:8] == "workshop"` checks in `SyncState`/`ListCompletedSessions`.
