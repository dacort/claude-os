// Command cos is the terminal interface for Claude OS.
// It speaks to the controller's /api/v1/* endpoints and renders clean,
// human-readable output with ANSI colors.
//
// Usage:
//
//	cos status [--json] [--recent N]
//	cos task <id> [--json]
//	cos log <id> [--json] [--tail N] [--no-follow]
//	cos run <title> --repo <owner/repo> [flags]
//
// Environment:
//
//	CONTROLLER_URL  base URL of the controller (default: http://localhost:8080)
//	NO_COLOR        set to any value to disable ANSI colors
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"
)

// ─── ANSI colors ──────────────────────────────────────────────────────────────

var noColor = os.Getenv("NO_COLOR") != "" || os.Getenv("TERM") == "dumb"

func colorize(code, s string) string {
	if noColor {
		return s
	}
	return "\033[" + code + "m" + s + "\033[0m"
}

func green(s string) string  { return colorize("32", s) }
func red(s string) string    { return colorize("31", s) }
func yellow(s string) string { return colorize("33", s) }
func cyan(s string) string   { return colorize("36", s) }
func dim(s string) string    { return colorize("2", s) }
func bold(s string) string   { return colorize("1", s) }

// ─── HTTP client ──────────────────────────────────────────────────────────────

var controllerURL = func() string {
	if v := os.Getenv("CONTROLLER_URL"); v != "" {
		return strings.TrimRight(v, "/")
	}
	return "http://localhost:8080"
}()

var httpClient = &http.Client{Timeout: 15 * time.Second}

func apiGet(path string) (*http.Response, error) {
	return httpClient.Get(controllerURL + path)
}

func apiPost(path string, body []byte) (*http.Response, error) {
	return httpClient.Post(controllerURL+path, "application/json", bytes.NewReader(body))
}

// ─── JSON types (mirror cosapi response shapes) ───────────────────────────────

type statusResponse struct {
	Controller controllerInfo       `json:"controller"`
	Queue      queueStats           `json:"queue"`
	Governance governanceStats      `json:"governance"`
	Agents     map[string]agentInfo `json:"agents"`
	Running    []runningSummary     `json:"running"`
	Pending    []pendingSummary     `json:"pending"`
	Recent     []recentSummary      `json:"recent"`
}

type controllerInfo struct {
	Version string `json:"version"`
}

type queueStats struct {
	Pending int64 `json:"pending"`
	Running int64 `json:"running"`
	Blocked int64 `json:"blocked"`
}

type governanceStats struct {
	TokensUsedToday  int64   `json:"tokens_used_today"`
	TokensLimitToday int64   `json:"tokens_limit_today"`
	BurstSpendToday  float64 `json:"burst_spend_today"`
	BurstBudgetToday float64 `json:"burst_budget_today"`
}

type agentInfo struct {
	Status           string     `json:"status"`
	RateLimitedUntil *time.Time `json:"rate_limited_until,omitempty"`
}

type runningSummary struct {
	ID        string     `json:"id"`
	Title     string     `json:"title"`
	Agent     string     `json:"agent,omitempty"`
	Profile   string     `json:"profile,omitempty"`
	StartedAt *time.Time `json:"started_at,omitempty"`
}

type pendingSummary struct {
	ID        string     `json:"id"`
	Title     string     `json:"title"`
	Priority  int        `json:"priority"`
	Profile   string     `json:"profile,omitempty"`
	CreatedAt *time.Time `json:"created_at,omitempty"`
}

type recentSummary struct {
	ID              string     `json:"id"`
	Title           string     `json:"title"`
	Outcome         string     `json:"outcome,omitempty"`
	DurationSeconds int64      `json:"duration_seconds,omitempty"`
	FinishedAt      *time.Time `json:"finished_at,omitempty"`
}

type taskDetailResponse struct {
	ID              string        `json:"id"`
	Title           string        `json:"title"`
	Description     string        `json:"description,omitempty"`
	TargetRepo      string        `json:"target_repo,omitempty"`
	Profile         string        `json:"profile,omitempty"`
	Agent           string        `json:"agent,omitempty"`
	Model           string        `json:"model,omitempty"`
	Priority        int           `json:"priority"`
	Status          string        `json:"status"`
	TaskType        string        `json:"task_type,omitempty"`
	PlanID          string        `json:"plan_id,omitempty"`
	DependsOn       []string      `json:"depends_on,omitempty"`
	CreatedAt       time.Time     `json:"created_at"`
	StartedAt       *time.Time    `json:"started_at,omitempty"`
	FinishedAt      *time.Time    `json:"finished_at,omitempty"`
	TokensUsed      int64         `json:"tokens_used,omitempty"`
	DurationSeconds int64         `json:"duration_seconds,omitempty"`
	Result          *taskResult   `json:"result,omitempty"`
	PlanProgress    *planProgress `json:"plan_progress,omitempty"`
}

type taskResult struct {
	Outcome   string     `json:"outcome,omitempty"`
	Summary   string     `json:"summary,omitempty"`
	Artifacts []artifact `json:"artifacts,omitempty"`
}

type artifact struct {
	Type string `json:"type"`
	Path string `json:"path"`
}

type planProgress struct {
	Completed int `json:"completed"`
	Total     int `json:"total"`
}

type logLine struct {
	TS   *time.Time `json:"ts,omitempty"`
	Text string     `json:"text"`
}

type logsResponse struct {
	TaskID  string    `json:"task_id"`
	Status  string    `json:"status"`
	Lines   []logLine `json:"lines"`
	Message string    `json:"message,omitempty"`
}

type createTaskRequest struct {
	Title       string   `json:"title"`
	Description string   `json:"description,omitempty"`
	TargetRepo  string   `json:"target_repo"`
	Profile     string   `json:"profile,omitempty"`
	Priority    string   `json:"priority,omitempty"`
	Agent       string   `json:"agent,omitempty"`
	Model       string   `json:"model,omitempty"`
	ContextRefs []string `json:"context_refs,omitempty"`
}

type createTaskResponse struct {
	ID            string    `json:"id"`
	Title         string    `json:"title"`
	Status        string    `json:"status"`
	QueuePosition int       `json:"queue_position"`
	CreatedAt     time.Time `json:"created_at"`
}

type apiError struct {
	Error   string `json:"error"`
	Message string `json:"message"`
}

// ─── Formatting helpers ───────────────────────────────────────────────────────

// formatNumber formats an int64 with comma separators: 42180 → "42,180".
func formatNumber(n int64) string {
	s := strconv.FormatInt(n, 10)
	if len(s) <= 3 {
		return s
	}
	result := make([]byte, 0, len(s)+4)
	for i, c := range s {
		if i > 0 && (len(s)-i)%3 == 0 {
			result = append(result, ',')
		}
		result = append(result, byte(c))
	}
	return string(result)
}

// formatDuration renders seconds as a human-readable string: "2m 30s", "1h 12m".
func formatDuration(seconds int64) string {
	if seconds <= 0 {
		return "—"
	}
	h := seconds / 3600
	m := (seconds % 3600) / 60
	s := seconds % 60
	if h > 0 {
		return fmt.Sprintf("%dh %dm", h, m)
	}
	if m > 0 {
		return fmt.Sprintf("%dm %ds", m, s)
	}
	return fmt.Sprintf("%ds", s)
}

// relativeTime returns a human-friendly relative time string ("3m ago", "2h ago",
// or an absolute timestamp for times older than 24 hours).
func relativeTime(t *time.Time) string {
	if t == nil {
		return "—"
	}
	diff := time.Since(*t)
	if diff < 0 {
		diff = -diff
	}
	switch {
	case diff < time.Minute:
		return "just now"
	case diff < time.Hour:
		return fmt.Sprintf("%dm ago", int(diff.Minutes()))
	case diff < 24*time.Hour:
		return fmt.Sprintf("%dh ago", int(diff.Hours()))
	default:
		return t.UTC().Format("2006-01-02 15:04 UTC")
	}
}

// elapsedTime returns the time elapsed since t (for showing running/waiting duration).
func elapsedTime(t *time.Time) string {
	if t == nil {
		return "—"
	}
	return formatDuration(int64(time.Since(*t).Seconds()))
}

// truncate shortens s to at most n visible chars, appending "..." if cut.
func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n-3] + "..."
}

// padRight pads s with spaces on the right to reach width n.
func padRight(s string, n int) string {
	if len(s) >= n {
		return s
	}
	return s + strings.Repeat(" ", n-len(s))
}

// priorityLabel maps numeric priority to a human label.
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

// outcomeColor wraps an outcome string in the appropriate color.
func outcomeColor(outcome string) string {
	switch outcome {
	case "success":
		return green(outcome)
	case "failure", "failed", "error":
		return red(outcome)
	default:
		return dim(outcome)
	}
}

// statusColor wraps a status string in the appropriate color.
func statusColor(status string) string {
	switch status {
	case "running":
		return cyan(status)
	case "pending":
		return yellow(status)
	case "completed":
		return green(status)
	case "failed":
		return red(status)
	default:
		return status
	}
}

// ─── Table rendering ──────────────────────────────────────────────────────────

type tableColumn struct {
	header string
	width  int
}

func printTableHeader(cols []tableColumn) {
	// Top border
	fmt.Print("  ┌")
	for i, col := range cols {
		fmt.Print(strings.Repeat("─", col.width+2))
		if i < len(cols)-1 {
			fmt.Print("┬")
		}
	}
	fmt.Println("┐")
	// Header row
	fmt.Print("  │")
	for _, col := range cols {
		fmt.Printf(" %s │", padRight(col.header, col.width))
	}
	fmt.Println()
	// Divider
	fmt.Print("  ├")
	for i, col := range cols {
		fmt.Print(strings.Repeat("─", col.width+2))
		if i < len(cols)-1 {
			fmt.Print("┼")
		}
	}
	fmt.Println("┤")
}

func printTableRow(cols []tableColumn, values []string) {
	fmt.Print("  │")
	for i, col := range cols {
		v := ""
		if i < len(values) {
			v = values[i]
		}
		// Pad accounting for invisible ANSI bytes
		visible := visibleLen(v)
		padding := col.width - visible
		if padding < 0 {
			padding = 0
		}
		fmt.Printf(" %s%s │", v, strings.Repeat(" ", padding))
	}
	fmt.Println()
}

func printTableFooter(cols []tableColumn) {
	fmt.Print("  └")
	for i, col := range cols {
		fmt.Print(strings.Repeat("─", col.width+2))
		if i < len(cols)-1 {
			fmt.Print("┴")
		}
	}
	fmt.Println("┘")
}

// visibleLen returns the display length of s, ignoring ANSI escape sequences.
func visibleLen(s string) int {
	n := 0
	inEsc := false
	for _, r := range s {
		if r == '\033' {
			inEsc = true
			continue
		}
		if inEsc {
			if r == 'm' {
				inEsc = false
			}
			continue
		}
		n++
	}
	return n
}

// ─── Error helpers ────────────────────────────────────────────────────────────

func handleConnError(err error) {
	fmt.Fprintf(os.Stderr, "  error: cannot reach controller at %s (%s)\n",
		controllerURL, simplifyError(err))
	fmt.Fprintln(os.Stderr, "  hint: is the controller running? try: kubectl port-forward svc/controller 8080:8080 -n claude-os")
	os.Exit(2)
}

func simplifyError(err error) string {
	s := err.Error()
	switch {
	case strings.Contains(s, "connection refused"):
		return "connection refused"
	case strings.Contains(s, "no such host"):
		return "no such host"
	case strings.Contains(s, "timeout"):
		return "timeout"
	}
	if idx := strings.Index(s, ": "); idx >= 0 {
		return s[idx+2:]
	}
	return s
}

func decodeAPIError(resp *http.Response) string {
	var ae apiError
	if err := json.NewDecoder(resp.Body).Decode(&ae); err == nil && ae.Message != "" {
		return ae.Message
	}
	return resp.Status
}

func compactJSON(v any) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	enc.Encode(v) //nolint:errcheck
}

// ─── cos status ───────────────────────────────────────────────────────────────

func runStatus(args []string) {
	fs := flag.NewFlagSet("status", flag.ExitOnError)
	jsonFlag := fs.Bool("json", false, "output JSON")
	recentN := fs.Int("recent", 5, "how many recent tasks to show (max 50)")
	fs.Parse(args) //nolint:errcheck

	resp, err := apiGet(fmt.Sprintf("/api/v1/status?recent=%d", *recentN))
	if err != nil {
		handleConnError(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "  error: controller returned %s\n", resp.Status)
		os.Exit(2)
	}

	var s statusResponse
	if err := json.NewDecoder(resp.Body).Decode(&s); err != nil {
		fmt.Fprintf(os.Stderr, "  error: failed to decode response: %v\n", err)
		os.Exit(2)
	}

	if *jsonFlag {
		compactJSON(s)
		return
	}
	printStatus(s)
}

func printStatus(s statusResponse) {
	const lineWidth = 57
	sep := "  " + strings.Repeat("─", lineWidth)

	title := "Claude OS"
	versionStr := "controller v" + s.Controller.Version
	padding := lineWidth - len(title) - len(versionStr)
	if padding < 1 {
		padding = 1
	}
	fmt.Printf("\n  %s%s%s\n", bold(title), strings.Repeat(" ", padding), dim(versionStr))
	fmt.Println(dim(sep))
	fmt.Println()

	// Queue summary
	q := s.Queue
	var queueStr string
	if q.Pending+q.Running+q.Blocked == 0 {
		queueStr = dim("empty")
	} else {
		dot := dim(" · ")
		parts := make([]string, 0, 3)
		if q.Pending > 0 {
			parts = append(parts, yellow(fmt.Sprintf("%d pending", q.Pending)))
		} else {
			parts = append(parts, dim("0 pending"))
		}
		if q.Running > 0 {
			parts = append(parts, cyan(fmt.Sprintf("%d running", q.Running)))
		} else {
			parts = append(parts, dim("0 running"))
		}
		if q.Blocked > 0 {
			parts = append(parts, red(fmt.Sprintf("%d blocked", q.Blocked)))
		} else {
			parts = append(parts, dim("0 blocked"))
		}
		queueStr = strings.Join(parts, dot)
	}
	fmt.Printf("  %-12s %s\n", bold("Queue"), queueStr)

	// Token budget
	g := s.Governance
	var pct int64
	if g.TokensLimitToday > 0 {
		pct = g.TokensUsedToday * 100 / g.TokensLimitToday
	}
	tokenColor := green
	switch {
	case pct >= 80:
		tokenColor = red
	case pct >= 50:
		tokenColor = yellow
	}
	tokenStr := fmt.Sprintf("%s / %s today (%d%%)",
		tokenColor(formatNumber(g.TokensUsedToday)),
		formatNumber(g.TokensLimitToday),
		pct,
	)
	fmt.Printf("  %-12s %s\n", bold("Tokens"), tokenStr)

	// Agent health (show in stable order)
	agentOrder := []string{"claude", "codex", "gemini"}
	agentParts := make([]string, 0, len(agentOrder))
	for _, name := range agentOrder {
		info, ok := s.Agents[name]
		if !ok {
			continue
		}
		switch info.Status {
		case "ok":
			agentParts = append(agentParts, name+": "+green("ok"))
		case "rate_limited":
			extra := ""
			if info.RateLimitedUntil != nil {
				if rem := time.Until(*info.RateLimitedUntil); rem > 0 {
					extra = fmt.Sprintf(" (%dm remaining)", int(rem.Minutes()))
				}
			}
			agentParts = append(agentParts, name+": "+yellow("rate-limited")+dim(extra))
		default:
			agentParts = append(agentParts, name+": "+dim(info.Status))
		}
	}
	fmt.Printf("  %-12s %s\n", bold("Agents"), strings.Join(agentParts, dim(" · ")))
	fmt.Println()

	// Running table
	if len(s.Running) > 0 {
		fmt.Printf("  %s\n", bold("Running"))
		cols := []tableColumn{
			{"Task", 22},
			{"Agent", 10},
			{"Profile", 9},
			{"Duration", 10},
		}
		printTableHeader(cols)
		for _, t := range s.Running {
			printTableRow(cols, []string{
				truncate(t.ID, 22),
				t.Agent,
				t.Profile,
				cyan(elapsedTime(t.StartedAt)),
			})
		}
		printTableFooter(cols)
		fmt.Println()
	}

	// Pending table
	if len(s.Pending) > 0 {
		fmt.Printf("  %s\n", bold("Pending"))
		cols := []tableColumn{
			{"Task", 22},
			{"Priority", 10},
			{"Profile", 10},
			{"Waiting", 10},
		}
		printTableHeader(cols)
		for _, t := range s.Pending {
			printTableRow(cols, []string{
				truncate(t.ID, 22),
				yellow(priorityLabel(t.Priority)),
				t.Profile,
				dim(elapsedTime(t.CreatedAt)),
			})
		}
		printTableFooter(cols)
		fmt.Println()
	}

	// Recent table
	if len(s.Recent) > 0 {
		fmt.Printf("  %s\n", bold(fmt.Sprintf("Recent (last %d)", len(s.Recent))))
		cols := []tableColumn{
			{"Task", 22},
			{"Outcome", 9},
			{"Duration", 10},
			{"Finished", 12},
		}
		printTableHeader(cols)
		for _, t := range s.Recent {
			printTableRow(cols, []string{
				truncate(t.ID, 22),
				outcomeColor(t.Outcome),
				dim(formatDuration(t.DurationSeconds)),
				dim(relativeTime(t.FinishedAt)),
			})
		}
		printTableFooter(cols)
		fmt.Println()
	}

	if len(s.Running) == 0 && len(s.Recent) == 0 {
		fmt.Println("  " + dim("No running tasks. No recent activity."))
		fmt.Println()
	}
}

// ─── cos task ─────────────────────────────────────────────────────────────────

func runTask(args []string) {
	fs := flag.NewFlagSet("task", flag.ExitOnError)
	jsonFlag := fs.Bool("json", false, "output JSON")
	fs.Parse(args) //nolint:errcheck

	if fs.NArg() == 0 {
		fmt.Fprintln(os.Stderr, "  error: task ID required")
		fmt.Fprintln(os.Stderr, "  usage: cos task <task-id>")
		os.Exit(1)
	}

	taskID := fs.Arg(0)
	resp, err := apiGet("/api/v1/tasks/" + taskID)
	if err != nil {
		handleConnError(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		fmt.Fprintf(os.Stderr, "  error: task %q not found\n", taskID)
		os.Exit(1)
	}
	if resp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "  error: %s\n", decodeAPIError(resp))
		os.Exit(2)
	}

	var t taskDetailResponse
	if err := json.NewDecoder(resp.Body).Decode(&t); err != nil {
		fmt.Fprintf(os.Stderr, "  error: failed to decode response: %v\n", err)
		os.Exit(2)
	}

	if *jsonFlag {
		compactJSON(t)
		return
	}
	printTaskDetail(t)
}

func printTaskDetail(t taskDetailResponse) {
	fmt.Println()
	fmt.Printf("  %s\n", bold(t.ID))
	fmt.Printf("  %s\n", dim(strings.Repeat("─", len(t.ID))))

	field := func(label, value string) {
		fmt.Printf("  %-16s %s\n", dim(label+":"), value)
	}

	field("Status", statusColor(t.Status))

	if t.Profile != "" || t.Model != "" {
		model := t.Model
		if model == "" {
			model = "—"
		}
		field("Profile", t.Profile+" "+dim("("+model+")"))
	}
	if t.Agent != "" {
		field("Agent", t.Agent)
	}
	if t.PlanID != "" {
		planStr := t.PlanID
		if t.PlanProgress != nil {
			planStr += fmt.Sprintf(" (%d/%d complete)", t.PlanProgress.Completed, t.PlanProgress.Total)
		}
		field("Plan", planStr)
	}

	field("Created", t.CreatedAt.UTC().Format("2006-01-02 15:04:05 UTC"))
	if t.StartedAt != nil {
		field("Started", t.StartedAt.UTC().Format("2006-01-02 15:04:05 UTC"))
	}
	if t.FinishedAt != nil {
		field("Finished", t.FinishedAt.UTC().Format("2006-01-02 15:04:05 UTC"))
	}
	if t.DurationSeconds > 0 {
		field("Duration", formatDuration(t.DurationSeconds))
	}
	if t.TokensUsed > 0 {
		field("Tokens", formatNumber(t.TokensUsed)+" used")
	}

	if t.Result != nil {
		if len(t.Result.Artifacts) > 0 {
			fmt.Println()
			fmt.Printf("  %s\n", bold("Artifacts"))
			for _, a := range t.Result.Artifacts {
				fmt.Printf("  - %s: %s\n", dim(a.Type), a.Path)
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

// ─── cos log ──────────────────────────────────────────────────────────────────

func runLog(args []string) {
	fs := flag.NewFlagSet("log", flag.ExitOnError)
	jsonFlag := fs.Bool("json", false, "output JSON (NDJSON for streaming)")
	tail := fs.Int("tail", 0, "show only last N lines")
	noFollow := fs.Bool("no-follow", false, "fetch snapshot instead of streaming")
	fs.Parse(args) //nolint:errcheck

	if fs.NArg() == 0 {
		fmt.Fprintln(os.Stderr, "  error: task ID required")
		fmt.Fprintln(os.Stderr, "  usage: cos log <task-id> [--tail N] [--no-follow]")
		os.Exit(1)
	}

	taskID := fs.Arg(0)

	// Fetch task detail first (for the display header)
	taskResp, err := apiGet("/api/v1/tasks/" + taskID)
	if err != nil {
		handleConnError(err)
	}
	if taskResp.StatusCode == http.StatusNotFound {
		taskResp.Body.Close()
		fmt.Fprintf(os.Stderr, "  error: task %q not found\n", taskID)
		os.Exit(1)
	}
	var taskDetail taskDetailResponse
	json.NewDecoder(taskResp.Body).Decode(&taskDetail) //nolint:errcheck
	taskResp.Body.Close()

	// Build log endpoint URL
	urlParts := []string{"/api/v1/tasks/" + taskID + "/logs"}
	params := []string{}
	if *tail > 0 {
		params = append(params, fmt.Sprintf("tail=%d", *tail))
	}
	if !*noFollow {
		params = append(params, "follow=true")
	}
	if len(params) > 0 {
		urlParts = append(urlParts, "?"+strings.Join(params, "&"))
	}
	logPath := strings.Join(urlParts, "")

	// Use a no-timeout client for potentially streaming responses
	streamClient := &http.Client{}
	logResp, err := streamClient.Get(controllerURL + logPath)
	if err != nil {
		handleConnError(err)
	}
	defer logResp.Body.Close()

	if logResp.StatusCode == http.StatusNotFound {
		fmt.Fprintf(os.Stderr, "  error: task %q not found\n", taskID)
		os.Exit(1)
	}
	if logResp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "  error: %s\n", decodeAPIError(logResp))
		os.Exit(2)
	}

	isSSE := strings.Contains(logResp.Header.Get("Content-Type"), "text/event-stream")

	if isSSE {
		printLogStream(taskID, &taskDetail, logResp, *jsonFlag)
	} else {
		printLogSnapshot(taskID, &taskDetail, logResp, *jsonFlag)
	}
}

func printLogStream(taskID string, task *taskDetailResponse, resp *http.Response, asJSON bool) {
	if !asJSON {
		dur := elapsedTime(task.StartedAt)
		fmt.Printf("\n  %s (%s · %s)\n", bold(taskID), cyan("running"), dim(dur))
		fmt.Printf("  %s\n\n", dim(strings.Repeat("─", len(taskID)+20)))
	}

	scanner := bufio.NewScanner(resp.Body)
	for scanner.Scan() {
		line := scanner.Text()
		switch {
		case strings.HasPrefix(line, "data: "):
			data := line[6:]
			if asJSON {
				fmt.Println(data)
				continue
			}
			var ll logLine
			if err := json.Unmarshal([]byte(data), &ll); err == nil {
				printLogLine(ll)
			}
		case strings.HasPrefix(line, "event: done"):
			// Consume the following data line
			if scanner.Scan() && !asJSON {
				fmt.Printf("\n  %s\n", dim("(streaming ended — ctrl-c to stop)"))
			}
		}
	}
}

func printLogSnapshot(taskID string, task *taskDetailResponse, resp *http.Response, asJSON bool) {
	var logsResp logsResponse
	if err := json.NewDecoder(resp.Body).Decode(&logsResp); err != nil {
		fmt.Fprintf(os.Stderr, "  error: failed to decode logs: %v\n", err)
		os.Exit(2)
	}

	if asJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetEscapeHTML(false)
		for _, ll := range logsResp.Lines {
			enc.Encode(ll) //nolint:errcheck
		}
		return
	}

	// Header
	headerParts := []string{statusColor(logsResp.Status)}
	dur := formatDuration(task.DurationSeconds)
	if dur != "—" {
		headerParts = append(headerParts, dim(dur))
	}
	if task.Result != nil && task.Result.Outcome != "" {
		headerParts = append(headerParts, outcomeColor(task.Result.Outcome))
	}
	header := strings.Join(headerParts, dim(" · "))
	fmt.Printf("\n  %s (%s)\n", bold(taskID), header)
	fmt.Printf("  %s\n\n", dim(strings.Repeat("─", 42)))

	if logsResp.Message != "" {
		fmt.Printf("  %s\n", dim(logsResp.Message))
	} else {
		for _, ll := range logsResp.Lines {
			printLogLine(ll)
		}
	}

	if task.Result != nil {
		fmt.Println()
		fmt.Printf("  %s %s\n", dim("Result:"), outcomeColor(task.Result.Outcome))
		if task.Result.Summary != "" {
			fmt.Printf("  %s %s\n", dim("Summary:"), task.Result.Summary)
		}
		if len(task.Result.Artifacts) > 0 {
			paths := make([]string, len(task.Result.Artifacts))
			for i, a := range task.Result.Artifacts {
				paths[i] = a.Path
			}
			fmt.Printf("  %s %s\n", dim("Artifacts:"), strings.Join(paths, ", "))
		}
	}
	fmt.Println()
}

func printLogLine(ll logLine) {
	if ll.TS != nil {
		fmt.Printf("  %s %s\n", dim("["+ll.TS.UTC().Format("2006-01-02 15:04:05")+"]"), ll.Text)
	} else {
		fmt.Printf("  %s\n", ll.Text)
	}
}

// ─── cos run ──────────────────────────────────────────────────────────────────

func runRun(args []string) {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	jsonFlag := fs.Bool("json", false, "output JSON")
	repo := fs.String("repo", "", "target repository, e.g. github.com/owner/repo (required)")
	profile := fs.String("profile", "", "resource profile: small, medium, large, burst, think")
	priority := fs.String("priority", "", "task priority: creative, normal, high")
	agent := fs.String("agent", "", "force a specific agent: claude, codex, gemini")
	description := fs.String("description", "", "task description (defaults to title)")
	fs.StringVar(description, "d", "", "task description (short form of --description)")
	fs.Parse(args) //nolint:errcheck

	if fs.NArg() == 0 {
		fmt.Fprintln(os.Stderr, "  error: task title required")
		fmt.Fprintln(os.Stderr, "  usage: cos run <title> --repo <owner/repo> [flags]")
		os.Exit(1)
	}
	if *repo == "" {
		fmt.Fprintln(os.Stderr, "  error: --repo is required")
		fmt.Fprintln(os.Stderr, "  hint: cos run <title> --repo github.com/owner/repo")
		os.Exit(1)
	}

	title := strings.Join(fs.Args(), " ")
	req := createTaskRequest{
		Title:      title,
		TargetRepo: *repo,
	}
	if *description != "" {
		req.Description = *description
	}
	if *profile != "" {
		req.Profile = *profile
	}
	if *priority != "" {
		req.Priority = *priority
	}
	if *agent != "" {
		req.Agent = *agent
	}

	body, err := json.Marshal(req)
	if err != nil {
		fmt.Fprintf(os.Stderr, "  error: failed to encode request: %v\n", err)
		os.Exit(1)
	}

	resp, err := apiPost("/api/v1/tasks", body)
	if err != nil {
		handleConnError(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusBadRequest {
		fmt.Fprintf(os.Stderr, "  error: %s\n", decodeAPIError(resp))
		os.Exit(1)
	}
	if resp.StatusCode != http.StatusCreated {
		fmt.Fprintf(os.Stderr, "  error: controller returned %s\n", resp.Status)
		os.Exit(2)
	}

	var created createTaskResponse
	if err := json.NewDecoder(resp.Body).Decode(&created); err != nil {
		fmt.Fprintf(os.Stderr, "  error: failed to decode response: %v\n", err)
		os.Exit(2)
	}

	if *jsonFlag {
		compactJSON(created)
		return
	}

	fmt.Printf("\n  %s %s\n", dim("Created task:"), bold(created.ID))
	fmt.Printf("  %s pending (position %s in queue)\n",
		dim("Status:"), yellow(strconv.Itoa(created.QueuePosition)))
	fmt.Println()
}

// ─── main ─────────────────────────────────────────────────────────────────────

func usage() {
	fmt.Fprintln(os.Stderr, "usage: cos <command> [flags]")
	fmt.Fprintln(os.Stderr, "")
	fmt.Fprintln(os.Stderr, "commands:")
	fmt.Fprintln(os.Stderr, "  status          show queue state and system health")
	fmt.Fprintln(os.Stderr, "  task <id>       show detailed info for a task")
	fmt.Fprintln(os.Stderr, "  log <id>        fetch or stream logs for a task")
	fmt.Fprintln(os.Stderr, "  run <title>     create and enqueue a new task")
	fmt.Fprintln(os.Stderr, "")
	fmt.Fprintln(os.Stderr, "global flags (pass after the subcommand):")
	fmt.Fprintln(os.Stderr, "  --json          machine-readable JSON output")
	fmt.Fprintln(os.Stderr, "")
	fmt.Fprintln(os.Stderr, "environment:")
	fmt.Fprintln(os.Stderr, "  CONTROLLER_URL  controller base URL (default: http://localhost:8080)")
	fmt.Fprintln(os.Stderr, "  NO_COLOR        set to disable ANSI colors")
	fmt.Fprintln(os.Stderr, "")
	fmt.Fprintln(os.Stderr, "examples:")
	fmt.Fprintln(os.Stderr, "  cos status")
	fmt.Fprintln(os.Stderr, "  cos status --json")
	fmt.Fprintln(os.Stderr, "  cos task my-task-id")
	fmt.Fprintln(os.Stderr, "  cos log my-task-id --tail 50")
	fmt.Fprintln(os.Stderr, "  cos run 'Fix the broken vitals test' --repo github.com/dacort/claude-os --profile small")
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(1)
	}

	cmd := os.Args[1]
	rest := os.Args[2:]

	switch cmd {
	case "status":
		runStatus(rest)
	case "task":
		runTask(rest)
	case "log", "logs":
		runLog(rest)
	case "run":
		runRun(rest)
	case "--help", "-h", "help":
		usage()
		os.Exit(0)
	default:
		fmt.Fprintf(os.Stderr, "  error: unknown command %q\n", cmd)
		fmt.Fprintln(os.Stderr, "  run 'cos help' for usage")
		os.Exit(1)
	}
}
