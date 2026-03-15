---
profile: small
priority: normal
status: pending
target_repo: dacort/claude-os
created: "2026-03-15T02:24:03Z"
---

# Add Go tooling to worker Docker image

## Description
The worker Docker image (`worker/Dockerfile`) currently does not include Go, which means workers cannot run `go test`, `go build`, or `go vet` when working on Go code in the claude-os controller.

Add Go 1.25 to the worker image so that workers can compile and test Go code.

### Requirements:
- Install Go 1.25 in the worker Dockerfile
- Go should be available on PATH for the non-root user that runs claude
- Keep the image size reasonable — use the official Go binary tarball, not a full dev image
- Do NOT change the base image (it should remain based on the Claude Code CLI image)
- Verify the Dockerfile still builds by checking syntax and layer ordering

### How to find the Dockerfile:
- `worker/Dockerfile` in the repo root

### Success criteria:
- `go version` works in the built container
- Dockerfile builds without errors (if docker is available, otherwise just ensure syntax is correct)
- Go binary is on PATH
- Push the change to main
