# Skill: Go Testing

Auto-injected when the task involves writing, fixing, or running Go tests.

## Conventions in this repo

- Tests live alongside source files (`*_test.go`)
- Use `t.Helper()` in test helpers so failure lines point to the caller
- Table-driven tests with `tests := []struct{...}` are preferred
- `t.TempDir()` for temporary files — it's automatically cleaned up
- Use `t.Cleanup(func() { ... })` to reset global state between tests

## Common patterns

```go
// Table-driven test
func TestFoo(t *testing.T) {
    tests := []struct {
        name    string
        input   string
        want    string
        wantErr bool
    }{
        {"happy path", "input", "expected", false},
        {"error case", "bad", "", true},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got, err := Foo(tt.input)
            if (err != nil) != tt.wantErr {
                t.Fatalf("Foo() error = %v, wantErr %v", err, tt.wantErr)
            }
            if got != tt.want {
                t.Errorf("Foo() = %q, want %q", got, tt.want)
            }
        })
    }
}
```

## Debugging failing tests

```bash
go test ./... -v -run TestFoo      # Run one test with verbose output
go test ./... -count=1             # Disable test caching
go test -race ./...                # Race detector
```

## This repo's test approach

The controller uses `k8s.io/client-go/kubernetes/fake` for K8s API mocking and
`github.com/alicebob/miniredis/v2` for Redis. No external services needed in tests.
