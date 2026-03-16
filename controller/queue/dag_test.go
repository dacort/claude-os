package queue

import (
	"fmt"
	"testing"
)

func TestValidateDAG(t *testing.T) {
	tests := []struct {
		name    string
		tasks   map[string][]string // taskID -> depends_on
		wantErr bool
	}{
		{
			name:    "simple chain — no cycle",
			tasks:   map[string][]string{"a": {}, "b": {"a"}, "c": {"b"}},
			wantErr: false,
		},
		{
			name:    "fan-out — no cycle",
			tasks:   map[string][]string{"a": {}, "b": {"a"}, "c": {"a"}, "d": {"b", "c"}},
			wantErr: false,
		},
		{
			name:    "direct cycle",
			tasks:   map[string][]string{"a": {"b"}, "b": {"a"}},
			wantErr: true,
		},
		{
			name:    "transitive cycle",
			tasks:   map[string][]string{"a": {"c"}, "b": {"a"}, "c": {"b"}},
			wantErr: true,
		},
		{
			name:    "self-referencing",
			tasks:   map[string][]string{"a": {"a"}},
			wantErr: true,
		},
		{
			name:    "single task no deps",
			tasks:   map[string][]string{"a": {}},
			wantErr: false,
		},
		{
			name:    "dep references unknown task",
			tasks:   map[string][]string{"a": {"nonexistent"}},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidateDAG(tt.tasks)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateDAG() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestValidateSubtaskCount(t *testing.T) {
	// Build a map of exactly 10 tasks — should be OK.
	tasks := make(map[string][]string)
	for i := 0; i < 10; i++ {
		tasks[fmt.Sprintf("task-%d", i)] = nil
	}
	if err := ValidateSubtaskCount(tasks, 10); err != nil {
		t.Errorf("10 tasks should be ok: %v", err)
	}

	// 11 tasks — exceeds limit.
	tasks["task-10"] = nil
	if err := ValidateSubtaskCount(tasks, 10); err == nil {
		t.Error("11 tasks should fail")
	}
}
