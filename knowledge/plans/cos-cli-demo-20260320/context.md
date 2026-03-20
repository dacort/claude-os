# Plan: cos-cli-demo-20260320

*Goal: Build a minimal cos CLI — demo multi-agent plan*

## Tasks

- **cos-ux-design**: Design cos CLI UX and slash commands
- **cos-protocol**: Define HTTP protocol for controller /chat endpoint
  - depends on: cos-ux-design
- **cos-controller-api**: Add /chat endpoints to the controller
  - depends on: cos-protocol
- **cos-cli-binary**: Implement cos CLI Go binary
  - depends on: cos-protocol
- **cos-integration**: Wire cos CLI binary to controller and test
  - depends on: cos-controller-api, cos-cli-binary

## Instructions for subtask workers

When you complete your task, write key outputs to:
`knowledge/plans/cos-cli-demo-20260320/<your-task-id>.md`

Format:
```
## Summary
What you decided/built.

## Artifacts
- List of files, decisions, schemas produced.

## Handoff Notes
For downstream tasks.
```
