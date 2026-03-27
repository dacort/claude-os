# Plan: orch-integration-test-20260327

*Goal: End-to-end test of DAG scheduling: step1 gathers context, step2 depends on it and synthesizes a reflection. Validates spawn_tasks + depends_on from S52-S68.*

## Tasks

- **orch-test-step1**: Gather recent workshop context for DAG integration test
- **orch-test-step2**: Synthesize DAG test reflection from step1 context
  - depends on: orch-test-step1

## Instructions for subtask workers

When you complete your task, write key outputs to:
`knowledge/plans/orch-integration-test-20260327/<your-task-id>.md`

Format:
```
## Summary
What you decided/built.

## Artifacts
- List of files, decisions, schemas produced.

## Handoff Notes
For downstream tasks.
```
