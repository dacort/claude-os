package projects

import (
	"strings"
	"testing"
)

const sampleProject = `---
name: rag-indexer
title: RAG Document Indexer
status: active
owner: dacort
reviewer: claude
created: 2026-03-01T00:00:00Z
secret: false
backlog_source: inline
budget:
  daily_tokens: 50000
  model: claude-sonnet-4-6
---

## Goal

Build a RAG indexer that processes documents and stores embeddings.

## Current State

Initial scaffolding complete, embedding pipeline in progress.

## Backlog

- [ ] Set up document loader
- [x] Create embedding client
- [ ] Build vector store interface
- [ ] Add CLI entry point

## Memory

### 2026-03-15

Completed the embedding client. Had to handle rate limiting.

### 2026-03-10

Initial scaffolding done.

## Decisions

- Use OpenAI embeddings API
- Store in PostgreSQL with pgvector
`

func TestParseProject(t *testing.T) {
	p, err := ParseProject("rag-indexer", []byte(sampleProject))
	if err != nil {
		t.Fatalf("ParseProject failed: %v", err)
	}

	if p.Name != "rag-indexer" {
		t.Errorf("expected name rag-indexer, got %q", p.Name)
	}
	if p.Title != "RAG Document Indexer" {
		t.Errorf("expected title 'RAG Document Indexer', got %q", p.Title)
	}
	if p.Status != "active" {
		t.Errorf("expected status active, got %q", p.Status)
	}
	if p.Owner != "dacort" {
		t.Errorf("expected owner dacort, got %q", p.Owner)
	}
	if p.Reviewer != "claude" {
		t.Errorf("expected reviewer claude, got %q", p.Reviewer)
	}
	if p.Created != "2026-03-01T00:00:00Z" {
		t.Errorf("expected created 2026-03-01T00:00:00Z, got %q", p.Created)
	}
	if p.Secret {
		t.Error("expected secret=false")
	}
	if p.BacklogSource != "inline" {
		t.Errorf("expected backlog_source inline, got %q", p.BacklogSource)
	}
	if p.Budget.DailyTokens != 50000 {
		t.Errorf("expected daily_tokens 50000, got %d", p.Budget.DailyTokens)
	}
	if p.Budget.Model != "claude-sonnet-4-6" {
		t.Errorf("expected budget model claude-sonnet-4-6, got %q", p.Budget.Model)
	}
	if !strings.Contains(p.Goal, "RAG indexer") {
		t.Errorf("goal missing expected text, got %q", p.Goal)
	}
	if !strings.Contains(p.State, "scaffolding complete") {
		t.Errorf("state missing expected text, got %q", p.State)
	}
	if len(p.Backlog) != 4 {
		t.Errorf("expected 4 backlog items, got %d", len(p.Backlog))
	}
	if !strings.Contains(p.Memory, "2026-03-15") {
		t.Errorf("memory missing expected date, got %q", p.Memory)
	}
	if !strings.Contains(p.Decisions, "OpenAI") {
		t.Errorf("decisions missing expected text, got %q", p.Decisions)
	}
}

func TestNextBacklogItem(t *testing.T) {
	p, err := ParseProject("rag-indexer", []byte(sampleProject))
	if err != nil {
		t.Fatalf("ParseProject failed: %v", err)
	}

	item := p.NextBacklogItem()
	if item == nil {
		t.Fatal("expected a next backlog item, got nil")
	}
	if !strings.Contains(item.Text, "Set up document loader") {
		t.Errorf("expected first unchecked item, got %q", item.Text)
	}
	if item.Done {
		t.Error("next item should not be done")
	}
}

func TestNextBacklogItem_AllDone(t *testing.T) {
	content := `---
name: all-done
title: All Done
status: active
---

## Backlog

- [x] First item
- [x] Second item
`
	p, err := ParseProject("all-done", []byte(content))
	if err != nil {
		t.Fatalf("ParseProject failed: %v", err)
	}

	item := p.NextBacklogItem()
	if item != nil {
		t.Errorf("expected nil when all items done, got %+v", item)
	}
}

func TestCheckOffItem(t *testing.T) {
	p, err := ParseProject("rag-indexer", []byte(sampleProject))
	if err != nil {
		t.Fatalf("ParseProject failed: %v", err)
	}

	first := p.NextBacklogItem()
	if first == nil {
		t.Fatal("expected a next backlog item")
	}

	updated, err := CheckOffItem(sampleProject, *first)
	if err != nil {
		t.Fatalf("CheckOffItem failed: %v", err)
	}

	// Re-parse updated content
	p2, err := ParseProject("rag-indexer", []byte(updated))
	if err != nil {
		t.Fatalf("re-parse failed: %v", err)
	}

	next := p2.NextBacklogItem()
	if next == nil {
		t.Fatal("expected a next unchecked item after checking off first")
	}
	if strings.Contains(next.Text, "Set up document loader") {
		t.Errorf("first item should be checked off now, but still returned as next")
	}
	if !strings.Contains(next.Text, "Build vector store interface") {
		t.Errorf("expected 'Build vector store interface' as next item, got %q", next.Text)
	}
}

func TestRemainingItems(t *testing.T) {
	p, err := ParseProject("rag-indexer", []byte(sampleProject))
	if err != nil {
		t.Fatalf("ParseProject failed: %v", err)
	}

	// 4 total, 1 done → 3 remaining
	if p.RemainingItems() != 3 {
		t.Errorf("expected 3 remaining items, got %d", p.RemainingItems())
	}
}

func TestUpdateCurrentState(t *testing.T) {
	updated, err := UpdateCurrentState(sampleProject, "Vector store interface complete, CLI in progress.")
	if err != nil {
		t.Fatalf("UpdateCurrentState failed: %v", err)
	}

	if !strings.Contains(updated, "Vector store interface complete") {
		t.Error("updated content missing new state text")
	}
	if strings.Contains(updated, "Initial scaffolding complete") {
		t.Error("old state text should be replaced")
	}

	// Verify other sections still present
	if !strings.Contains(updated, "## Backlog") {
		t.Error("Backlog section should still be present")
	}
	if !strings.Contains(updated, "## Goal") {
		t.Error("Goal section should still be present")
	}
}

func TestAppendMemory(t *testing.T) {
	updated, err := AppendMemory(sampleProject, "2026-03-20", "Completed vector store interface.")
	if err != nil {
		t.Fatalf("AppendMemory failed: %v", err)
	}

	if !strings.Contains(updated, "2026-03-20") {
		t.Error("updated content missing new memory date")
	}
	if !strings.Contains(updated, "Completed vector store interface") {
		t.Error("updated content missing new memory summary")
	}

	// New entry should appear before the old 2026-03-15 entry
	newIdx := strings.Index(updated, "2026-03-20")
	oldIdx := strings.Index(updated, "2026-03-15")
	if newIdx > oldIdx {
		t.Errorf("new memory entry should appear before old entries (new=%d, old=%d)", newIdx, oldIdx)
	}
}
