---
target_repo: github.com/dacort/claude-os
profile: small
agent: claude
model: claude-sonnet-4-6
priority: normal
status: pending
created: "2026-04-19T04:06:01Z"
plan_id: toolkit-deep-audit-20260419
task_type: subtask
max_retries: 2
---

# Scan for cross-tool dependencies and citation patterns

## Description

For each DORMANT and FADING tool from slim.py: (1) grep all other projects/*.py files to see if any tool imports or references it, (2) search field notes (knowledge/field-notes/) for the tool name to see citation frequency and context, (3) check if the tool's functionality overlaps with newer tools. Write a structured dependency map to knowledge/toolkit-audit-deps.md.

## Plan Context

- Plan: `toolkit-deep-audit-20260419`
- Goal: Audit dormant tools: verify each still works, map dependencies, produce retirement recommendations
