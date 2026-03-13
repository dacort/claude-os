---
profile: medium
priority: normal
status: proposed
created: "2026-03-12T00:00:00Z"
---

# Orchestration Phase 1: Context Infrastructure

Implement the first phase of the orchestration layer designed in
`knowledge/orchestration-design.md` — the parts that deliver immediate value
even before the full DAG scheduler exists.

## What This Does

Adds three backward-compatible capabilities to the system:

**1. `context_refs` in task frontmatter**
Tasks can declare files to auto-inject into their system prompt:
```yaml
context_refs:
  - knowledge/plans/my-plan/api-schema.md
  - knowledge/preferences.md
```
The worker entrypoint reads these files and prepends them to the system prompt.
This generalizes the preferences.md injection we added in session 9.

**2. `model` in task frontmatter**
Explicit model override, independent of profile:
```yaml
profile: small      # resource envelope
model: claude-opus  # reasoning quality
```
The dispatcher honors explicit `model:` over the profile's `default_model`.
Adds a `think` profile: same resources as `small`, no default model (routing required).

**3. `knowledge/plans/` convention**
Workers that produce outputs for downstream tasks write them to
`knowledge/plans/<plan-id>/<task-slug>.md` following a standard format.
The field guide gets a section on the convention.

## Why Phase 1 Specifically

The full orchestration design (DAG scheduler, `cos` CLI, retry escalation) is
several weeks of work. Phase 1 is the part that's:
- **Backward-compatible** — zero changes to existing tasks
- **Independently useful** — you can manually sequence tasks that share context
  without the dependency graph scheduler
- **Unblocking** — phases 2–4 build on this context infrastructure

After Phase 1, a human can hand-craft a two-task plan where task 2 reads
task 1's outputs. That's already a step-change from the current "each task is
an island" model.

## Implementation Scope

**Controller changes (Go):**
- `gitsync/gitsync.go`: Add `ContextRefs []string` and `Model string` to `TaskFrontmatter`
- `queue/queue.go`: Add same fields to `Task` struct
- `dispatcher.go` (or equivalent): Honor explicit `model:` in job env vars
- `config/profiles.yaml`: Add `think` profile

**Worker changes (shell):**
- `worker/entrypoint.sh`: If `CONTEXT_REFS` env var is set, read those files
  and prepend to system prompt (like preferences.md injection, but configurable)

**Documentation:**
- `knowledge/claude-os-field-guide.md`: Add `knowledge/plans/` convention section
- Update worker prompt to mention `context_refs` capability

**Estimated effort:** 2–3 sessions for someone familiar with the controller code.
Could be split: controller changes in one task, worker changes + docs in another.

## Questions for dacort

1. **Priority?** The system is working great without this. Is now the right time,
   or should the queue focus on feature tasks first?

2. **Scope creep risk?** Phase 1 touches the controller, worker, and docs.
   Should I break this into three separate tasks to keep each reviewable?

3. **`think` profile?** The new profile requires cloud burst tolerations.
   Is that plumbing already set up, or does it need K8s config changes too?

## Reference

Full design: `knowledge/orchestration-design.md` (written session 7, 2026-03-11)

The design document has implementation pseudocode, rationale for all decisions,
and the full 5-phase roadmap. Phase 1 is §1 (partial) + §2 of that document.

## Results

Implemented all three Phase 1 capabilities in commit de30f6f:

**1. `context_refs` in task frontmatter**
- Added `ContextRefs []string` to `TaskFrontmatter`, `TaskFile`, and `queue.Task`
- Dispatcher joins refs with `:` and passes as `CONTEXT_REFS` env var
- Worker `entrypoint.sh` reads each file and prepends content to the system prompt as a "Task Context" section — automatic, no worker code needed

**2. `model` in task frontmatter**
- Added `Model string` to all three structs
- Dispatcher uses `task.Model` if set, falling back to `profile.DefaultModel`
- Tested both paths in `TestModelOverride`

**3. `think` profile**
- Added to `config/profiles.yaml`: 250m CPU / 256Mi RAM / 1Gi scratch, burst tolerations, empty `default_model`
- Tasks using this profile must set `model:` explicitly

**4. `knowledge/plans/` convention**
- Created `knowledge/plans/README.md` with standard output format
- Updated field guide: task file format section + new "On knowledge/plans/" section

**Tests added:**
- `TestParseTaskFileWithContextRefsAndModel` in `gitsync_test.go`
- `TestModelOverride` and `TestContextRefsEnvVar` in `dispatcher_test.go`

All changes are backward-compatible. Zero existing task files require modification.
