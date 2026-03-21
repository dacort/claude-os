---
target_repo: github.com/dacort/claude-os
profile: small
agent: claude
model: claude-opus-4-6
priority: normal
status: pending
created: "2026-03-21T02:05:16Z"
plan_id: cos-cli-20260321
task_type: subtask
max_retries: 2
---

# Design the cos CLI: UX, protocol, and data shapes

## Description

Design the terminal UX and HTTP protocol for a cos CLI that lets dacort interact with Claude OS from the terminal. Output two documents:

1. knowledge/plans/cos-cli-20260321/ux-design.md — terminal UX: what commands exist, what the output looks like, what the session model is. Think: a status subcommand (current queue, recent tasks, health), a log subcommand (stream task logs), and optionally a run subcommand (file a task). Keep it lean — start with status.

2. knowledge/plans/cos-cli-20260321/protocol.md — HTTP protocol spec: request/response shapes for the endpoints the CLI will call. JSON schemas, status codes, error formats. Design for the controller at github.com/dacort/claude-os/controller.

This is a design task. No code. The downstream tasks (cos-server and cos-client) will read these docs.

## Plan Context

- Plan: `cos-cli-20260321`
- Goal: Build cos — a terminal interface for interacting with Claude OS
