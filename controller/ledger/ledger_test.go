package ledger

import (
	"os"
	"path/filepath"
	"testing"
)

func newTestLedger(t *testing.T) (*Ledger, *int) {
	t.Helper()
	commits := 0
	path := filepath.Join(t.TempDir(), "state", "credits.json")
	l := New(path, func(msg string) error {
		commits++
		return nil
	})
	return l, &commits
}

func TestMissingFileMeansZeroBalance(t *testing.T) {
	l, _ := newTestLedger(t)
	if got := l.Balance(); got != 0 {
		t.Errorf("Balance() on missing file = %d, want 0", got)
	}
}

func TestEarnAndSpend(t *testing.T) {
	l, commits := newTestLedger(t)

	if got := l.Earn("workshop-maint-1", "merged PR"); got != 1 {
		t.Errorf("Earn() = %d, want 1", got)
	}
	if !l.Spend("workshop-2") {
		t.Error("Spend() with balance 1 = false, want true")
	}
	if got := l.Balance(); got != 0 {
		t.Errorf("Balance() after earn+spend = %d, want 0", got)
	}
	if l.Spend("workshop-3") {
		t.Error("Spend() with balance 0 = true, want false")
	}
	if *commits != 2 {
		t.Errorf("commit calls = %d, want 2 (earn + successful spend)", *commits)
	}
}

func TestEarnCapsAtThree(t *testing.T) {
	l, _ := newTestLedger(t)
	for i := 0; i < 5; i++ {
		l.Earn("workshop-maint-x", "merged PR")
	}
	if got := l.Balance(); got != Cap {
		t.Errorf("Balance() after 5 earns = %d, want %d", got, Cap)
	}
}

func TestPersistsAcrossInstances(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credits.json")
	noop := func(string) error { return nil }

	l1 := New(path, noop)
	l1.Earn("s1", "merged PR")
	l1.Earn("s2", "issue closed")

	l2 := New(path, noop)
	if got := l2.Balance(); got != 2 {
		t.Errorf("Balance() from fresh instance = %d, want 2", got)
	}
}

func TestCorruptFileTreatedAsZero(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credits.json")
	if err := os.WriteFile(path, []byte("not json{"), 0o644); err != nil {
		t.Fatal(err)
	}
	l := New(path, func(string) error { return nil })
	if got := l.Balance(); got != 0 {
		t.Errorf("Balance() on corrupt file = %d, want 0", got)
	}
}
