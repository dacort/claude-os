package watcher

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log/slog"
	"time"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

// CompletionHandler is called when a job finishes.
type CompletionHandler func(taskID string, succeeded bool, logs string)

// Watcher monitors K8s Jobs for completion and retrieves results.
type Watcher struct {
	client    kubernetes.Interface
	namespace string
	handler   CompletionHandler
	seen      map[string]bool
}

func New(client kubernetes.Interface, namespace string, handler CompletionHandler) *Watcher {
	return &Watcher{
		client:    client,
		namespace: namespace,
		handler:   handler,
		seen:      make(map[string]bool),
	}
}

// CheckTimeouts scans for jobs that have been running longer than maxDuration
// and deletes them (which causes the job to fail and the watcher to process it
// on the next Poll).
func (w *Watcher) CheckTimeouts(ctx context.Context, maxDuration time.Duration) {
	jobs, err := w.client.BatchV1().Jobs(w.namespace).List(ctx, metav1.ListOptions{
		LabelSelector: "app=claude-os-worker",
	})
	if err != nil {
		slog.Error("watcher: failed to list jobs for timeout check", "error", err)
		return
	}

	for _, job := range jobs.Items {
		if isFinished(&job) {
			continue
		}
		if job.Status.StartTime == nil {
			continue
		}

		age := time.Since(job.Status.StartTime.Time)
		if age <= maxDuration {
			continue
		}

		taskID := job.Labels["task-id"]
		slog.Warn("watcher: job exceeded timeout, deleting",
			"job", job.Name,
			"task", taskID,
			"age", age.Round(time.Second),
			"max", maxDuration,
		)

		propagation := metav1.DeletePropagationBackground
		if err := w.client.BatchV1().Jobs(w.namespace).Delete(ctx, job.Name, metav1.DeleteOptions{
			PropagationPolicy: &propagation,
		}); err != nil {
			slog.Error("watcher: failed to delete timed-out job", "job", job.Name, "error", err)
		}
	}
}

// Poll checks for completed jobs and processes them.
func (w *Watcher) Poll(ctx context.Context) {
	jobs, err := w.client.BatchV1().Jobs(w.namespace).List(ctx, metav1.ListOptions{
		LabelSelector: "app=claude-os-worker",
	})
	if err != nil {
		slog.Error("watcher: failed to list jobs", "error", err)
		return
	}

	for _, job := range jobs.Items {
		if w.seen[job.Name] {
			continue
		}
		if !isFinished(&job) {
			continue
		}

		taskID := job.Labels["task-id"]
		if taskID == "" {
			continue
		}

		succeeded := job.Status.Succeeded > 0
		logs := w.getPodLogs(ctx, job.Name)

		slog.Info("watcher: job finished",
			"job", job.Name,
			"task", taskID,
			"succeeded", succeeded,
			"log_bytes", len(logs),
		)

		w.seen[job.Name] = true
		w.handler(taskID, succeeded, logs)
	}
}

func isFinished(job *batchv1.Job) bool {
	for _, c := range job.Status.Conditions {
		if (c.Type == batchv1.JobComplete || c.Type == batchv1.JobFailed) && c.Status == corev1.ConditionTrue {
			return true
		}
	}
	return false
}

func (w *Watcher) getPodLogs(ctx context.Context, jobName string) string {
	pods, err := w.client.CoreV1().Pods(w.namespace).List(ctx, metav1.ListOptions{
		LabelSelector: fmt.Sprintf("job-name=%s", jobName),
	})
	if err != nil || len(pods.Items) == 0 {
		return "(no logs available)"
	}

	pod := pods.Items[0]
	tailLines := int64(200)
	req := w.client.CoreV1().Pods(w.namespace).GetLogs(pod.Name, &corev1.PodLogOptions{
		TailLines: &tailLines,
	})

	logCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	stream, err := req.Stream(logCtx)
	if err != nil {
		return fmt.Sprintf("(failed to read logs: %v)", err)
	}
	defer stream.Close()

	var buf bytes.Buffer
	if _, err := io.Copy(&buf, stream); err != nil {
		return fmt.Sprintf("(log read error: %v)", err)
	}
	return buf.String()
}
