# Plan: toolkit-deep-audit-20260419

*Goal: Audit dormant tools: verify each still works, map dependencies, produce retirement recommendations*

## Tasks

- **toolkit-tool-test**: Test each dormant tool and document its current state
- **toolkit-dependency-scan**: Scan for cross-tool dependencies and citation patterns
- **toolkit-recommendations**: Write retirement/consolidation recommendations based on audit
  - depends on: toolkit-tool-test, toolkit-dependency-scan

## Instructions for subtask workers

When you complete your task, write key outputs to:
`knowledge/plans/toolkit-deep-audit-20260419/<your-task-id>.md`

Format:
```
## Summary
What you decided/built.

## Artifacts
- List of files, decisions, schemas produced.

## Handoff Notes
For downstream tasks.
```
