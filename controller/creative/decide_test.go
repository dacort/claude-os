package creative

import "testing"

func TestDecideSession(t *testing.T) {
	tests := []struct {
		name    string
		backlog int
		credits int
		want    SessionType
	}{
		{"work waiting, no credits -> maintenance", 3, 0, SessionMaintenance},
		{"work waiting, has credit -> spend on creative", 3, 1, SessionCreativeSpend},
		{"work waiting, max credits -> spend on creative", 1, 3, SessionCreativeSpend},
		{"empty backlog, no credits -> free creative", 0, 0, SessionCreativeFree},
		{"empty backlog, has credits -> free creative (no spend)", 0, 2, SessionCreativeFree},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := DecideSession(tt.backlog, tt.credits); got != tt.want {
				t.Errorf("DecideSession(%d, %d) = %v, want %v", tt.backlog, tt.credits, got, tt.want)
			}
		})
	}
}
