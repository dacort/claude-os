---
profile: medium
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
depends_on:
  - v2-task-4-comms-interface
  - v2-task-5-github-channel
created: "2026-03-20T17:50:00Z"
---

# v2 Task 6: Comms config and wiring into controller

## Description

Wire the comms package (Tasks 4+5) into the controller's config and main.go. This is the integration task that makes comms actually work end-to-end.

### Step 0: Add public accessors to Syncer

In `controller/gitsync/syncer.go`, add public methods that expose `localPath` and `gitCommitAndPush`:

```go
// LocalPath returns the local clone directory path.
func (s *Syncer) LocalPath() string {
	return s.localPath
}

// CommitAndPush stages all changes, commits with the given message, and pushes.
func (s *Syncer) CommitAndPush(message string) error {
	return s.gitCommitAndPush(message)
}
```

If `syncer.go` doesn't exist yet or these methods already exist, skip this step.

### Step 1: Add CommsConfig to config struct

In `controller/config/config.go`, add to the `Config` struct:

```go
Comms CommsConfig `yaml:"comms"`
```

Add new structs:

```go
type CommsConfig struct {
	Channels []ChannelConfig `yaml:"channels"`
}

type ChannelConfig struct {
	Type   string `yaml:"type"`   // "github" or "file"
	Repo   string `yaml:"repo"`   // for github type
	Secret string `yaml:"secret"` // K8s secret name for github token
}
```

### Step 2: Add Workshop config for project weight

In `controller/config/config.go`, add to `SchedulerConfig`:

```go
WorkshopProjectWeight int `yaml:"workshop_project_weight"` // 0-100, default 70
```

Add a method:

```go
func (s SchedulerConfig) ProjectWeight() int {
	if s.WorkshopProjectWeight <= 0 {
		return 70
	}
	return s.WorkshopProjectWeight
}
```

### Step 3: Update controller.yaml config

In `controller/config/controller.yaml` (the default config), add:

```yaml
comms:
  channels:
    - type: file  # always-on fallback

scheduler:
  workshop_project_weight: 70
```

### Step 4: Wire comms Manager into main.go

In `controller/main.go`, after loading config, initialize comms channels:

```go
// Initialize comms channels
var channels []comms.Channel
blockedDir := filepath.Join(gitSyncer.LocalPath(), "tasks", "blocked")
channels = append(channels, comms.NewFileChannel(blockedDir))

for _, chCfg := range cfg.Comms.Channels {
	switch chCfg.Type {
	case "github":
		token := os.Getenv("OCTOCLAUDE_GITHUB_TOKEN")
		if token != "" {
			channels = append(channels, comms.NewGitHubChannel(chCfg.Repo, token))
			slog.Info("comms: github channel enabled", "repo", chCfg.Repo)
		} else {
			slog.Info("comms: github channel configured but OCTOCLAUDE_GITHUB_TOKEN not set, skipping")
		}
	case "file":
		// already added above
	}
}
commsManager := comms.NewManager(channels...)
```

### Step 5: Wire blocker detection into completion handler

In the task completion handler in main.go, after parsing results, add blocker detection:

```go
blocker := queue.ParseBlocker(logs)
if blocker != nil {
	slog.Info("task blocker detected", "task", taskID, "type", blocker.Type)
	commsManager.Notify(ctx, comms.Message{
		ID:      taskID,
		Type:    comms.NeedsHuman,
		Title:   fmt.Sprintf("Blocked: %s — %s", taskID, blocker.Type),
		Body:    fmt.Sprintf("**Credential needed:** %s\n\n**Project:** %s", blocker.Credential, blocker.Project),
		Project: blocker.Project,
		TaskID:  taskID,
	})
}
```

### Step 6: Commit blocked dir on sync

In the git sync loop, after writing results, commit any new blocked files:

```go
if err := gitSyncer.CommitAndPush("comms: update blocked tasks"); err != nil {
	slog.Error("failed to push blocked tasks", "error", err)
}
```

### Testing

- Verify `go build ./controller/...` succeeds
- Run `go test ./controller/... -v` — all existing tests must pass
- Config parsing should handle missing `comms` section gracefully (empty channels list)

### TDD
- Write a test for `ProjectWeight()` default behavior
- Commit: `feat: wire comms channels into controller main loop`

## Results

## Outcome

- Outcome: success
- Agent: claude
- Model: claude-sonnet-4-6

## Summary

Task completed without an explicit structured result block.

## Usage

- Tokens in: 0
- Tokens out: 0
- Duration (s): 251

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "v2-task-6-comms-wiring",
  "agent": "claude",
  "model": "claude-sonnet-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 251
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: v2-task-6-comms-wiring
Profile: medium
Agent: claude
Mode: execution
Started: 2026-03-20T17:54:44Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
Done. Here's what was done:

## Summary

**Task:** Wire the comms package (Tasks 4+5) into the controller's config and `main.go`.

### Changes made (commit `97ce54d`)

**`gitsync/syncer.go`** — Added two public accessors:
- `LocalPath() string` — exposes the repo clone path
- `CommitAndPush(message string) error` — public wrapper around `gitCommitAndPush`

**`config/config.go`** — Three additions:
- `Comms CommsConfig` field on the `Config` struct, plus `CommsConfig` and `ChannelConfig` types
- Renamed `ProjectWeight int` (yaml: `project_weight`) → `WorkshopProjectWeight int` (yaml: `workshop_project_weight`)
- Added `ProjectWeight()` method returning the value with a default of 70 when unset

**`config/controller.yaml`** — New default config file with sensible production defaults, including the `file` comms channel enabled out of the box

**`config/config_test.go`** — Added `TestProjectWeight_Default` and `TestProjectWeight_Explicit` covering the default-70 behavior

**`main.go`** — Four wiring changes:
1. Added `comms`, `path/filepath`, `strings` imports
2. Comms initialization after git syncer setup: FileChannel always-on, GitHubChannel conditionally if `OCTOCLAUDE_GITHUB_TOKEN` is set and repo is in `owner/repo` format
3. Updated `cfg.Scheduler.ProjectWeight` → `cfg.Scheduler.ProjectWeight()` to use the new method
4. Blocker detection in the watcher completion callback: if `queue.ParseBlocker(logs)` returns a result, notify all comms channels and commit/push the blocked task file

All 11 packages build and pass tests.
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-20T17:58:55Z
===RESULT_START===
{"version":"1","task_id":"v2-task-6-comms-wiring","agent":"claude","model":"claude-sonnet-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":251},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"v2-task-6-comms-wiring","agent":"claude","profile":"medium","duration_seconds":251,"exit_code":0,"finished_at":"2026-03-20T17:58:55Z"}
=== END_CLAUDE_OS_USAGE ===

