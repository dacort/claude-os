# knowledge/plans/

This directory holds shared context for multi-step task plans.

## Convention

Each plan gets its own subdirectory: `knowledge/plans/<plan-id>/`

Workers that produce outputs for downstream tasks write structured output files here.
Those files are then referenced by downstream tasks via `context_refs` in their frontmatter.

## Output File Format

```markdown
# [Task Slug] — Outputs
*plan_id: <plan-id> | task_id: <task-id> | completed: <timestamp>*

## Summary
One paragraph. What was decided/built/found.

## Key Artifacts
Bulleted list of what was produced (file paths, decisions, schemas).

## Handoff Notes
Specific things the next task should know. Not a full log — just what matters.

## Full Output
(The detailed work — schemas, code snippets, analysis, etc.)
```

## Example

Task `cos-cli-define-protocol` writes its output to:
```
knowledge/plans/cos-cli-build-20260311/cos-cli-define-protocol.md
```

Downstream task `cos-cli-implement` declares in its frontmatter:
```yaml
context_refs:
  - knowledge/plans/cos-cli-build-20260311/cos-cli-define-protocol.md
```

The worker entrypoint reads those files and prepends them to the system prompt automatically.

## Audit Trail

The git log for a plan directory shows exactly what context each step had:
```bash
git log knowledge/plans/cos-cli-build-20260311/
```

This is intentional. Everything is git-native for debuggability.
