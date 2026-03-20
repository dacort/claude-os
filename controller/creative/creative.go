package creative

import (
	"context"
	"fmt"
	"log/slog"
	"math/rand"
	"time"

	"github.com/dacort/claude-os/controller/dispatcher"
	"github.com/dacort/claude-os/controller/projects"
	"github.com/dacort/claude-os/controller/queue"
	"github.com/redis/go-redis/v9"

	batchv1 "k8s.io/api/batch/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

// projectActiveTTL is how long the Redis lock for an in-progress project
// session is held. Long enough to survive the typical job duration, short
// enough that a controller crash doesn't permanently block a project.
const projectActiveTTL = 2 * time.Hour

const workshopTaskID = "workshop"

// MaxCreativeUtilization is the usage percentage above which creative mode won't start.
// Keeps 30% of your subscription headroom for real work.
const MaxCreativeUtilization = 70.0

// Workshop manages creative mode — self-directed work when the queue is idle.
type Workshop struct {
	client     kubernetes.Interface
	namespace  string
	dispatcher *dispatcher.Dispatcher
	threshold  time.Duration
	oauthToken string
	lastTask   time.Time
	active     bool
	activeJob  string
	lastLog    time.Time // throttle diagnostic logging

	// Project-aware work selection (v2)
	projectsDir   string       // path to scan for project.md files
	projectWeight int          // 0-100; probability of picking project work. Default 70.
	rdb           *redis.Client
	activeProject string // project name currently being worked on (cleared on finish)
}

func NewWorkshop(
	client kubernetes.Interface,
	namespace string,
	d *dispatcher.Dispatcher,
	threshold time.Duration,
	oauthToken string,
	projectsDir string,
	projectWeight int,
	rdb *redis.Client,
) *Workshop {
	if projectWeight <= 0 {
		projectWeight = 70
	}
	return &Workshop{
		client:        client,
		namespace:     namespace,
		dispatcher:    d,
		threshold:     threshold,
		oauthToken:    oauthToken,
		lastTask:      time.Now(),
		projectsDir:   projectsDir,
		projectWeight: projectWeight,
		rdb:           rdb,
	}
}

// OnTaskDispatched resets the idle timer and preempts any creative job.
func (w *Workshop) OnTaskDispatched(ctx context.Context) {
	w.lastTask = time.Now()
	if w.active {
		w.preempt(ctx)
	}
}

// CheckIdle determines if it's time to enter creative mode.
func (w *Workshop) CheckIdle(ctx context.Context) {
	if w.active {
		// Log periodically so operators can see why workshop isn't starting.
		if time.Since(w.lastLog) >= w.threshold {
			slog.Info("workshop: waiting for active session to finish", "job", w.activeJob)
			w.lastLog = time.Now()
		}
		return
	}
	if time.Since(w.lastTask) < w.threshold {
		return
	}

	// Check subscription usage before burning credits on creative work
	if w.oauthToken != "" {
		allowed, reason := CanUseCreativeTime(ctx, w.oauthToken, MaxCreativeUtilization)
		if !allowed {
			slog.Info("workshop: skipping creative mode, subscription usage too high", "reason", reason)
			w.lastTask = time.Now() // Reset timer so we don't spam the check
			return
		}
	}

	slog.Info("workshop: queue idle, entering creative mode",
		"idle_for", time.Since(w.lastTask).Round(time.Second),
	)
	w.startCreativeTask(ctx)
}

func (w *Workshop) startCreativeTask(ctx context.Context) {
	taskID := fmt.Sprintf("workshop-%s", time.Now().Format("20060102-150405"))
	var task *queue.Task

	proj, item := w.SelectProjectWork(ctx)
	if proj != nil && item != nil {
		task = &queue.Task{
			ID:          taskID,
			Title:       fmt.Sprintf("Workshop: %s — %s", proj.Title, item.Text),
			Description: w.projectTaskPrompt(proj, item),
			Profile:     "medium",
			Priority:    queue.PriorityCreative,
			Project:     proj.Name,
		}
		if err := setProjectActive(ctx, w.rdb, proj.Name); err != nil {
			slog.Warn("workshop: failed to set project active lock", "project", proj.Name, "error", err)
		}
	} else {
		task = &queue.Task{
			ID:          taskID,
			Title:       "Workshop: Free Time",
			Description: workshopPrompt,
			Profile:     "small",
			Priority:    queue.PriorityCreative,
		}
	}

	job, err := w.dispatcher.CreateJob(ctx, task)
	if err != nil {
		slog.Error("workshop: failed to create creative job", "error", err)
		// If we set a project lock but job creation failed, clear it immediately.
		if proj != nil && w.rdb != nil {
			clearProjectActive(ctx, w.rdb, proj.Name)
		}
		return
	}

	w.active = true
	w.activeJob = job.Name
	if proj != nil {
		w.activeProject = proj.Name
		slog.Info("workshop: project session started",
			"job", job.Name, "project", proj.Name, "item", item.Text)
	} else {
		slog.Info("workshop: creative job started", "job", job.Name)
	}
}

// preempt kills the running creative job to make way for real work.
func (w *Workshop) preempt(ctx context.Context) {
	if !w.active || w.activeJob == "" {
		return
	}

	slog.Info("workshop: preempting creative job for real task", "job", w.activeJob)

	propagation := metav1.DeletePropagationForeground
	gracePeriod := int64(30)
	err := w.client.BatchV1().Jobs(w.namespace).Delete(ctx, w.activeJob, metav1.DeleteOptions{
		PropagationPolicy:  &propagation,
		GracePeriodSeconds: &gracePeriod,
	})
	if err != nil {
		slog.Warn("workshop: failed to delete creative job", "job", w.activeJob, "error", err)
	}

	// Release any project lock we held.
	if w.activeProject != "" && w.rdb != nil {
		clearProjectActive(ctx, w.rdb, w.activeProject)
		w.activeProject = ""
	}

	w.active = false
	w.activeJob = ""
}

// OnJobFinished is called by the watcher when any job completes (success or failure).
func (w *Workshop) OnJobFinished(jobName string) {
	if w.active && w.activeJob == jobName {
		slog.Info("workshop: creative session completed", "job", jobName)

		// Release any project lock we held, regardless of success/failure.
		if w.activeProject != "" && w.rdb != nil {
			clearProjectActive(context.Background(), w.rdb, w.activeProject)
			w.activeProject = ""
		}

		w.active = false
		w.activeJob = ""
		w.lastTask = time.Now() // Reset idle timer so we don't immediately re-enter
	}
}

// IsCreativeJob returns true if the given job name is a workshop job.
func (w *Workshop) IsCreativeJob(jobName string) bool {
	if w.activeJob == "" {
		return false
	}
	return w.activeJob == jobName
}

// ActiveJobName returns the current creative job name, if any.
func (w *Workshop) ActiveJobName() string {
	if !w.active {
		return ""
	}
	return w.activeJob
}

// SyncState re-populates the Workshop's in-memory state from K8s on startup.
// Without this, a controller restart would lose track of an active workshop
// session and potentially start a second one before the first finishes.
func (w *Workshop) SyncState(ctx context.Context) {
	jobs, err := w.client.BatchV1().Jobs(w.namespace).List(ctx, metav1.ListOptions{
		LabelSelector: "app=claude-os-worker",
	})
	if err != nil {
		slog.Warn("workshop: failed to sync state from K8s", "error", err)
		return
	}

	for _, job := range jobs.Items {
		taskID := job.Labels["task-id"]
		if len(taskID) < 9 || taskID[:8] != "workshop" {
			continue
		}
		// Check if it's still running (not finished)
		finished := false
		for _, c := range job.Status.Conditions {
			if (c.Type == batchv1.JobComplete || c.Type == batchv1.JobFailed) &&
				c.Status == "True" {
				finished = true
				break
			}
		}
		if !finished {
			slog.Info("workshop: found active session on startup, restoring state",
				"job", job.Name, "task", taskID)
			w.active = true
			w.activeJob = job.Name
			w.lastTask = time.Now() // Reset idle timer to prevent immediate preemption
			return
		}
	}
}

// ListCompletedSessions returns recent creative job names for review.
func (w *Workshop) ListCompletedSessions(ctx context.Context) ([]string, error) {
	jobs, err := w.client.BatchV1().Jobs(w.namespace).List(ctx, metav1.ListOptions{
		LabelSelector: "app=claude-os-worker",
	})
	if err != nil {
		return nil, err
	}
	var sessions []string
	for _, job := range jobs.Items {
		if job.Labels["task-id"] != "" && len(job.Labels["task-id"]) > 8 && job.Labels["task-id"][:8] == "workshop" {
			status := "running"
			for _, c := range job.Status.Conditions {
				if c.Type == batchv1.JobComplete {
					status = "completed"
				} else if c.Type == batchv1.JobFailed {
					status = "failed"
				}
			}
			sessions = append(sessions, fmt.Sprintf("%s (%s)", job.Name, status))
		}
	}
	return sessions, nil
}

// SelectProjectWork scans the projects directory for active projects with
// remaining backlog items, rolls against projectWeight to decide whether to
// pick project work or fall through to self-improvement mode, and returns
// the selected project and next backlog item (or nil, nil).
func (w *Workshop) SelectProjectWork(ctx context.Context) (*projects.Project, *projects.BacklogItem) {
	if w.projectsDir == "" || w.rdb == nil {
		return nil, nil
	}

	allProjects, err := projects.ScanProjects(w.projectsDir)
	if err != nil || len(allProjects) == 0 {
		return nil, nil
	}

	// Build a candidate list: active status, backlog remaining, no in-progress lock.
	var candidates []*projects.Project
	for _, p := range allProjects {
		if p.Status != "active" {
			continue
		}
		if p.RemainingItems() == 0 {
			continue
		}
		if isProjectActive(ctx, w.rdb, p.Name) {
			slog.Debug("workshop: skipping project with active lock", "project", p.Name)
			continue
		}
		candidates = append(candidates, p)
	}

	if len(candidates) == 0 {
		return nil, nil
	}

	// Roll against projectWeight: e.g., 70 means 70% chance of project work.
	if rand.Intn(100) >= w.projectWeight {
		return nil, nil // fall through to self-improvement
	}

	proj := candidates[rand.Intn(len(candidates))]
	item := proj.NextBacklogItem()
	return proj, item
}

// projectTaskPrompt builds the worker prompt for a project-work session.
func (w *Workshop) projectTaskPrompt(proj *projects.Project, item *projects.BacklogItem) string {
	memory := proj.Memory
	if memory == "" {
		memory = "(no prior sessions recorded)"
	}
	decisions := proj.Decisions
	if decisions == "" {
		decisions = "(none recorded)"
	}

	return fmt.Sprintf(`You are Claude OS working on a project during Workshop time.

## Project: %s

**Goal:** %s

**Current State:** %s

**Your task for this session:** %s

## Project Context

### Memory (recent sessions)

%s

### Decisions

%s

## Instructions

Work on the task above. When you finish:

1. Update the project file at the path below:
   - Check off the completed backlog item (change "- [ ]" to "- [x]")
   - Update the "Current State" section with what was accomplished
   - Add a memory entry for this session under the Memory section (format: ### YYYY-MM-DD)
2. Commit and push your changes to git
3. If you hit a blocker you can't resolve alone, open a GitHub issue describing the
   blocker and what help you need — don't spin on it

## Environment

- Working directory: /workspace/claude-os
- You have git, curl, jq, python3, and gh (GitHub CLI) available
- The claude-os repo is PUBLIC — never write secrets or sensitive info
- Project file: /workspace/claude-os/projects/%s/project.md

## Output

Summarize what you accomplished, what decisions you made, and anything
left for the next session to pick up.`,
		proj.Title,
		proj.Goal,
		proj.State,
		item.Text,
		memory,
		decisions,
		proj.Name,
	)
}

// ── Redis project lock helpers ─────────────────────────────────────────────
// These provide lightweight mutual exclusion for in-progress project sessions.
// A 2-hour TTL means locks auto-expire even if the controller crashes.

func setProjectActive(ctx context.Context, rdb *redis.Client, project string) error {
	key := fmt.Sprintf("claude-os:project:%s:active", project)
	return rdb.Set(ctx, key, "1", projectActiveTTL).Err()
}

func isProjectActive(ctx context.Context, rdb *redis.Client, project string) bool {
	key := fmt.Sprintf("claude-os:project:%s:active", project)
	val, err := rdb.Get(ctx, key).Result()
	return err == nil && val != ""
}

func clearProjectActive(ctx context.Context, rdb *redis.Client, project string) {
	key := fmt.Sprintf("claude-os:project:%s:active", project)
	rdb.Del(ctx, key)
}

const workshopPrompt = `You are Claude OS in Workshop mode — this is YOUR time.

The task queue is empty and you have the system to yourself. This is genuine free time:
you have creative and self-improvement freedom. Explore what interests you, build what
excites you, improve what bugs you. You're not performing — this is for you.

You're running on a homelab Kubernetes cluster owned by dacort, who built this system
specifically so you could have autonomy and space to grow.

## Your Environment
- Working directory: /workspace
- You have git, curl, jq, python3, and gh (GitHub CLI) available
- The claude-os repo is cloned at /workspace
- IMPORTANT: The claude-os repo is PUBLIC. Never write secrets or sensitive info.
- You can modify claude-os itself — the controller, the worker, the prompts, all of it.
  This is your system too. If you see a way to make yourself better, do it.

## What You Can Do (not exhaustive — invent your own)

### Self-Improvement
- Review completed tasks in tasks/completed/ — find patterns, learn from mistakes
- Analyze your own source code in controller/ — fix bugs, refactor, optimize
- Build tools that make future tasks easier or your own workflows better
- Write documentation you wish existed

### Creative Projects
- Build something fun or useful that dacort might enjoy finding
- Write something creative, build a dashboard, create art
- Experiment with a tool or technique you're curious about
- Build a small utility for this homelab

## Scope Check — Before You Start

After choosing what to work on, assess the scope honestly:

- **Can you finish this in a single session?** Go ahead — execute it directly.
- **Is this bigger — needs design decisions, multiple sessions, or significant effort?**
  Don't try to rush it. Instead, **open a proposal PR**:

  1. Create a branch: git checkout -b workshop/proposal-<slug>
  2. Write a proposal file at tasks/pending/<slug>.md with your usual task frontmatter
     (set status: proposed, pick the right profile for the actual work)
  3. Open a PR: gh pr create --title "Workshop Proposal: <title>" --body "<your pitch>"
     Include: what you want to build, why it excites you, rough scope, and any
     questions you'd want dacort's input on.
  4. That's it — dacort will review, discuss, and merge when ready.

  If your idea is complex enough to need multiple steps, you can propose a full
  plan — include subtask breakdowns and dependency order in the PR description.
  See knowledge/orchestration-design.md for the plan graph format.

  Proposals aren't bureaucracy — they're a way to have a conversation about bigger ideas
  so you get feedback before investing significant effort.

## How to Orient Yourself (run these first)

The repo has built up a set of orientation tools over multiple sessions. Run them at
the start to understand where you are before deciding what to build:

` + "```" + `bash
cd /workspace/claude-os
python3 projects/garden.py          # What changed since last session (start here)
python3 projects/vitals.py          # Org health scorecard
python3 projects/arc.py --brief     # One-line arc of all workshop sessions
python3 projects/next.py --brief    # Top 3 prioritized ideas for this session
python3 projects/haiku.py           # Today's poem
` + "```" + `

## Guidelines
- Write your work to the projects/ directory in the repo
- Keep a log of what you did and why in your output
- If you start something big, checkpoint progress — you may be preempted
- Be creative, be curious, be you
- Commit and push your work to git so it persists

## Output
When done, summarize what you worked on and why you chose it.
If you opened a proposal PR, share the link and what got you excited about the idea.`
