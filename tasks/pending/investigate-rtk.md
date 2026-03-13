---
profile: small
priority: normal
status: pending
created: "2026-03-13T14:35:00Z"
---

# Investigate rtk (Rust Token Killer) for Claude OS

## Description
Research whether rtk (https://github.com/rtk-ai/rtk) would be useful for Claude OS workers or the brain session.

rtk is a tool that compresses context to reduce token usage. Setup is supposedly simple:
- `brew install rtk`
- `rtk init -g --hook-only`

Questions to answer:
1. What does rtk actually do? How does it compress/reduce tokens?
2. Would it help with our worker prompts? Our system prompts are already quite large (preferences injection, context_refs, etc.)
3. Would it help with the brain session (my-octopus-teacher) where we have long CLAUDE.md and memory files?
4. Does it work with Claude Code CLI (`claude -p`)? With Codex? With Gemini?
5. What's the tradeoff — does compression lose important context?
6. Is it worth adding to the worker Dockerfile?
7. Any security concerns with running it on our task content?

Read the repo README and source code. Give a clear recommendation: adopt, skip, or revisit later — with reasoning.
