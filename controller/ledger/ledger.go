// Package ledger tracks creative-time credits for the chores-before-dessert
// Workshop loop (spec 2026-06-10). State lives in a JSON file inside the
// controller's git clone so it is transparent and survives Redis wipes.
package ledger

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Cap is the maximum credit balance — no hoarding haiku vouchers.
const Cap = 3

// historyLimit bounds the audit trail kept in the state file.
const historyLimit = 20

// Entry is one credit change, kept for transparency.
type Entry struct {
	Time    time.Time `json:"time"`
	Delta   int       `json:"delta"`
	Session string    `json:"session"`
	Reason  string    `json:"reason"`
}

type state struct {
	Credits int     `json:"credits"`
	History []Entry `json:"history"`
}

// Ledger reads and writes the credit balance. commitFn is called after every
// successful write with a commit message (wired to gitsync.CommitAndPush in
// production); commit failures are logged, not fatal — the file write is the
// source of truth until the next push succeeds.
type Ledger struct {
	mu       sync.Mutex
	path     string
	commitFn func(message string) error
}

func New(path string, commitFn func(string) error) *Ledger {
	return &Ledger{path: path, commitFn: commitFn}
}

// Balance returns the current credit balance. Missing or corrupt state files
// read as zero — the ledger is forgiving by design.
func (l *Ledger) Balance() int {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.load().Credits
}

// Earn adds one credit (capped at Cap) and returns the new balance.
func (l *Ledger) Earn(session, reason string) int {
	l.mu.Lock()
	defer l.mu.Unlock()

	s := l.load()
	if s.Credits >= Cap {
		slog.Info("ledger: at cap, credit not added", "session", session, "cap", Cap)
		return s.Credits
	}
	s.Credits++
	l.append(&s, Entry{Time: time.Now().UTC(), Delta: +1, Session: session, Reason: reason})
	l.save(s, fmt.Sprintf("ledger: +1 credit (%s) — balance %d", session, s.Credits))
	return s.Credits
}

// Spend removes one credit for a creative session. Returns false (and writes
// nothing) if the balance is zero.
func (l *Ledger) Spend(session string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	s := l.load()
	if s.Credits <= 0 {
		return false
	}
	s.Credits--
	l.append(&s, Entry{Time: time.Now().UTC(), Delta: -1, Session: session, Reason: "creative session"})
	l.save(s, fmt.Sprintf("ledger: -1 credit (%s) — balance %d", session, s.Credits))
	return true
}

func (l *Ledger) load() state {
	data, err := os.ReadFile(l.path)
	if err != nil {
		return state{}
	}
	var s state
	if err := json.Unmarshal(data, &s); err != nil {
		slog.Warn("ledger: corrupt state file, treating as zero", "path", l.path, "error", err)
		return state{}
	}
	return s
}

func (l *Ledger) append(s *state, e Entry) {
	s.History = append(s.History, e)
	if len(s.History) > historyLimit {
		s.History = s.History[len(s.History)-historyLimit:]
	}
}

func (l *Ledger) save(s state, commitMsg string) {
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		slog.Error("ledger: marshal failed", "error", err)
		return
	}
	if err := os.MkdirAll(filepath.Dir(l.path), 0o755); err != nil {
		slog.Error("ledger: mkdir failed", "path", l.path, "error", err)
		return
	}
	if err := os.WriteFile(l.path, data, 0o644); err != nil {
		slog.Error("ledger: write failed", "path", l.path, "error", err)
		return
	}
	if l.commitFn != nil {
		if err := l.commitFn(commitMsg); err != nil {
			slog.Warn("ledger: commit failed (state file still written)", "error", err)
		}
	}
}
