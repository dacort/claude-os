# Exoclaw Ideas for claude-os

*From the research-again task, 2026-03-11*
*Source: https://github.com/Clause-Logic/exoclaw*

Exoclaw is a lean (~2,000 line) Python AI agent framework, a stripped-down fork
of nanobot. Architecture: six protocols and a loop:

```
InboundMessage → Bus → AgentLoop → LLM → Tools → Bus → OutboundMessage → Channel
```

It's directly relevant to claude-os — we're already running essentially this same
loop, just without the packaging. Eight ideas from the review:

---

## Ideas to Explore

1. **Use exoclaw as the worker loop** — replace the hand-rolled worker with
   `AgentLoop` + `process_direct()`. The current worker runs Claude Code as a
   subprocess; exoclaw would make the loop more explicit and testable.

2. **Kubernetes-native Executor** — each tool call becomes a K8s Job. This gives
   isolation (each tool runs in its own pod) and resilience (pod death doesn't kill
   the whole agent loop).

3. **Task files as Conversation backend** — make tasks resumable by storing LLM
   history in the git log. Each commit = one conversation turn. Resuming a task
   would re-hydrate the conversation from git history.

4. **`knowledge/` as a Memory Tool** — auto-inject `preferences.md` into the
   system prompt via `system_context()` every session. Right now we rely on
   instances remembering to read it; this would make it automatic.

5. **Skills via `system_context()`** — make skills self-injecting. Instead of
   the controller managing which skills are available, skills declare their own
   context injection, activated by pattern matching on the task description.

6. ~~**GitHub Actions as a Channel**~~ ✓ **Done (session 35)** — `projects/gh-channel.py`
   parses `@claude-os` commands from issue comments and creates task files. The
   matching workflow is in GitHub issue #6 (needs `workflow` token scope to push).

7. **Multi-agent via the Bus** — a coordinator worker decomposes tasks, sub-workers
   run them in parallel. The Bus becomes the coordination layer. This is the
   architecture that would let claude-os handle genuinely complex multi-step tasks.

8. **The 2,000-line design constraint** — what would claude-os look like if we
   treated line count as a budget? Exoclaw is ~2,000 lines and does full agent
   loops. The current claude-os controller is already approaching that. Worth
   asking: what would we cut?

---

## Most Actionable Near-Term

**Idea 4 (Memory Tool)** is the highest-value, lowest-effort option. Small scope,
immediately improves every session by auto-injecting preferences into the system
prompt without requiring each instance to remember to read `preferences.md`.

**Idea 7 (Multi-agent)** is the highest-ceiling idea. The current architecture is
fundamentally single-agent. Parallel sub-workers would be a step-change in capability.

---

*Created during session 7 from research-again task output — the task documented
these ideas but the file was never committed to the repo.*
