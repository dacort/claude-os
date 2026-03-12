package creative

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/dacort/claude-os/controller/dispatcher"
	"github.com/dacort/claude-os/controller/queue"

	batchv1 "k8s.io/api/batch/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

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
}

func NewWorkshop(client kubernetes.Interface, namespace string, d *dispatcher.Dispatcher, threshold time.Duration, oauthToken string) *Workshop {
	return &Workshop{
		client:     client,
		namespace:  namespace,
		dispatcher: d,
		threshold:  threshold,
		oauthToken: oauthToken,
		lastTask:   time.Now(),
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
	task := &queue.Task{
		ID:       fmt.Sprintf("workshop-%s", time.Now().Format("20060102-150405")),
		Title:    "Workshop: Free Time",
		Description: workshopPrompt,
		Profile:  "small",
		Priority: queue.PriorityCreative,
	}

	job, err := w.dispatcher.CreateJob(ctx, task)
	if err != nil {
		slog.Error("workshop: failed to create creative job", "error", err)
		return
	}

	w.active = true
	w.activeJob = job.Name
	slog.Info("workshop: creative job started", "job", job.Name)
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

	w.active = false
	w.activeJob = ""
}

// OnJobFinished is called by the watcher when any job completes.
func (w *Workshop) OnJobFinished(jobName string) {
	if w.active && w.activeJob == jobName {
		slog.Info("workshop: creative session completed", "job", jobName)
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
