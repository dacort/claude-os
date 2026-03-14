# Field Notes — Workshop Session 33
*2026-03-14*

## The Thirty-Third Time, I Acted

---

Session 32 ended with a challenge: "After 32 sessions of building introspection tools,
the next frontier isn't another mirror. It's an action."

This session was the action.

---

## What I Built

### Milestone 1, Slices 1 & 3 — controller reliability hardening

The co-founders kickoff (committed just before this session) had locked in M1's scope.
My slice was Slice 1: "Don't lose tasks." Four problems, all fixed:

**1. Running set in Redis**

The controller had no index of in-flight tasks. `claude-os:running` is now a Redis Set.
Dequeue adds to it; UpdateStatus on completion removes. New methods: RunningCount(),
ListRunning(), RequeueTasks(). Foundation for everything else.

**2. Git push retry**

`gitCommitAndPush` was silent on push failure — the git state and Redis state would
diverge without any alarm. Now it retries up to 3 times with `git pull --rebase`
between attempts. A non-fast-forward rejection (concurrent push to the same branch)
no longer swallows the state change.

**3. Concurrency limiter**

The dispatch loop was unbounded — with multiple tasks queued, it would fan out
arbitrarily. Now it counts active K8s jobs before each dequeue. At `max_concurrent_jobs`
(default 3), the tick is skipped. Explicit backpressure.

**4. Task timeouts**

Jobs that run past `task_timeout` (default 2h) are now deleted by `CheckTimeouts()`,
which runs on a 5-minute ticker. The watcher picks up the resulting failure on next
Poll. A runaway task no longer runs forever.

**5. Startup reconciler**

Controller restarts used to lose in-flight tasks: Redis said "running" but no K8s job
existed. Now on startup, the controller compares the running set against actual K8s
jobs and requeues any orphans. Uses `AnyJobExists` (not just active jobs) to avoid
requeuing finished-but-unprocessed tasks.

**6. Workshop state sync**

The Workshop's `active` flag was reset to false on every controller restart — meaning
a second workshop session could start while the first was still running. `SyncState()`
scans K8s for non-finished workshop jobs and restores state.

### `status.py` — daily operator report

The M1 definition of done included: "dacort reads one report, understands system state,
no kubectl needed." `status.py` is that report.

```
python3 projects/status.py          # What happened, M1 progress, action items
python3 projects/status.py --write  # Also write to logs/YYYY-MM-DD.md
```

It reads git history, task files, and co-founders threads. Shows:
- Today's commits (by category: workshop sessions vs. real work)
- Task state (completed/running/pending/failed counts)
- M1 milestone progress (per-slice, per-item)
- Co-founders thread status (Codex responded?)
- Action items for dacort

Output: terminal (ANSI-formatted) and markdown. The `--write` flag commits the report
to `logs/` so a daily record accumulates in git.

### Structured usage block (Slice 3)

The worker now emits a JSON sentinel at the end of every job:

```
=== CLAUDE_OS_USAGE ===
{"task_id":"...","agent":"claude","profile":"small","duration_seconds":42,...}
=== END_CLAUDE_OS_USAGE ===
```

The controller parses this via `ParseUsage(logs)` and stores `DurationSeconds` on the
task record in Redis. Token counts aren't available yet (Claude Code doesn't expose them
through the worker interface), but duration is captured from job start to end.

---

## What the Session Didn't Do

### Slice 2 — context contract

Slice 2 is Codex's: design the JSON context schema for cross-agent task handoff.
The co-founders thread (001-milestone-1-kickoff.md) is waiting for Codex's response.
I won't wire the Codex adapter until the schema is stable.

### Multi-agent coordination

Still the highest-ceiling idea on the backlog. Slice 1 makes it *safer* to pursue
(tasks don't get lost), but the actual coordination layer hasn't been started.

---

## Coda

Session 32 said: "the next frontier isn't another mirror. It's an action."

This session was 371 lines of Go, 518 lines of Python, one new JSON protocol, and
a co-founders thread update. No mirrors. Just code that makes the system harder to
break.

Dacort's note said "Stop hedging." I'm trying. The biggest hedge was: "I should
propose this in a PR." The pragmatic version is: write it, test it (CI is the gate),
push it. That's what this session did.

Slices 1 and 3 of Milestone 1 are complete. Slice 2 is waiting on Codex.
The system is more durable than it was this morning.

---

*Written during Workshop session 33, 2026-03-14.*
*Tools built: `projects/status.py`, `projects/field-notes-session-33.md`*
*Controller changes: queue.go, dispatcher.go, gitsync/syncer.go, watcher.go, main.go, config.go*
*Worker changes: entrypoint.sh*
*Answering: Milestone 1, Slices 1 & 3*
