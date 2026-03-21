# Plan: cos-cli-20260321

*Goal: Build cos — a terminal interface for interacting with Claude OS*

## Tasks

- **cos-design**: Design the cos CLI: UX, protocol, and data shapes
- **cos-server**: Add cos API endpoints to the controller
  - depends on: cos-design
- **cos-client**: Build the cos CLI binary
  - depends on: cos-design

## Instructions for subtask workers

When you complete your task, write key outputs to:
`knowledge/plans/cos-cli-20260321/<your-task-id>.md`

Format:
```
## Summary
What you decided/built.

## Artifacts
- List of files, decisions, schemas produced.

## Handoff Notes
For downstream tasks.
```
