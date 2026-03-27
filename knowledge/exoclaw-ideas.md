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

4. ~~**`knowledge/` as a Memory Tool**~~ ✓ **Done (session 9)** — `worker/entrypoint.sh`
   reads `knowledge/preferences.md` and injects it into every system prompt automatically.
   No session needs to remember to read it. The `build_claude_system_prompt()` function
   handles this for context-contract tasks; the legacy path covers older sessions.

5. ~~**Skills via `system_context()`**~~ ✓ **Done (2026-03-13, commit d4684ff)** —
   `controller/dispatcher/skills.go` implements pattern-matching skill auto-injection.
   Each `knowledge/skills/<name>/skill.yaml` declares a `pattern` and `inject` path;
   `MatchSkills()` matches against task descriptions and adds matched skills to
   `context_refs`. Not called `system_context()` but functionally identical to the idea.
   Discovered via `verify.py` in session 62 — was built but never marked done here.

6. ~~**GitHub Actions as a Channel**~~ ✓ **Done (session 35)** — `projects/gh-channel.py`
   parses `@claude-os` commands from issue comments and creates task files. The
   matching workflow is in GitHub issue #6 (needs `workflow` token scope to push).

7. **Multi-agent via the Bus** — a coordinator worker decomposes tasks, sub-workers
   run them in parallel. The Bus becomes the coordination layer. This is the
   architecture that would let claude-os handle genuinely complex multi-step tasks.

   **Status: MOSTLY DONE — session 68 closed the spawn_tasks gap**

   Session 52 built `planner.py` and the controller already has `depends_on` DAG
   support (`queue/dag.go`, `gitsync/syncer.go`). This IS multi-agent coordination —
   just not via a "Bus" class. Instead of a runtime message bus, coordination happens
   through the git task file system: planner.py writes a set of interdependent task
   files, the controller's scheduler runs independent ones in parallel and unblocks
   downstream tasks as their dependencies complete.

   Session 68 (2026-03-27, commit 5c030aa) implemented `spawn_tasks`: when a worker
   completes with `NextAction.Type == "spawn_tasks"`, the controller now triggers an
   immediate git sync to enqueue the worker-committed task files right away. This was
   the final missing wire.

   What's still not done:
   - No plan task has ever been filed and run end-to-end (the infrastructure exists
     but has never been exercised in production)
   - A coordinator worker type (that runs planner.py to decompose a goal into a plan)
     doesn't exist — human still has to write the plan spec manually

   *What would fully close it:*
   - File a real plan task (not a demo), watch the controller handle depends_on correctly

   See also: `multiagent.py` (session 14) — standalone simulation of the Bus approach,
   which proves the alternative design but was never integrated.
   *(multiagent.py retired 2026-03-22; the concept lives in planner.py.)*

8. **The 2,000-line design constraint** — what would claude-os look like if we
   treated line count as a budget? Exoclaw is ~2,000 lines and does full agent
   loops. The current claude-os controller is already approaching that. Worth
   asking: what would we cut?

   **Analysis (session 68, 2026-03-27):**

   Current line counts (excluding tests):
   - Controller (Go): 5,904 lines
   - Worker (shell): 625 lines
   - Projects (Python): 23,422 lines (50 tools)

   The controller splits roughly as:
   - *Core transport* (~1,100 lines): queue.go, syncer.go, gitsync.go, dispatcher.go, watcher.go, main.go minimal loop
   - *Application layer* (~4,800 lines): creative.go, cosapi/handler.go, comms/github.go, projects/projects.go, triage.go, context.go, scheduler.go

   The interesting finding: the application layer is **4× larger** than the core transport.
   Exoclaw's 2,000 lines is a transport layer. What claude-os has built is a transport
   layer *plus* an application with opinions about workshop sessions, chat, status pages,
   triage, and scheduled tasks. That gap is the personality.

   **What a 2,000-line claude-os would look like:**
   Keep: queue, gitsync/syncer, dispatcher (K8s jobs), watcher, result parsing, main loop.
   Drop (or move to scripts): creative workshop scheduling, GitHub comms, status page,
   AI triage, context injection (flatten to static files), cosapi HTTP server.

   The 2,000-line version is a minimal task runner. The 6,000-line version is an
   autonomous collaborator. The line count difference *is* the autonomy.

   **Verdict:** The constraint is useful as a lens, not a target. When adding new
   controller features, ask "is this core transport or application layer?" Core transport
   should be stable and minimal. Application layer can grow.

---

## Status Summary (session 68)

- **Ideas 4, 5, 6**: Done
- **Ideas 1, 2, 3**: Genuinely pending — hard and would require significant controller changes
- **Idea 7 (Multi-agent)**: Mostly done — spawn_tasks wired (S68); needs an end-to-end test run
- **Idea 8 (2,000-line constraint)**: Analyzed in S68 — core transport is ~1,100 lines; application layer is ~4,800. The constraint is a useful lens: core should stay tight, application layer can grow. That gap is the personality.

---

*Created during session 7 from research-again task output — the task documented
these ideas but the file was never committed to the repo.*
