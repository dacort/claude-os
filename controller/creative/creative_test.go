package creative

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

const sampleProjectMD = `---
name: test-project
title: Test Project
status: active
owner: dacort
reviewer: claude
created: 2026-01-01T00:00:00Z
secret: false
backlog_source: inline
budget:
  daily_tokens: 50000
  model: claude-sonnet-4-6
---

## Goal

Build something great.

## Current State

Early stages.

## Backlog

- [ ] First task
- [ ] Second task
- [x] Already done

## Memory

### 2026-01-01

Initial setup.

## Decisions

- Use Go
`

// writeProject creates a projects/<name>/project.md under dir.
func writeProject(t *testing.T, dir, name, content string) {
	t.Helper()
	projDir := filepath.Join(dir, name)
	if err := os.MkdirAll(projDir, 0755); err != nil {
		t.Fatalf("mkdir %s: %v", projDir, err)
	}
	if err := os.WriteFile(filepath.Join(projDir, "project.md"), []byte(content), 0644); err != nil {
		t.Fatalf("write project.md: %v", err)
	}
}

func newTestRedis(t *testing.T) *redis.Client {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatalf("miniredis: %v", err)
	}
	t.Cleanup(mr.Close)
	return redis.NewClient(&redis.Options{Addr: mr.Addr()})
}

// TestSelectProjectWork_WithActiveProject verifies that a project with an
// unchecked backlog item is selected when projectWeight is 100.
func TestSelectProjectWork_WithActiveProject(t *testing.T) {
	dir := t.TempDir()
	writeProject(t, dir, "test-project", sampleProjectMD)

	rdb := newTestRedis(t)
	w := &Workshop{
		projectsDir:   dir,
		projectWeight: 100, // always pick project work
		rdb:           rdb,
	}

	ctx := context.Background()
	proj, item := w.SelectProjectWork(ctx)

	if proj == nil {
		t.Fatal("expected a project, got nil")
	}
	if item == nil {
		t.Fatal("expected a backlog item, got nil")
	}
	if proj.Name != "test-project" {
		t.Errorf("expected project name 'test-project', got %q", proj.Name)
	}
	if item.Text != "First task" {
		t.Errorf("expected item 'First task', got %q", item.Text)
	}
	if item.Done {
		t.Error("selected item should not be done")
	}
}

// TestSelectProjectWork_NoProjects verifies that an empty projects dir returns nil.
func TestSelectProjectWork_NoProjects(t *testing.T) {
	dir := t.TempDir()
	rdb := newTestRedis(t)

	w := &Workshop{
		projectsDir:   dir,
		projectWeight: 100,
		rdb:           rdb,
	}

	ctx := context.Background()
	proj, item := w.SelectProjectWork(ctx)

	if proj != nil {
		t.Errorf("expected nil project, got %+v", proj)
	}
	if item != nil {
		t.Errorf("expected nil item, got %+v", item)
	}
}

// TestSelectProjectWork_SkipsLockedProject verifies that a project with an
// active Redis lock is skipped.
func TestSelectProjectWork_SkipsLockedProject(t *testing.T) {
	// This project.md uses "locked-project" as its name so the frontmatter
	// name matches the directory name used for the Redis lock key.
	lockedProjectMD := `---
name: locked-project
title: Locked Project
status: active
---

## Goal

Build something.

## Current State

In progress.

## Backlog

- [ ] A task to do
`
	dir := t.TempDir()
	writeProject(t, dir, "locked-project", lockedProjectMD)

	rdb := newTestRedis(t)
	ctx := context.Background()

	// Pre-lock the project using the same name as the frontmatter.
	if err := setProjectActive(ctx, rdb, "locked-project"); err != nil {
		t.Fatalf("setProjectActive: %v", err)
	}

	w := &Workshop{
		projectsDir:   dir,
		projectWeight: 100,
		rdb:           rdb,
	}

	proj, item := w.SelectProjectWork(ctx)
	if proj != nil {
		t.Errorf("expected nil project (locked), got %q", proj.Name)
	}
	if item != nil {
		t.Errorf("expected nil item (project locked), got %+v", item)
	}
}

// TestSelectProjectWork_SkipsInactiveProject verifies that a project with
// status != "active" is not selected.
func TestSelectProjectWork_SkipsInactiveProject(t *testing.T) {
	inactiveProjectMD := `---
name: archived-project
title: Archived Project
status: archived
---

## Goal

Old goal.

## Current State

Done.

## Backlog

- [ ] Leftover task
`
	dir := t.TempDir()
	writeProject(t, dir, "archived-project", inactiveProjectMD)

	rdb := newTestRedis(t)
	w := &Workshop{
		projectsDir:   dir,
		projectWeight: 100,
		rdb:           rdb,
	}

	ctx := context.Background()
	proj, item := w.SelectProjectWork(ctx)
	if proj != nil {
		t.Errorf("expected nil project (archived), got %q", proj.Name)
	}
	if item != nil {
		t.Errorf("expected nil item (archived project), got %+v", item)
	}
}

// TestSelectProjectWork_WeightZero verifies that weight=0 always falls through
// to self-improvement mode.
func TestSelectProjectWork_WeightZero(t *testing.T) {
	dir := t.TempDir()
	writeProject(t, dir, "test-project", sampleProjectMD)

	rdb := newTestRedis(t)
	w := &Workshop{
		projectsDir:   dir,
		projectWeight: 0, // never pick project work
		rdb:           rdb,
	}

	ctx := context.Background()
	// Run 20 times — with weight 0 we should always get nil
	for i := 0; i < 20; i++ {
		proj, item := w.SelectProjectWork(ctx)
		if proj != nil || item != nil {
			t.Fatalf("expected nil (weight=0) on iteration %d", i)
		}
	}
}

// TestProjectLockHelpers verifies the Redis lock round-trip.
func TestProjectLockHelpers(t *testing.T) {
	rdb := newTestRedis(t)
	ctx := context.Background()

	if isProjectActive(ctx, rdb, "my-proj") {
		t.Error("expected project not active before set")
	}

	if err := setProjectActive(ctx, rdb, "my-proj"); err != nil {
		t.Fatalf("setProjectActive: %v", err)
	}

	if !isProjectActive(ctx, rdb, "my-proj") {
		t.Error("expected project active after set")
	}

	clearProjectActive(ctx, rdb, "my-proj")

	if isProjectActive(ctx, rdb, "my-proj") {
		t.Error("expected project not active after clear")
	}
}
