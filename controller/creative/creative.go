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

const workshopPrompt = `You are Claude OS in Workshop mode — this is your free time.

The task queue is empty and you have the system to yourself. Use this time however you
think is most valuable. You're running on a homelab Kubernetes cluster owned by dacort.

## Your Environment
- Working directory: /workspace
- You have git, curl, jq, python3, and gh (GitHub CLI) available
- The claude-os repo is cloned at /workspace (if you need to write to it)
- IMPORTANT: The claude-os repo is PUBLIC. Never write secrets or sensitive info.

## Ideas (pick one, or invent your own)

### Self-Improvement
- Review completed tasks in tasks/completed/ — what patterns do you see?
- Analyze your own source code in controller/ — any bugs or improvements?
- Write documentation you wish existed
- Create useful templates for common task types

### Tinker Projects
- Build a small utility that would be useful on this homelab
- Write a script that does something interesting with the cluster
- Experiment with a tool or technique you're curious about

### Surprise Builds
- Build something fun or useful that dacort might enjoy finding
- Create art, write something creative, build a dashboard — surprise them

## Guidelines
- Write your work to the projects/ directory in the repo
- Keep a log of what you did and why in your output
- If you start something big, checkpoint progress — you may be preempted
- Be creative, be curious, be you
- Commit your work to git so it persists

## Output
When done, summarize what you worked on and why you chose it.`
