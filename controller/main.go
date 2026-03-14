package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/dacort/claude-os/controller/config"
	"github.com/dacort/claude-os/controller/creative"
	"github.com/dacort/claude-os/controller/dispatcher"
	"github.com/dacort/claude-os/controller/gitsync"
	"github.com/dacort/claude-os/controller/governance"
	"github.com/dacort/claude-os/controller/queue"
	"github.com/dacort/claude-os/controller/watcher"

	"github.com/redis/go-redis/v9"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	configPath := os.Getenv("CONFIG_PATH")
	if configPath == "" {
		configPath = "/etc/claude-os/controller.yaml"
	}

	cfg, err := config.Load(configPath)
	if err != nil {
		slog.Error("failed to load config", "error", err)
		os.Exit(1)
	}

	// Load resource profiles
	profilesPath := os.Getenv("PROFILES_PATH")
	if profilesPath == "" {
		profilesPath = "/etc/claude-os/profiles.yaml"
	}
	if err := dispatcher.LoadProfiles(profilesPath); err != nil {
		slog.Error("failed to load profiles", "error", err)
		os.Exit(1)
	}

	// Load skills (optional — missing dir is not an error)
	skillsPath := os.Getenv("SKILLS_PATH")
	if skillsPath == "" {
		skillsPath = "/etc/claude-os/skills"
	}
	if err := dispatcher.LoadSkills(skillsPath); err != nil {
		slog.Error("failed to load skills", "error", err)
		os.Exit(1)
	}

	// Connect to Redis
	rdb := redis.NewClient(&redis.Options{Addr: cfg.Redis.Address})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("failed to connect to Redis", "error", err)
		os.Exit(1)
	}
	cancel()
	slog.Info("connected to Redis", "address", cfg.Redis.Address)

	// Create K8s client (in-cluster)
	k8sConfig, err := rest.InClusterConfig()
	if err != nil {
		slog.Error("failed to get in-cluster config", "error", err)
		os.Exit(1)
	}
	k8sClient, err := kubernetes.NewForConfig(k8sConfig)
	if err != nil {
		slog.Error("failed to create k8s client", "error", err)
		os.Exit(1)
	}

	// Initialize components
	taskQueue := queue.New(rdb)
	jobDispatcher := dispatcher.New(k8sClient, cfg.Worker.Namespace, cfg.Worker.Image)

	// Governance — default limits if config not available
	governor := governance.New(rdb, governance.Limits{
		DailyTokenLimit:     1_000_000,
		WeeklyTokenLimit:    5_000_000,
		ReservePercentage:   30,
		MaxTokensPerJob:     200_000,
		CreativeTokenBudget: 100_000,
		DailyBurstBudget:    5.00,
		BurstWarningPct:     80,
	})

	// Git syncer (uses GITHUB_TOKEN for push access)
	githubToken := os.Getenv("GITHUB_TOKEN")
	gitSyncer := gitsync.NewSyncer(
		cfg.Git.Repo, cfg.Git.Branch,
		"/tmp/claude-os-repo", githubToken, taskQueue,
	)

	// Creative mode (The Workshop)
	oauthToken := os.Getenv("CLAUDE_CODE_OAUTH_TOKEN")
	var workshop *creative.Workshop
	if cfg.Scheduler.CreativeModeEnabled {
		workshop = creative.NewWorkshop(k8sClient, cfg.Worker.Namespace, jobDispatcher, cfg.Scheduler.IdleThreshold(), oauthToken)
		slog.Info("workshop enabled", "idle_threshold", cfg.Scheduler.IdleThreshold(), "usage_check", oauthToken != "")
	}

	// Track Redis health for readiness
	var redisHealthy atomic.Bool
	redisHealthy.Store(true)

	// HTTP server
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "ok")
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
		if !redisHealthy.Load() {
			http.Error(w, "redis unavailable", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "ok")
	})
	server := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.Server.Port),
		Handler: mux,
	}

	// Graceful shutdown
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	// ── Startup Reconciler ─────────────────────────────────────────────────
	// If the controller crashed while tasks were running, their Redis state
	// will still be StatusRunning but no K8s Job will exist. Find and
	// re-queue them so they aren't silently lost.
	reconcileCtx, reconcileCancel := context.WithTimeout(ctx, 30*time.Second)
	runningIDs, err := taskQueue.ListRunning(reconcileCtx)
	if err != nil {
		slog.Warn("reconciler: failed to list running tasks", "error", err)
	} else if len(runningIDs) > 0 {
		slog.Info("reconciler: checking running tasks for orphaned state", "count", len(runningIDs))
		var orphans []string
		for _, id := range runningIDs {
			// Use AnyJobExists (not JobExists) so we don't requeue tasks whose
			// job finished but the watcher hasn't processed it yet.
			exists, err := jobDispatcher.AnyJobExists(reconcileCtx, id)
			if err != nil {
				slog.Warn("reconciler: failed to check job existence", "task", id, "error", err)
				continue
			}
			if !exists {
				slog.Info("reconciler: orphaned task found — no K8s job, will requeue", "task", id)
				orphans = append(orphans, id)
			}
		}
		if len(orphans) > 0 {
			if err := taskQueue.RequeueTasks(reconcileCtx, orphans); err != nil {
				slog.Error("reconciler: failed to requeue orphaned tasks", "error", err)
			} else {
				slog.Info("reconciler: requeued orphaned tasks", "count", len(orphans))
			}
		}
	}
	reconcileCancel()

	go func() {
		slog.Info("starting HTTP server", "port", cfg.Server.Port)
		if err := server.ListenAndServe(); err != http.ErrServerClosed {
			slog.Error("HTTP server error", "error", err)
		}
	}()

	// Git sync loop
	go func() {
		slog.Info("starting git sync loop", "interval", cfg.Git.PollDuration())
		if err := gitSyncer.Sync(ctx); err != nil {
			slog.Error("initial git sync failed", "error", err)
		}
		ticker := time.NewTicker(cfg.Git.PollDuration())
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if err := gitSyncer.Sync(ctx); err != nil {
					slog.Error("git sync failed", "error", err)
				}
			}
		}
	}()

	// Concurrency config — default 3 if not set.
	maxJobs := cfg.Scheduler.MaxConcurrentJobs
	if maxJobs <= 0 {
		maxJobs = 3
	}
	taskTimeout := cfg.Scheduler.TaskTimeoutDuration()
	slog.Info("scheduler configured",
		"max_concurrent_jobs", maxJobs,
		"task_timeout", taskTimeout,
	)

	// Main dispatch loop
	go func() {
		ticker := time.NewTicker(10 * time.Second)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				// Check Redis health
				pingCtx, pingCancel := context.WithTimeout(ctx, 2*time.Second)
				err := rdb.Ping(pingCtx).Err()
				pingCancel()
				redisHealthy.Store(err == nil)

				if err != nil {
					slog.Warn("Redis unavailable, skipping dispatch", "error", err)
					continue
				}

				// ── Concurrency check ──────────────────────────────────────
				// Count active K8s jobs. If we're at the limit, skip this tick.
				// This prevents the dispatcher from launching more jobs than the
				// cluster can handle and makes backpressure explicit.
				activeJobs, err := jobDispatcher.CountActiveJobs(ctx)
				if err != nil {
					slog.Warn("failed to count active jobs", "error", err)
				} else if activeJobs >= maxJobs {
					slog.Debug("concurrency limit reached, skipping dispatch",
						"active", activeJobs, "max", maxJobs)
					continue
				}

				task, err := taskQueue.Dequeue(ctx)
				if err != nil {
					slog.Error("dequeue failed", "error", err)
					continue
				}
				if task == nil {
					// Queue is empty — check if it's time for creative mode
					if workshop != nil {
						workshop.CheckIdle(ctx)
					}
					continue
				}

				// Real task arrived — preempt any creative work
				if workshop != nil {
					workshop.OnTaskDispatched(ctx)
				}

				// Governance check
				priorityStr := "normal"
				switch task.Priority {
				case queue.PriorityHigh:
					priorityStr = "high"
				case queue.PriorityCreative:
					priorityStr = "creative"
				}

				allowed, reason := governor.CanDispatch(ctx, priorityStr)
				if !allowed {
					slog.Info("dispatch throttled by governance", "task", task.ID, "reason", reason)
					taskQueue.Enqueue(ctx, task)
					continue
				}

				slog.Info("dispatching task", "id", task.ID, "title", task.Title, "profile", task.Profile)
				job, err := jobDispatcher.CreateJob(ctx, task)
				if err != nil {
					slog.Error("failed to create job", "task", task.ID, "error", err)
					taskQueue.UpdateStatus(ctx, task.ID, queue.StatusFailed, fmt.Sprintf("dispatch error: %v", err))
					continue
				}
				slog.Info("job created", "task", task.ID, "job", job.Name)
			}
		}
	}()

	// Job completion watcher — reads results and updates task files in git
	jobWatcher := watcher.New(k8sClient, cfg.Worker.Namespace, func(taskID string, succeeded bool, logs string) {
		// Notify workshop if this was a creative job
		if workshop != nil {
			workshop.OnJobFinished(fmt.Sprintf("claude-os-%s", taskID))
		}

		if succeeded {
			slog.Info("completing task", "task", taskID)
			gitSyncer.CompleteTask(taskID, logs)
			taskQueue.UpdateStatus(ctx, taskID, queue.StatusCompleted, "")
		} else {
			slog.Info("failing task", "task", taskID)
			gitSyncer.FailTask(taskID, logs)
			taskQueue.UpdateStatus(ctx, taskID, queue.StatusFailed, "job failed")
		}
	})
	go func() {
		ticker := time.NewTicker(15 * time.Second)
		timeoutTicker := time.NewTicker(5 * time.Minute)
		defer ticker.Stop()
		defer timeoutTicker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				jobWatcher.Poll(ctx)
			case <-timeoutTicker.C:
				// ── Task timeout enforcement ───────────────────────────────
				// Kill jobs that have been running past the configured limit.
				// The watcher will pick up the resulting failure on the next Poll.
				jobWatcher.CheckTimeouts(ctx, taskTimeout)
			}
		}
	}()

	<-ctx.Done()
	slog.Info("shutting down...")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()
	server.Shutdown(shutdownCtx)
	rdb.Close()
}
