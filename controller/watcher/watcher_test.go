package watcher

import "testing"

func TestClassifyFailure(t *testing.T) {
	tests := []struct {
		name string
		logs string
		want FailureClass
	}{
		{
			name: "rate limit - out of usage",
			logs: "Error: You're out of extra usage for Claude until next week",
			want: FailureClassRateLimit,
		},
		{
			name: "rate limit - 429",
			logs: "HTTP 429 Too Many Requests",
			want: FailureClassRateLimit,
		},
		{
			name: "rate limit - credit balance",
			logs: "Error: Credit balance too low",
			want: FailureClassRateLimit,
		},
		{
			name: "rate limit - usage limit",
			logs: "You've reached your usage limit",
			want: FailureClassRateLimit,
		},
		{
			name: "task error - generic",
			logs: "Error: file not found: /workspace/missing.go",
			want: FailureClassTaskError,
		},
		{
			name: "task error - test failure",
			logs: "FAIL: TestLogin expected 200 got 500",
			want: FailureClassTaskError,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ClassifyFailure(tt.logs)
			if got != tt.want {
				t.Errorf("ClassifyFailure() = %v, want %v", got, tt.want)
			}
		})
	}
}
