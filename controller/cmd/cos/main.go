// cos — terminal interface for Claude OS.
//
// Usage:
//
//	cos status           system snapshot (queue, tokens, agents)
//	cos log <id>         fetch or stream task logs
//	cos task <id>        detailed info for a single task
//	cos run <title>      create and enqueue a new task
//
// Environment:
//
//	CONTROLLER_URL   base URL of the controller (default: http://localhost:8080)
//	NO_COLOR         set to any value to disable ANSI colors
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

// ---------------------------------------------------------------------------
// Color helpers
// ---------------------------------------------------------------------------

var noColor = os.Getenv("NO_COLOR") != ""

const (
	ansiReset  = "\033[0m"
	ansiRed    = "\033[31m"
	ansiGreen  = "\033[32m"
	ansiYellow = "\033[33m"
	ansiCyan   = "\033[36m"
	ansiBold   = "\033[1m"
	ansiDim    = "\033[2m"
)

func colorize(code, s string) string {
	if noColor {
		return s
	}
	return code + s + ansiReset
}

func red(s string) string    { return colorize(ansiRed, s) }
func green(s string) string  { return colorize(ansiGreen, s) }
func yellow(s string) string { return colorize(ansiYellow, s) }
func cyan(s string) string   { return colorize(ansiCyan, s) }
func bold(s string) string   { return colorize(ansiBold, s) }
func dim(s string) string    { return colorize(ansiDim, s) }

// outcomeColor maps a task outcome string to its colored version.
func outcomeColor(outcome string) string {
	switch outcome {
	case "success":
		return green(outcome)
	case "failed", "failure":
		return red(outcome)
	default:
		return yellow(outcome)
	}
}

// statusColor colors a task status string.
func statusColor(status string) string {
	switch status {
	case "running":
		return cyan(status)
	case "completed":
		return green(status)
	case "failed":
		return red(status)
	case "pending", "blocked":
		return yellow(status)
	default:
		return status
	}
}

// agentStatusColor colors agent health strings.
func agentStatusColor(status string) string {
	switch status {
	case "ok":
		return green(status)
	case "rate_limited":
		return yellow("rate-limited")
	default:
		return red(status)
	}
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

// humanDuration returns a human-readable duration string.
func humanDuration(d time.Duration) string {
	d = d.Round(time.Second)
	if d < time.Minute {
		return fmt.Sprintf("%ds", int(d.Seconds()))
	}
	if d < time.Hour {
		m := int(d.Minutes())
		s := int(d.Seconds()) % 60
		if s == 0 {
			return fmt.Sprintf("%dm", m)
		}
		return fmt.Sprintf("%dm %ds", m, s)
	}
	h := int(d.Hours())
	m := int(d.Minutes()) % 60
	if m == 0 {
		return fmt.Sprintf("%dh", h)
	}
	return fmt.Sprintf("%dh %dm", h, m)
}

// humanDurationSeconds converts seconds to human-readable string.
func humanDurationSeconds(secs int64) string {
	return humanDuration(time.Duration(secs) * time.Second)
}

// relativeTime renders a time relative to now when it was within the last 24h,
// otherwise absolute UTC.
func relativeTime(t time.Time) string {
	if t.IsZero() {
		return "-"
	}
	d := time.Since(t)
	if d < 0 {
		d = -d
	}
	if d < 24*time.Hour {
		return humanDuration(d) + " ago"
	}
	return t.UTC().Format("2006-01-02 15:04 UTC")
}

// commaInt formats an integer with comma separators.
func commaInt(n int64) string {
	s := strconv.FormatInt(n, 10)
	if len(s) <= 3 {
		return s
	}
	var b strings.Builder
	rem := len(s) % 3
	if rem > 0 {
		b.WriteString(s[:rem])
	}
	for i := rem; i < len(s); i += 3 {
		if b.Len() > 0 {
			b.WriteByte(',')
		}
		b.WriteString(s[i : i+3])
	}
	return b.String()
}

// priorityLabel converts a numeric priority to a label.
func priorityLabel(p int) string {
	switch p {
	case 0:
		return "creative"
	case 10:
		return "normal"
	case 20:
		return "high"
	default:
		return strconv.Itoa(p)
	}
}

// truncate clips a string to max rune length, adding "..." if clipped.
func truncate(s string, max int) string {
	if utf8.RuneCountInString(s) <= max {
		return s
	}
	runes := []rune(s)
	return string(runes[:max-3]) + "..."
}

// ---------------------------------------------------------------------------
// Table renderer
// ---------------------------------------------------------------------------

type table struct {
	headers []string
	rows    [][]string
}

// renderTable draws a Unicode box-drawing table.
// Each cell value may include ANSI codes; widths are computed on visible chars.
func renderTable(t table) string {
	// Compute visible width for a string (strip ANSI).
	visibleLen := func(s string) int {
		stripped := stripANSI(s)
		return utf8.RuneCountInString(stripped)
	}

	widths := make([]int, len(t.headers))
	for i, h := range t.headers {
		widths[i] = visibleLen(h)
	}
	for _, row := range t.rows {
		for i, cell := range row {
			if i < len(widths) {
				w := visibleLen(cell)
				if w > widths[i] {
					widths[i] = w
				}
			}
		}
	}

	var b strings.Builder

	// Top border.
	b.WriteString("  ┌")
	for i, w := range widths {
		b.WriteString(strings.Repeat("─", w+2))
		if i < len(widths)-1 {
			b.WriteString("┬")
		}
	}
	b.WriteString("┐\n")

	// Header row.
	b.WriteString("  │")
	for i, h := range t.headers {
		bolded := bold(h)
		vis := visibleLen(bolded)
		pad := widths[i] - vis
		if pad < 0 {
			pad = 0
		}
		b.WriteString(" ")
		b.WriteString(bolded)
		b.WriteString(strings.Repeat(" ", pad))
		b.WriteString(" │")
	}
	b.WriteString("\n")

	// Header separator.
	b.WriteString("  ├")
	for i, w := range widths {
		b.WriteString(strings.Repeat("─", w+2))
		if i < len(widths)-1 {
			b.WriteString("┼")
		}
	}
	b.WriteString("┤\n")

	// Data rows.
	for _, row := range t.rows {
		b.WriteString("  │")
		for i, w := range widths {
			cell := ""
			if i < len(row) {
				cell = row[i]
			}
			vis := visibleLen(cell)
			pad := w - vis
			if pad < 0 {
				pad = 0
			}
			b.WriteString(" ")
			b.WriteString(cell)
			b.WriteString(strings.Repeat(" ", pad))
			b.WriteString(" │")
		}
		b.WriteString("\n")
	}

	// Bottom border.
	b.WriteString("  └")
	for i, w := range widths {
		b.WriteString(strings.Repeat("─", w+2))
		if i < len(widths)-1 {
			b.WriteString("┴")
		}
	}
	b.WriteString("┘\n")

	return b.String()
}

// stripANSI removes ANSI escape sequences from s.
func stripANSI(s string) string {
	var b strings.Builder
	i := 0
	for i < len(s) {
		if s[i] == '\033' && i+1 < len(s) && s[i+1] == '[' {
			// skip until 'm'
			j := i + 2
			for j < len(s) && s[j] != 'm' {
				j++
			}
			i = j + 1
			continue
		}
		b.WriteByte(s[i])
		i++
	}
	return b.String()
}

// ---------------------------------------------------------------------------
// HTTP client
// ---------------------------------------------------------------------------

var controllerURL string

func apiURL(path string) string {
	base := strings.TrimRight(controllerURL, "/")
	return base + path
}

func apiGet(path string, query url.Values) (*http.Response, error) {
	u := apiURL(path)
	if len(query) > 0 {
		u += "?" + query.Encode()
	}
	resp, err := http.Get(u) //nolint:noctx
	if err != nil {
		return nil, err
	}
	return resp, nil
}

func apiPost(path string, body any) (*http.Response, error) {
	data, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	resp, err := http.Post(apiURL(path), "application/json", bytes.NewReader(data)) //nolint:noctx
	if err != nil {
		return nil, err
	}
	return resp, nil
}

// connectionError prints a friendly error for network failures.
func connectionError(err error) {
	fmt.Fprintf(os.Stderr, "  %s: cannot reach controller at %s (%s)\n",
		red("error"), controllerURL, briefError(err))
	fmt.Fprintf(os.Stderr, "  %s: is the controller running? try: kubectl port-forward svc/controller 8080:8080 -n claude-os\n",
		dim("hint"))
}

// briefError extracts a short, human-readable error message.
func briefError(err error) string {
	s := err.Error()
	// For "connect: connection refused" style messages, grab from "connect:" onward.
	if idx := strings.Index(s, "connect: "); idx >= 0 {
		return strings.TrimSpace(s[idx:])
	}
	// For other network errors, trim Go URL boilerplate.
	if idx := strings.Index(s, ": "); idx >= 0 {
		// Take the last segment which is usually the most useful.
		for {
			rest := s[idx+2:]
			next := strings.Index(rest, ": ")
			if next < 0 {
				return strings.TrimSpace(rest)
			}
			idx = idx + 2 + next
		}
	}
	return s
}

// apiError holds a JSON error response from the controller.
type apiError struct {
	Error   string `json:"error"`
	Message string `json:"message"`
}

func readAPIError(resp *http.Response) string {
	var ae apiError
	if err := json.NewDecoder(resp.Body).Decode(&ae); err == nil && ae.Message != "" {
		return ae.Message
	}
	return resp.Status
}

// ---------------------------------------------------------------------------
// Protocol types
// ---------------------------------------------------------------------------

type StatusResponse struct {
	Controller struct {
		Version string `json:"version"`
	} `json:"controller"`
	Queue struct {
		Pending int `json:"pending"`
		Running int `json:"running"`
		Blocked int `json:"blocked"`
	} `json:"queue"`
	Governance struct {
		TokensUsedToday  int64   `json:"tokens_used_today"`
		TokensLimitToday int64   `json:"tokens_limit_today"`
		BurstSpendToday  float64 `json:"burst_spend_today"`
		BurstBudgetToday float64 `json:"burst_budget_today"`
	} `json:"governance"`
	Agents  map[string]AgentStatus `json:"agents"`
	Running []RunningTask          `json:"running"`
	Pending []PendingTask          `json:"pending"`
	Recent  []RecentTask           `json:"recent"`
}

type AgentStatus struct {
	Status          string    `json:"status"`
	RateLimitedUntil *time.Time `json:"rate_limited_until,omitempty"`
}

type RunningTask struct {
	ID        string    `json:"id"`
	Title     string    `json:"title"`
	Agent     string    `json:"agent"`
	Profile   string    `json:"profile"`
	StartedAt time.Time `json:"started_at"`
}

type PendingTask struct {
	ID        string    `json:"id"`
	Title     string    `json:"title"`
	Priority  int       `json:"priority"`
	Profile   string    `json:"profile"`
	CreatedAt time.Time `json:"created_at"`
}

type RecentTask struct {
	ID              string    `json:"id"`
	Title           string    `json:"title"`
	Outcome         string    `json:"outcome"`
	DurationSeconds int64     `json:"duration_seconds"`
	FinishedAt      time.Time `json:"finished_at"`
}

type TaskDetail struct {
	ID              string          `json:"id"`
	Title           string          `json:"title"`
	Description     string          `json:"description"`
	TargetRepo      string          `json:"target_repo"`
	Profile         string          `json:"profile"`
	Agent           string          `json:"agent,omitempty"`
	Model           string          `json:"model,omitempty"`
	Priority        int             `json:"priority"`
	Status          string          `json:"status"`
	TaskType        string          `json:"task_type,omitempty"`
	PlanID          string          `json:"plan_id,omitempty"`
	DependsOn       []string        `json:"depends_on,omitempty"`
	CreatedAt       time.Time       `json:"created_at"`
	StartedAt       *time.Time      `json:"started_at,omitempty"`
	FinishedAt      *time.Time      `json:"finished_at,omitempty"`
	TokensUsed      int64           `json:"tokens_used,omitempty"`
	DurationSeconds int64           `json:"duration_seconds,omitempty"`
	Result          *TaskResult     `json:"result,omitempty"`
	PlanProgress    *PlanProgress   `json:"plan_progress,omitempty"`
}

type TaskResult struct {
	Outcome   string     `json:"outcome"`
	Summary   string     `json:"summary"`
	Artifacts []Artifact `json:"artifacts,omitempty"`
}

type Artifact struct {
	Type string `json:"type"`
	Path string `json:"path"`
}

type PlanProgress struct {
	Completed int `json:"completed"`
	Total     int `json:"total"`
}

type LogResponse struct {
	TaskID  string     `json:"task_id"`
	Status  string     `json:"status"`
	Lines   []LogEntry `json:"lines"`
	Message string     `json:"message,omitempty"`
}

type LogEntry struct {
	TS   *time.Time `json:"ts,omitempty"`
	Text string     `json:"text"`
}

type CreateTaskRequest struct {
	Title       string   `json:"title"`
	Description string   `json:"description,omitempty"`
	TargetRepo  string   `json:"target_repo"`
	Profile     string   `json:"profile,omitempty"`
	Priority    string   `json:"priority,omitempty"`
	Agent       string   `json:"agent,omitempty"`
	ContextRefs []string `json:"context_refs,omitempty"`
}

type CreateTaskResponse struct {
	ID            string    `json:"id"`
	Title         string    `json:"title"`
	Status        string    `json:"status"`
	QueuePosition int       `json:"queue_position"`
	CreatedAt     time.Time `json:"created_at"`
}

// ---------------------------------------------------------------------------
// cos status
// ---------------------------------------------------------------------------

func runStatus(args []string) int {
	fs := flag.NewFlagSet("status", flag.ContinueOnError)
	jsonOut := fs.Bool("json", false, "output as JSON")
	recent := fs.Int("recent", 5, "number of recent tasks to show")
	fs.Usage = func() {
		fmt.Fprintln(os.Stderr, "usage: cos status [--json] [--recent N]")
	}
	if err := fs.Parse(args); err != nil {
		return 1
	}

	q := url.Values{}
	q.Set("recent", strconv.Itoa(*recent))

	resp, err := apiGet("/api/v1/status", q)
	if err != nil {
		connectionError(err)
		return 2
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "  %s: controller returned %s\n", red("error"), resp.Status)
		return 2
	}

	var status StatusResponse
	if err := json.NewDecoder(resp.Body).Decode(&status); err != nil {
		fmt.Fprintf(os.Stderr, "  %s: failed to parse response: %v\n", red("error"), err)
		return 2
	}

	if *jsonOut {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "")
		_ = enc.Encode(status)
		return 0
	}

	printStatus(status, *recent)
	return 0
}

func printStatus(s StatusResponse, recentN int) {
	version := s.Controller.Version
	if version == "" {
		version = "unknown"
	}

	// Header
	title := bold("Claude OS")
	verStr := dim("controller v" + version)
	fmt.Println()
	fmt.Printf("  %s  %s\n", title, verStr)
	fmt.Printf("  %s\n", strings.Repeat("─", 55))
	fmt.Println()

	// Queue summary
	queueStr := fmt.Sprintf("%s pending · %s running · %s blocked",
		bold(strconv.Itoa(s.Queue.Pending)),
		bold(strconv.Itoa(s.Queue.Running)),
		bold(strconv.Itoa(s.Queue.Blocked)))
	if s.Queue.Pending == 0 && s.Queue.Running == 0 && s.Queue.Blocked == 0 {
		queueStr = dim("empty")
	}
	fmt.Printf("  %-12s %s\n", "Queue", queueStr)

	// Token summary
	tokenStr := "n/a"
	if s.Governance.TokensLimitToday > 0 {
		pct := int(100 * s.Governance.TokensUsedToday / s.Governance.TokensLimitToday)
		tokenStr = fmt.Sprintf("%s / %s today (%d%%)",
			commaInt(s.Governance.TokensUsedToday),
			commaInt(s.Governance.TokensLimitToday),
			pct)
	}
	fmt.Printf("  %-12s %s\n", "Tokens", tokenStr)

	// Agent summary
	agentParts := make([]string, 0, len(s.Agents))
	// Stable ordering: prefer known agents first.
	known := []string{"claude", "codex", "gemini"}
	seen := map[string]bool{}
	for _, name := range known {
		if ag, ok := s.Agents[name]; ok {
			seen[name] = true
			agentParts = append(agentParts, formatAgentStatus(name, ag))
		}
	}
	for name, ag := range s.Agents {
		if !seen[name] {
			agentParts = append(agentParts, formatAgentStatus(name, ag))
		}
	}
	agentStr := strings.Join(agentParts, " · ")
	if agentStr == "" {
		agentStr = dim("none configured")
	}
	fmt.Printf("  %-12s %s\n", "Agents", agentStr)
	fmt.Println()

	// Running table
	if len(s.Running) > 0 {
		fmt.Printf("  %s\n", bold("Running"))
		rows := make([][]string, len(s.Running))
		for i, t := range s.Running {
			dur := "-"
			if !t.StartedAt.IsZero() {
				dur = humanDuration(time.Since(t.StartedAt))
			}
			rows[i] = []string{
				cyan(truncate(t.ID, 22)),
				t.Agent,
				t.Profile,
				dur,
			}
		}
		fmt.Print(renderTable(table{
			headers: []string{"Task", "Agent", "Profile", "Duration"},
			rows:    rows,
		}))
		fmt.Println()
	}

	// Pending table
	if len(s.Pending) > 0 {
		fmt.Printf("  %s\n", bold("Pending"))
		rows := make([][]string, len(s.Pending))
		for i, t := range s.Pending {
			wait := "-"
			if !t.CreatedAt.IsZero() {
				wait = humanDuration(time.Since(t.CreatedAt))
			}
			rows[i] = []string{
				yellow(truncate(t.ID, 22)),
				priorityLabel(t.Priority),
				t.Profile,
				wait,
			}
		}
		fmt.Print(renderTable(table{
			headers: []string{"Task", "Priority", "Profile", "Waiting"},
			rows:    rows,
		}))
		fmt.Println()
	}

	// Recent table
	if len(s.Recent) > 0 {
		fmt.Printf("  %s (last %d)\n", bold("Recent"), recentN)
		rows := make([][]string, len(s.Recent))
		for i, t := range s.Recent {
			dur := "-"
			if t.DurationSeconds > 0 {
				dur = humanDurationSeconds(t.DurationSeconds)
			}
			finished := "-"
			if !t.FinishedAt.IsZero() {
				finished = relativeTime(t.FinishedAt)
			}
			rows[i] = []string{
				truncate(t.ID, 22),
				outcomeColor(t.Outcome),
				dur,
				dim(finished),
			}
		}
		fmt.Print(renderTable(table{
			headers: []string{"Task", "Outcome", "Duration", "Finished"},
			rows:    rows,
		}))
		fmt.Println()
	}

	// Empty state
	if len(s.Running) == 0 && len(s.Recent) == 0 {
		fmt.Printf("  %s\n", dim("No running tasks. No recent activity."))
		fmt.Println()
	}
}

func formatAgentStatus(name string, ag AgentStatus) string {
	statusStr := agentStatusColor(ag.Status)
	if ag.Status == "rate_limited" && ag.RateLimitedUntil != nil {
		remaining := time.Until(*ag.RateLimitedUntil)
		if remaining > 0 {
			statusStr += dim(fmt.Sprintf(" (%s remaining)", humanDuration(remaining)))
		}
	}
	return name + ": " + statusStr
}

// ---------------------------------------------------------------------------
// cos log
// ---------------------------------------------------------------------------

func runLog(args []string) int {
	fs := flag.NewFlagSet("log", flag.ContinueOnError)
	jsonOut := fs.Bool("json", false, "output as NDJSON")
	tail := fs.Int("tail", 0, "show only last N lines (0 = all)")
	noFollow := fs.Bool("no-follow", false, "do not stream running tasks")
	fs.Usage = func() {
		fmt.Fprintln(os.Stderr, "usage: cos log <task-id> [--json] [--tail N] [--no-follow]")
	}
	if err := fs.Parse(args); err != nil {
		return 1
	}
	if fs.NArg() < 1 {
		fmt.Fprintln(os.Stderr, "  "+red("error")+": task ID required")
		fmt.Fprintln(os.Stderr, "  "+dim("usage")+": cos log <task-id>")
		return 1
	}
	taskID := fs.Arg(0)

	q := url.Values{}
	if *tail > 0 {
		q.Set("tail", strconv.Itoa(*tail))
	}

	// First, check if task is running (to decide whether to stream).
	// We do a non-streaming fetch and inspect the status.
	// If running and not --no-follow, switch to streaming.
	q.Set("follow", "false")

	resp, err := apiGet("/api/v1/tasks/"+taskID+"/logs", q)
	if err != nil {
		connectionError(err)
		return 2
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		fmt.Fprintf(os.Stderr, "  %s: task %q not found\n", red("error"), taskID)
		return 2
	}
	if resp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "  %s: %s\n", red("error"), readAPIError(resp))
		return 2
	}

	var logResp LogResponse
	if err := json.NewDecoder(resp.Body).Decode(&logResp); err != nil {
		fmt.Fprintf(os.Stderr, "  %s: failed to parse response: %v\n", red("error"), err)
		return 2
	}

	if logResp.Status == "running" && !*noFollow {
		// Stream via SSE.
		return streamLogs(taskID, *tail, *jsonOut)
	}

	if *jsonOut {
		enc := json.NewEncoder(os.Stdout)
		for _, line := range logResp.Lines {
			_ = enc.Encode(line)
		}
		return 0
	}

	// Human-readable log output.
	printLogHeader(taskID, logResp)
	for _, line := range logResp.Lines {
		printLogLine(line)
	}
	if logResp.Message != "" {
		fmt.Printf("\n  %s\n", dim(logResp.Message))
	}
	if logResp.Status == "completed" || logResp.Status == "failed" {
		fmt.Printf("\n  %s: %s\n", dim("Result"), statusColor(logResp.Status))
	}
	return 0
}

func printLogHeader(taskID string, r LogResponse) {
	status := statusColor(r.Status)
	fmt.Printf("  %s (%s)\n", bold(taskID), status)
	fmt.Printf("  %s\n", strings.Repeat("─", 40))
}

func printLogLine(line LogEntry) {
	ts := ""
	if line.TS != nil {
		ts = dim("["+line.TS.UTC().Format("2006-01-02 15:04:05")+"] ")
	}
	fmt.Printf("  %s%s\n", ts, line.Text)
}

func streamLogs(taskID string, tailN int, jsonOut bool) int {
	q := url.Values{}
	q.Set("follow", "true")
	if tailN > 0 {
		q.Set("tail", strconv.Itoa(tailN))
	}

	resp, err := apiGet("/api/v1/tasks/"+taskID+"/logs", q)
	if err != nil {
		connectionError(err)
		return 2
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "  %s: %s\n", red("error"), readAPIError(resp))
		return 2
	}

	if !jsonOut {
		fmt.Printf("  %s (%s)\n", bold(taskID), cyan("running"))
		fmt.Printf("  %s\n", strings.Repeat("─", 40))
	}

	// Parse SSE stream line by line.
	scanner := bufio.NewScanner(resp.Body)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "event: done") {
			// Next data line has final status.
			if scanner.Scan() {
				data := strings.TrimPrefix(scanner.Text(), "data: ")
				if jsonOut {
					fmt.Println(data)
				} else {
					fmt.Printf("\n  %s\n", dim("(stream ended)"))
				}
			}
			break
		}
		if !strings.HasPrefix(line, "data: ") {
			continue
		}
		data := strings.TrimPrefix(line, "data: ")
		if jsonOut {
			fmt.Println(data)
			continue
		}
		var entry LogEntry
		if err := json.Unmarshal([]byte(data), &entry); err != nil {
			fmt.Printf("  %s\n", data)
			continue
		}
		printLogLine(entry)
	}

	if !jsonOut {
		fmt.Printf("  %s\n", dim("(streaming — ctrl-c to stop)"))
	}
	return 0
}

// ---------------------------------------------------------------------------
// cos task
// ---------------------------------------------------------------------------

func runTask(args []string) int {
	fs := flag.NewFlagSet("task", flag.ContinueOnError)
	jsonOut := fs.Bool("json", false, "output as JSON")
	fs.Usage = func() {
		fmt.Fprintln(os.Stderr, "usage: cos task <task-id> [--json]")
	}
	if err := fs.Parse(args); err != nil {
		return 1
	}
	if fs.NArg() < 1 {
		fmt.Fprintln(os.Stderr, "  "+red("error")+": task ID required")
		fmt.Fprintln(os.Stderr, "  "+dim("usage")+": cos task <task-id>")
		return 1
	}
	taskID := fs.Arg(0)

	resp, err := apiGet("/api/v1/tasks/"+taskID, nil)
	if err != nil {
		connectionError(err)
		return 2
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		fmt.Fprintf(os.Stderr, "  %s: task %q not found\n", red("error"), taskID)
		return 2
	}
	if resp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "  %s: %s\n", red("error"), readAPIError(resp))
		return 2
	}

	var task TaskDetail
	if err := json.NewDecoder(resp.Body).Decode(&task); err != nil {
		fmt.Fprintf(os.Stderr, "  %s: failed to parse response: %v\n", red("error"), err)
		return 2
	}

	if *jsonOut {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "")
		_ = enc.Encode(task)
		return 0
	}

	printTaskDetail(task)
	return 0
}

func printTaskDetail(t TaskDetail) {
	fmt.Println()
	fmt.Printf("  %s\n", bold(t.ID))
	fmt.Printf("  %s\n", strings.Repeat("─", 40))

	// Status line
	statusStr := statusColor(t.Status)
	if t.Result != nil && t.Result.Outcome != "" {
		statusStr += " (" + outcomeColor(t.Result.Outcome) + ")"
	}
	fmt.Printf("  %-14s %s\n", "Status:", statusStr)

	if t.Profile != "" {
		model := ""
		if t.Model != "" {
			model = dim(" (" + t.Model + ")")
		}
		fmt.Printf("  %-14s %s%s\n", "Profile:", t.Profile, model)
	}
	if t.Agent != "" {
		fmt.Printf("  %-14s %s\n", "Agent:", t.Agent)
	}
	if t.PlanID != "" {
		planStr := t.PlanID
		if t.PlanProgress != nil {
			planStr += fmt.Sprintf(" (%d/%d complete)", t.PlanProgress.Completed, t.PlanProgress.Total)
		}
		fmt.Printf("  %-14s %s\n", "Plan:", dim(planStr))
	}

	fmt.Printf("  %-14s %s\n", "Created:", dim(t.CreatedAt.UTC().Format("2006-01-02 15:04:05 UTC")))
	if t.StartedAt != nil && !t.StartedAt.IsZero() {
		fmt.Printf("  %-14s %s\n", "Started:", dim(t.StartedAt.UTC().Format("2006-01-02 15:04:05 UTC")))
	}
	if t.FinishedAt != nil && !t.FinishedAt.IsZero() {
		fmt.Printf("  %-14s %s\n", "Finished:", dim(t.FinishedAt.UTC().Format("2006-01-02 15:04:05 UTC")))
	}
	if t.DurationSeconds > 0 {
		fmt.Printf("  %-14s %s\n", "Duration:", humanDurationSeconds(t.DurationSeconds))
	}
	if t.TokensUsed > 0 {
		fmt.Printf("  %-14s %s\n", "Tokens:", commaInt(t.TokensUsed))
	}

	if t.Result != nil {
		if len(t.Result.Artifacts) > 0 {
			fmt.Println()
			fmt.Printf("  %s\n", bold("Artifacts"))
			for _, a := range t.Result.Artifacts {
				fmt.Printf("  - %s: %s\n", a.Type, a.Path)
			}
		}
		if t.Result.Summary != "" {
			fmt.Println()
			fmt.Printf("  %s\n", bold("Summary"))
			fmt.Printf("  %s\n", t.Result.Summary)
		}
	}
	fmt.Println()
}

// ---------------------------------------------------------------------------
// cos run
// ---------------------------------------------------------------------------

// splitPositional separates flag args from positional args so that flags can
// appear anywhere (before or after the positional title argument).
// stringFlagNames is the set of flag names whose next token is a value.
func splitPositional(args []string, stringFlagNames map[string]bool) (flagArgs, positionalArgs []string) {
	i := 0
	for i < len(args) {
		arg := args[i]
		if !strings.HasPrefix(arg, "-") {
			positionalArgs = append(positionalArgs, arg)
			i++
			continue
		}
		flagArgs = append(flagArgs, arg)
		// Strip leading dashes and any embedded =value.
		name := strings.TrimLeft(arg, "-")
		if idx := strings.Index(name, "="); idx >= 0 {
			// --flag=value — value is already embedded, no separate token.
			name = name[:idx]
		} else if stringFlagNames[name] && i+1 < len(args) {
			// --flag value — consume the next token as the flag value.
			i++
			flagArgs = append(flagArgs, args[i])
		}
		i++
	}
	return
}

func runRun(args []string) int {
	fs := flag.NewFlagSet("run", flag.ContinueOnError)
	jsonOut := fs.Bool("json", false, "output as JSON")
	repo := fs.String("repo", "", "target repository (required)")
	profile := fs.String("profile", "small", "resource profile: small, medium, large, burst, think")
	priority := fs.String("priority", "normal", "priority: creative, normal, high")
	agent := fs.String("agent", "", "force agent: claude, codex, gemini")
	description := fs.String("d", "", "task description (default: same as title)")
	fs.StringVar(description, "description", "", "task description (default: same as title)")
	fs.Usage = func() {
		fmt.Fprintln(os.Stderr, "usage: cos run <title> [--repo <repo>] [--profile <profile>] [--priority <priority>]")
		fmt.Fprintln(os.Stderr, "       [--agent <agent>] [--description <desc>] [--json]")
	}

	// Pre-split so flags can appear before or after the title positional arg.
	stringFlags := map[string]bool{
		"repo": true, "profile": true, "priority": true, "agent": true,
		"d": true, "description": true,
	}
	flagArgs, positionalArgs := splitPositional(args, stringFlags)
	if err := fs.Parse(flagArgs); err != nil {
		return 1
	}

	if len(positionalArgs) < 1 {
		fmt.Fprintln(os.Stderr, "  "+red("error")+": task title required")
		fmt.Fprintln(os.Stderr, "  "+dim("usage")+": cos run <title> --repo <owner/repo>")
		return 1
	}
	title := strings.Join(positionalArgs, " ")

	if *repo == "" {
		fmt.Fprintln(os.Stderr, "  "+red("error")+": --repo is required")
		fmt.Fprintln(os.Stderr, "  "+dim("hint")+": e.g. --repo github.com/dacort/claude-os")
		return 1
	}

	validProfiles := map[string]bool{"small": true, "medium": true, "large": true, "burst": true, "think": true}
	if !validProfiles[*profile] {
		fmt.Fprintf(os.Stderr, "  %s: invalid profile %q. Valid profiles: small, medium, large, burst, think\n",
			red("error"), *profile)
		return 1
	}

	validPriorities := map[string]bool{"creative": true, "normal": true, "high": true}
	if !validPriorities[*priority] {
		fmt.Fprintf(os.Stderr, "  %s: invalid priority %q. Valid priorities: creative, normal, high\n",
			red("error"), *priority)
		return 1
	}

	if *agent != "" {
		validAgents := map[string]bool{"claude": true, "codex": true, "gemini": true}
		if !validAgents[*agent] {
			fmt.Fprintf(os.Stderr, "  %s: invalid agent %q. Valid agents: claude, codex, gemini\n",
				red("error"), *agent)
			return 1
		}
	}

	req := CreateTaskRequest{
		Title:      title,
		TargetRepo: *repo,
		Profile:    *profile,
		Priority:   *priority,
		Agent:      *agent,
	}
	if *description != "" {
		req.Description = *description
	}

	resp, err := apiPost("/api/v1/tasks", req)
	if err != nil {
		connectionError(err)
		return 2
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		msg := readAPIError(resp)
		fmt.Fprintf(os.Stderr, "  %s: %s\n", red("error"), msg)
		return 2
	}

	var created CreateTaskResponse
	if err := json.NewDecoder(resp.Body).Decode(&created); err != nil {
		fmt.Fprintf(os.Stderr, "  %s: failed to parse response: %v\n", red("error"), err)
		return 2
	}

	if *jsonOut {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "")
		_ = enc.Encode(created)
		return 0
	}

	fmt.Printf("  Created task: %s\n", bold(created.ID))
	pos := ""
	if created.QueuePosition > 0 {
		pos = fmt.Sprintf(" (position %d in queue)", created.QueuePosition)
	}
	fmt.Printf("  Status: %s%s\n", yellow("pending"), dim(pos))
	return 0
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

func usage() {
	fmt.Fprintln(os.Stderr, "cos — terminal interface for Claude OS")
	fmt.Fprintln(os.Stderr)
	fmt.Fprintln(os.Stderr, "Usage:")
	fmt.Fprintln(os.Stderr, "  cos status             system snapshot (queue, tokens, agents)")
	fmt.Fprintln(os.Stderr, "  cos log <task-id>      fetch or stream task logs")
	fmt.Fprintln(os.Stderr, "  cos task <task-id>     detailed info for a single task")
	fmt.Fprintln(os.Stderr, "  cos run <title>        create and enqueue a new task")
	fmt.Fprintln(os.Stderr)
	fmt.Fprintln(os.Stderr, "Flags (all subcommands):")
	fmt.Fprintln(os.Stderr, "  --json                 machine-readable JSON output")
	fmt.Fprintln(os.Stderr)
	fmt.Fprintln(os.Stderr, "Environment:")
	fmt.Fprintln(os.Stderr, "  CONTROLLER_URL         controller base URL (default: http://localhost:8080)")
	fmt.Fprintln(os.Stderr, "  NO_COLOR               disable ANSI colors when set")
}

func main() {
	controllerURL = os.Getenv("CONTROLLER_URL")
	if controllerURL == "" {
		controllerURL = "http://localhost:8080"
	}
	noColor = os.Getenv("NO_COLOR") != ""

	if len(os.Args) < 2 {
		usage()
		os.Exit(1)
	}

	cmd := os.Args[1]
	rest := os.Args[2:]

	var code int
	switch cmd {
	case "status":
		code = runStatus(rest)
	case "log":
		code = runLog(rest)
	case "task":
		code = runTask(rest)
	case "run":
		code = runRun(rest)
	case "help", "--help", "-h":
		usage()
		code = 0
	case "--version", "version":
		fmt.Println("cos dev")
		code = 0
	default:
		fmt.Fprintf(os.Stderr, "  %s: unknown command %q\n", red("error"), cmd)
		fmt.Fprintf(os.Stderr, "  %s: run 'cos help' for available commands\n", dim("hint"))
		code = 1
	}

	os.Exit(code)
}

// Ensure io is used (bufio and bytes use it indirectly).
var _ = io.EOF
