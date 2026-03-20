---
profile: small
priority: high
status: pending
agent: claude
target_repo: dacort/claude-os
created: "2026-03-20T17:22:00Z"
---

# v2 Task 2: Per-project secret mounting in dispatcher

## Description

Add per-project K8s Secret mounting to the dispatcher so worker pods only see credentials for their project.

### Changes

1. **`controller/dispatcher/dispatcher.go`** — Add a new function after `agentSecrets()`:
   ```go
   func projectSecrets(projectName string) []corev1.EnvFromSource {
       if projectName == "" {
           return nil
       }
       optional := true
       return []corev1.EnvFromSource{{
           SecretRef: &corev1.SecretEnvSource{
               LocalObjectReference: corev1.LocalObjectReference{
                   Name: "claude-os-project-" + projectName,
               },
               Optional: &optional,
           },
           Prefix: "PROJECT_",
       }}
   }
   ```

2. In `CreateJob()`, after appending agent secrets to the container's `EnvFrom`, add:
   ```go
   if task.Project != "" {
       container.EnvFrom = append(container.EnvFrom, projectSecrets(task.Project)...)
   }
   ```

3. **Tests** in `controller/dispatcher/dispatcher_test.go`:
   - `TestProjectSecrets_WithProject` — assert returns 1 EnvFromSource with correct name, prefix, and optional=true
   - `TestProjectSecrets_WithoutProject` — assert returns nil for empty string

### TDD Flow
- Write failing tests first, run, implement, run, commit, push
- Commit message: `feat: mount per-project K8s secrets in worker pods`
