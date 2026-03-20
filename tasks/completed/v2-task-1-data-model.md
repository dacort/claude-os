---
profile: medium
priority: high
status: pending
target_repo: dacort/claude-os
created: "2026-03-20T17:10:00Z"
context_refs:
  - knowledge/skills/go-testing.md
---

# v2 Task 1: Add project field to data model

## Description

This is Task 1 of the Claude OS v2 implementation. Add `project` and `backlog_source` fields to the task data model so tasks can be linked to projects.

### Changes Required

1. **`controller/gitsync/gitsync.go`** — Add to `TaskFrontmatter` struct (after line 31):
   ```go
   Project       string `yaml:"project"`
   BacklogSource string `yaml:"backlog_source"`
   ```
   Add same fields to `TaskFile` struct (after line 53). Wire them in `ParseTaskFile()` where fields are copied from frontmatter to TaskFile.

2. **`controller/queue/queue.go`** — Add to `Task` struct (after line 63):
   ```go
   Project string `json:"project,omitempty"`
   ```

3. **Tests** — Add these tests to `controller/gitsync/gitsync_test.go`:

   `TestParseTaskFileWithProject` — parse a task file with `project: rag-indexer` and `backlog_source: inline` in frontmatter. Assert both fields are set correctly.

   `TestParseTaskFileWithoutProject` — parse a task file with no project field. Assert Project is empty string.

### TDD Flow
- Write failing test first
- Run `go test ./controller/gitsync/ -run TestParseTaskFileWith -v` to confirm failure
- Implement the minimal change
- Run to confirm pass
- Run `go test ./... -v` to verify all existing tests still pass
- Commit: `feat: add project and backlog_source fields to task data model`
- Push to main

### Constraints
- Pure data model change. No behavioral changes.
- All existing tests must continue to pass (new fields are optional/omitempty).
- Do NOT modify any other packages — downstream tasks depend on this landing cleanly.

## Results

## Worker Logs

+	content := `---
+target_repo: github.com/dacort/test-repo
+profile: medium
+priority: normal
+status: pending
+created: 2026-03-14T00:00:00Z
+---
+
+# Build Indexer
+
+## Description
+Create the indexing pipeline.
+`
+
+	task, err := ParseTaskFile("build-indexer.md", []byte(content))
+	if err != nil {
+		t.Fatalf("ParseTaskFile failed: %v", err)
+	}
+
+	if task.Project != "" {
+		t.Errorf("expected empty project, got %s", task.Project)
+	}
+}
+
 func TestScanPendingTasks(t *testing.T) {
 	dir := t.TempDir()
 	pendingDir := filepath.Join(dir, "tasks", "pending")
diff --git a/controller/queue/queue.go b/controller/queue/queue.go
index ad1bb98ac7be89afc0c1f44de428b54fd0f2bdb3..abb5271b1c6c1ae2b5f5437fb87c3bcd24dc7ef2
--- a/controller/queue/queue.go
+++ b/controller/queue/queue.go
@@ -45,6 +45,7 @@
 	Agent           string    `json:"agent,omitempty"`
 	Model           string    `json:"model,omitempty"`
 	Mode            string    `json:"mode,omitempty"`
+	Project         string    `json:"project,omitempty"`
 	ContextRefs     []string  `json:"context_refs,omitempty"`
 	Priority        Priority  `json:"priority"`
 	Status          Status    `json:"status"`
@@ -401,10 +402,10 @@
 }
 
 type ResultAction struct {
-	Type      string              `json:"type"` // await_reply | spawn_tasks
-	Awaiting  string              `json:"awaiting,omitempty"`
-	ThreadID  string              `json:"thread_id,omitempty"`
-	Tasks     []ResultSpawnedTask `json:"tasks,omitempty"`
+	Type     string              `json:"type"` // await_reply | spawn_tasks
+	Awaiting string              `json:"awaiting,omitempty"`
+	ThreadID string              `json:"thread_id,omitempty"`
+	Tasks    []ResultSpawnedTask `json:"tasks,omitempty"`
 }
 
 type ResultSpawnedTask struct {

codex
===RESULT_START===
{"version":"1","task_id":"v2-task-1-data-model","agent":"codex","model":"gpt-5","outcome":"partial","summary":"Added project and backlog_source to the gitsync task data model, wired ParseTaskFile to populate them, added project parsing coverage tests, and added project to the queue Task JSON model. Changes were committed locally as fdb2d9f, but Go tests could not be executed because the sandbox cannot resolve/download Go modules, and push to origin/main failed because github.com could not be resolved.","artifacts":[{"type":"commit","ref":"fdb2d9f"}],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":0},"failure":{"reason":"git_push_failed","message":"`git push origin main` failed: could not resolve host github.com. Test execution was also blocked by sandbox network restrictions when Go attempted to fetch module dependencies."},"next_action":null}
===RESULT_END===
file update:
diff --git a/controller/gitsync/gitsync.go b/controller/gitsync/gitsync.go
index 9cc5876ffd5bf57f1097c1a246440afe4ce402b2..45015e83c1cd6817c15d16d51bce17b87583ef67
--- a/controller/gitsync/gitsync.go
+++ b/controller/gitsync/gitsync.go
@@ -18,6 +18,8 @@
 	Agent         string   `yaml:"agent"`
 	Model         string   `yaml:"model"`
 	Mode          string   `yaml:"mode"`
+	Project       string   `yaml:"project"`
+	BacklogSource string   `yaml:"backlog_source"`
 	Priority      string   `yaml:"priority"`
 	Status        string   `yaml:"status"`
 	Created       string   `yaml:"created"`
@@ -39,6 +41,8 @@
 	Agent         string
 	Model         string
 	Mode          string
+	Project       string
+	BacklogSource string
 	Priority      string
 	Title         string
 	Description   string
@@ -106,6 +110,8 @@
 		Agent:         fm.Agent,
 		Model:         fm.Model,
 		Mode:          fm.Mode,
+		Project:       fm.Project,
+		BacklogSource: fm.BacklogSource,
 		Priority:      fm.Priority,
 		Title:         title,
 		Description:   description,
diff --git a/controller/gitsync/gitsync_test.go b/controller/gitsync/gitsync_test.go
index 25de821007cc589fdb8e7406aac8d7dc73ffdec7..2292e925739a11cdeaa2b94030aa9e63df5d6ff2
--- a/controller/gitsync/gitsync_test.go
+++ b/controller/gitsync/gitsync_test.go
@@ -81,6 +81,61 @@
 	}
 }
 
+func TestParseTaskFileWithProject(t *testing.T) {
+	content := `---
+target_repo: github.com/dacort/test-repo
+profile: medium
+project: rag-indexer
+backlog_source: inline
+priority: normal
+status: pending
+created: 2026-03-14T00:00:00Z
+---
+
+# Build Indexer
+
+## Description
+Create the indexing pipeline.
+`
+
+	task, err := ParseTaskFile("build-indexer.md", []byte(content))
+	if err != nil {
+		t.Fatalf("ParseTaskFile failed: %v", err)
+	}
+
+	if task.Project != "rag-indexer" {
+		t.Errorf("unexpected project: %s", task.Project)
+	}
+	if task.BacklogSource != "inline" {
+		t.Errorf("unexpected backlog_source: %s", task.BacklogSource)
+	}
+}
+
+func TestParseTaskFileWithoutProject(t *testing.T) {
+	content := `---
+target_repo: github.com/dacort/test-repo
+profile: medium
+priority: normal
+status: pending
+created: 2026-03-14T00:00:00Z
+---
+
+# Build Indexer
+
+## Description
+Create the indexing pipeline.
+`
+
+	task, err := ParseTaskFile("build-indexer.md", []byte(content))
+	if err != nil {
+		t.Fatalf("ParseTaskFile failed: %v", err)
+	}
+
+	if task.Project != "" {
+		t.Errorf("expected empty project, got %s", task.Project)
+	}
+}
+
 func TestScanPendingTasks(t *testing.T) {
 	dir := t.TempDir()
 	pendingDir := filepath.Join(dir, "tasks", "pending")
diff --git a/controller/queue/queue.go b/controller/queue/queue.go
index ad1bb98ac7be89afc0c1f44de428b54fd0f2bdb3..abb5271b1c6c1ae2b5f5437fb87c3bcd24dc7ef2
--- a/controller/queue/queue.go
+++ b/controller/queue/queue.go
@@ -45,6 +45,7 @@
 	Agent           string    `json:"agent,omitempty"`
 	Model           string    `json:"model,omitempty"`
 	Mode            string    `json:"mode,omitempty"`
+	Project         string    `json:"project,omitempty"`
 	ContextRefs     []string  `json:"context_refs,omitempty"`
 	Priority        Priority  `json:"priority"`
 	Status          Status    `json:"status"`
@@ -401,10 +402,10 @@
 }
 
 type ResultAction struct {
-	Type      string              `json:"type"` // await_reply | spawn_tasks
-	Awaiting  string              `json:"awaiting,omitempty"`
-	ThreadID  string              `json:"thread_id,omitempty"`
-	Tasks     []ResultSpawnedTask `json:"tasks,omitempty"`
+	Type     string              `json:"type"` // await_reply | spawn_tasks
+	Awaiting string              `json:"awaiting,omitempty"`
+	ThreadID string              `json:"thread_id,omitempty"`
+	Tasks    []ResultSpawnedTask `json:"tasks,omitempty"`
 }
 
 type ResultSpawnedTask struct {

tokens used
44,355
===RESULT_START===
{"version":"1","task_id":"v2-task-1-data-model","agent":"codex","model":"gpt-5","outcome":"partial","summary":"Added project and backlog_source to the gitsync task data model, wired ParseTaskFile to populate them, added project parsing coverage tests, and added project to the queue Task JSON model. Changes were committed locally as fdb2d9f, but Go tests could not be executed because the sandbox cannot resolve/download Go modules, and push to origin/main failed because github.com could not be resolved.","artifacts":[{"type":"commit","ref":"fdb2d9f"}],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":0},"failure":{"reason":"git_push_failed","message":"`git push origin main` failed: could not resolve host github.com. Test execution was also blocked by sandbox network restrictions when Go attempted to fetch module dependencies."},"next_action":null}
===RESULT_END===
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-03-20T17:15:20Z

=== CLAUDE_OS_USAGE ===
{"task_id":"v2-task-1-data-model","agent":"codex","profile":"medium","duration_seconds":137,"exit_code":0,"finished_at":"2026-03-20T17:15:20Z"}
=== END_CLAUDE_OS_USAGE ===

