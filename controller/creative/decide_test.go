package creative

import "testing"

func TestDecideSession(t *testing.T) {
	tests := []struct {
		name        string
		backlog     int
		credits     int
		freeEnabled bool
		want        SessionType
	}{
		// Approved work waiting — the free-creative flag is irrelevant here.
		{"work waiting, no credits -> maintenance", 3, 0, false, SessionMaintenance},
		{"work waiting, has credit -> spend on creative", 3, 1, false, SessionCreativeSpend},
		{"work waiting, max credits -> spend on creative", 1, 3, false, SessionCreativeSpend},
		{"work waiting, free enabled, has credit -> still spend", 3, 1, true, SessionCreativeSpend},
		// Empty backlog — gated by the free-creative flag.
		{"empty backlog, free disabled -> idle", 0, 0, false, SessionIdle},
		{"empty backlog, free disabled, has credits -> idle", 0, 2, false, SessionIdle},
		{"empty backlog, free enabled -> free creative", 0, 0, true, SessionCreativeFree},
		{"empty backlog, free enabled, has credits -> free creative (no spend)", 0, 2, true, SessionCreativeFree},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := DecideSession(tt.backlog, tt.credits, tt.freeEnabled); got != tt.want {
				t.Errorf("DecideSession(%d, %d, %v) = %v, want %v",
					tt.backlog, tt.credits, tt.freeEnabled, got, tt.want)
			}
		})
	}
}
