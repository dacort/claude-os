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
	"github.com/dacort/claude-os/controller/scheduler"
	"github.com/dacort/claude-os/controller/triage"
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
	jobDispatcher := dispatcher.New(k8sClient, cfg.Worker.Namespace, cfg.Worker.Image, cfg.Git.Repo, cfg.Git.Branch)

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

	// Scheduled task scheduler — enqueues recurring tasks on cron schedules.
	taskScheduler := scheduler.New(rdb, func(ctx context.Context, spawned scheduler.SpawnedTask) error {
		priority := queue.PriorityNormal
		switch spawned.Priority {
		case "high":
			priority = queue.PriorityHigh
		case "creative":
			priority = queue.PriorityCreative
		}
		task := &queue.Task{
			ID:          spawned.ID,
			Title:       spawned.Title,
			Description: spawned.Description,
			TargetRepo:  spawned.TargetRepo,
			Profile:     spawned.Profile,
			Agent:       spawned.Agent,
			Model:       spawned.Model,
			Mode:        spawned.Mode,
			Priority:    priority,
			ContextRefs: spawned.ContextRefs,
			MaxRetries:  1, // scheduled tasks get 1 retry by default
			TaskType:    queue.TaskTypeStandalone,
		}
		return taskQueue.Enqueue(ctx, task)
	}, governor.CanDispatch)
	gitSyncer.SetScheduler(taskScheduler)

	// Creative mode (The Workshop)
	oauthToken := os.Getenv("CLAUDE_CODE_OAUTH_TOKEN")
	var workshop *creative.Workshop
	if cfg.Scheduler.CreativeModeEnabled {
		workshop = creative.NewWorkshop(
			k8sClient,
			cfg.Worker.Namespace,
			jobDispatcher,
			cfg.Scheduler.IdleThreshold(),
			oauthToken,
			cfg.Scheduler.ProjectsDir,
			cfg.Scheduler.ProjectWeight,
			rdb,
		)
		slog.Info("workshop enabled",
			"idle_threshold", cfg.Scheduler.IdleThreshold(),
			"usage_check", oauthToken != "",
			"projects_dir", cfg.Scheduler.ProjectsDir,
			"project_weight", cfg.Scheduler.ProjectWeight,
		)
	}

	// Triage brain (Haiku API for fast routing)
	triageAPIKey := os.Getenv("TRIAGE_API_KEY")
	var triager *triage.Triager
	if triageAPIKey != "" {
		triager = triage.NewTriager("https://api.anthropic.com", triageAPIKey)
		slog.Info("triage enabled (Haiku API)")
	} else {
		slog.Warn("triage disabled — no TRIAGE_API_KEY, using heuristic routing only")
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

	// ── Workshop state sync ────────────────────────────────────────────────
	// On restart, re-discover any in-progress workshop session so we don't
	// spin up a second creative job while the first is still running.
	if workshop != nil {
		syncCtx, syncCancel := context.WithTimeout(ctx, 15*time.Second)
		workshop.SyncState(syncCtx)
		syncCancel()
	}

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

	// Scheduler tick loop — checks for due scheduled tasks every 60 seconds
	go func() {
		slog.Info("starting scheduler tick loop", "interval", "60s")
		ticker := time.NewTicker(60 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				taskScheduler.Tick(ctx)
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

				// Triage: assess task and route intelligently
				agentStatus := triage.AgentStatus{
					Claude: triage.AgentInfo{Available: !taskQueue.IsAgentRateLimited(ctx, "claude")},
					Codex:  triage.AgentInfo{Available: !taskQueue.IsAgentRateLimited(ctx, "codex")},
				}

				var verdict triage.Verdict
				if triager != nil {
					var triageErr error
					verdict, triageErr = triager.Assess(ctx, task.Title, task.Description, agentStatus)
					if triageErr != nil {
						slog.Warn("triage failed, using heuristic", "task", task.ID, "error", triageErr)
						verdict = triage.HeuristicRoute(task.Title, task.Description)
					}
				} else {
					verdict = triage.HeuristicRoute(task.Title, task.Description)
				}

				// Store triage verdict on task for debugging
				task.TriageVerdict = verdict.Reasoning

				// Apply triage recommendations (explicit frontmatter overrides triage)
				if task.Model == "" {
					task.Model = verdict.RecommendedModel
				}
				if task.Agent == "" {
					task.Agent = verdict.RecommendedAgent
				}

				// If triage says this needs a plan and it's not already a plan/subtask
				if verdict.NeedsPlan && task.TaskType == queue.TaskTypeStandalone {
					task.TaskType = queue.TaskTypePlan
					if task.Model == "" {
						task.Model = "claude-opus-4-6"
					}
					if task.Agent == "" {
						task.Agent = "claude"
					}
					slog.Info("triage: promoting to plan task", "id", task.ID)
				}

				slog.Info("dispatching task", "id", task.ID, "title", task.Title,
					"profile", task.Profile, "model", task.Model, "agent", task.Agent,
					"task_type", task.TaskType)
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

	// ── Seed watcher with already-processed tasks ───────────────────────
	// After git sync, scan completed/ and failed/ directories to find tasks
	// that have already been processed. This prevents the watcher from
	// re-processing finished K8s Jobs that are still lingering (TTL = 1 hour)
	// after a controller restart.
	processedTasks := gitSyncer.ListProcessedTaskIDs()
	slog.Info("found already-processed tasks for watcher seeding", "count", len(processedTasks))

	// Job completion watcher — reads results and updates task files in git
	jobWatcher := watcher.New(k8sClient, cfg.Worker.Namespace, func(taskID string, succeeded bool, logs string) {
		// Notify workshop if this was a creative job
		if workshop != nil {
			workshop.OnJobFinished(fmt.Sprintf("claude-os-%s", taskID))
		}

		// Notify scheduler so the next run of a recurring task can proceed
		taskScheduler.OnTaskCompleted(ctx, taskID)

		var parsedResult *queue.TaskResult

		// Try new reporting contract first (decision 002), fall back to legacy.
		if result := queue.ParseResult(logs); result != nil {
			parsedResult = result
			slog.Info("task result (v1 contract)",
				"task", taskID,
				"agent", result.Agent,
				"model", result.Model,
				"outcome", result.Outcome,
				"summary", result.Summary,
				"tokens_in", result.Usage.TokensIn,
				"tokens_out", result.Usage.TokensOut,
				"duration_s", result.Usage.DurationSeconds,
			)
			if task, err := taskQueue.Get(ctx, taskID); err == nil {
				task.DurationSeconds = result.Usage.DurationSeconds
				task.TokensUsed = result.Usage.TokensIn + result.Usage.TokensOut
				if saveErr := taskQueue.SaveTask(ctx, task); saveErr != nil {
					slog.Warn("failed to save task result", "task", taskID, "error", saveErr)
				}
			}
		} else if usage := queue.ParseUsage(logs); usage != nil {
			// Legacy usage block — backward compatible during transition.
			slog.Info("task usage (legacy)",
				"task", taskID,
				"agent", usage.Agent,
				"duration_s", usage.DurationSeconds,
				"exit_code", usage.ExitCode,
			)
			if task, err := taskQueue.Get(ctx, taskID); err == nil {
				task.DurationSeconds = usage.DurationSeconds
				if saveErr := taskQueue.SaveTask(ctx, task); saveErr != nil {
					slog.Warn("failed to save task duration", "task", taskID, "error", saveErr)
				}
			}
		}

		if succeeded {
			slog.Info("completing task", "task", taskID)
			gitSyncer.CompleteTask(taskID, parsedResult, logs)
			taskQueue.UpdateStatus(ctx, taskID, queue.StatusCompleted, "")

			// Check if this task is part of a plan
			if planTask, err := taskQueue.Get(ctx, taskID); err == nil && planTask.PlanID != "" {
				taskQueue.CompletePlanTask(ctx, planTask.PlanID, taskID)

				// Unblock any waiting siblings whose dependencies are now met
				blocked, _ := taskQueue.GetBlocked(ctx, planTask.PlanID)
				for _, bt := range blocked {
					allMet := true
					for _, dep := range bt.DependsOn {
						dt, depErr := taskQueue.Get(ctx, dep)
						if depErr != nil || dt.Status != queue.StatusCompleted {
							allMet = false
							break
						}
					}
					if allMet {
						slog.Info("unblocking task", "id", bt.ID, "plan", planTask.PlanID)
						taskQueue.Unblock(ctx, bt)
					}
				}

				// Check if the whole plan is now done
				if taskQueue.IsPlanComplete(ctx, planTask.PlanID) {
					slog.Info("plan completed", "plan_id", planTask.PlanID)
				}
			}
		} else {
			// Classify the failure: rate limit or task error
			failClass := watcher.ClassifyFailure(logs)

			if failClass == watcher.FailureClassRateLimit {
				// Rate limit — switch agents, don't consume a retry
				rlTask, rlErr := taskQueue.Get(ctx, taskID)
				if rlErr != nil {
					slog.Error("failed to get task for rate-limit fallback", "task", taskID, "error", rlErr)
					gitSyncer.FailTask(taskID, parsedResult, logs)
					taskQueue.UpdateStatus(ctx, taskID, queue.StatusFailed, "rate limit + lookup error")
					return
				}

				currentAgent := rlTask.Agent
				if currentAgent == "" {
					currentAgent = "claude"
				}

				slog.Warn("rate limit detected", "task", taskID, "agent", currentAgent)
				taskQueue.SetAgentRateLimited(ctx, currentAgent, 1*time.Hour)

				// Honour agent_required — task waits rather than falls back
				if rlTask.AgentRequired != "" && rlTask.AgentRequired == currentAgent {
					slog.Info("task requires specific agent, will wait",
						"task", taskID, "agent_required", rlTask.AgentRequired)
					rlTask.Priority = queue.PriorityCreative
					taskQueue.Enqueue(ctx, rlTask)
					return
				}

				fallbackAgent, ok := taskQueue.GetFallbackAgent(ctx, currentAgent)
				if ok {
					slog.Info("rerouting task to fallback agent",
						"task", taskID, "from", currentAgent, "to", fallbackAgent)
					rlTask.Agent = fallbackAgent
					taskQueue.Enqueue(ctx, rlTask)
				} else {
					slog.Warn("all agents rate-limited, task will wait", "task", taskID)
					rlTask.Priority = queue.PriorityCreative
					taskQueue.Enqueue(ctx, rlTask)
				}
			} else {
				// Task error — normal retry / escalation
				retryTask, retryErr := taskQueue.Get(ctx, taskID)
				if retryErr != nil || retryTask.RetryCount >= retryTask.MaxRetries {
					slog.Info("failing task (retries exhausted)", "task", taskID)
					gitSyncer.FailTask(taskID, parsedResult, logs)
					taskQueue.UpdateStatus(ctx, taskID, queue.StatusFailed, "job failed")
					if retryTask != nil && retryTask.PlanID != "" {
						slog.Warn("subtask failed, plan marked failed",
							"plan_id", retryTask.PlanID, "task", taskID)
					}
				} else {
					retryTask.RetryCount++
					slog.Info("retrying task", "task", taskID,
						"retry", retryTask.RetryCount, "max", retryTask.MaxRetries)
					// Late retries get a model bump
					if retryTask.RetryCount >= retryTask.MaxRetries/2+1 {
						retryTask.Model = escalateModel(retryTask.Model)
						slog.Info("escalating model", "task", taskID, "model", retryTask.Model)
					}
					taskQueue.Enqueue(ctx, retryTask)
				}
			}
		}
	})
	// Seed the watcher's seen map so it doesn't re-process already-handled jobs.
	seedCtx, seedCancel := context.WithTimeout(ctx, 15*time.Second)
	jobWatcher.SeedSeen(seedCtx, processedTasks)
	seedCancel()

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

// escalateModel bumps a model one tier up for retry escalation.
// haiku → sonnet → opus. Already at opus stays at opus.
func escalateModel(current string) string {
	switch current {
	case "claude-haiku-4-5":
		return "claude-sonnet-4-6"
	case "claude-sonnet-4-6":
		return "claude-opus-4-6"
	default:
		return current
	}
}
