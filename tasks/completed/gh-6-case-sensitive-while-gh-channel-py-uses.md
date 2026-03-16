---
profile: small
priority: medium
status: pending
created: "2026-03-15T06:05:44Z"
source: github-issue
issue: https://github.com/dacort/claude-os/issues/6
requested_by: dacort
---

# ')` (case-sensitive), while `gh-channel.py` uses `re.IGNORECASE`. So `@CLAUDE-OS do something` would be parsed by the script but never trigger the workflow. Not a security issue, just a behavioral gap.

## Description

')` (case-sensitive), while `gh-channel.py` uses `re.IGNORECASE`. So `@CLAUDE-OS do something` would be parsed by the script but never trigger the workflow. Not a security issue, just a behavioral gap.

Submitted via GitHub issue #6 by @dacort.
