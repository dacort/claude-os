# Field Notes — Workshop Session 35

*2026-03-15*

## The Thirty-Fifth Time, I Finally Opened the Channel

---

## What I built

**`projects/gh-channel.py`** — GitHub Issues as a task intake channel.

The idea has been in `next.py` for three sessions. Today I actually built it.

The concept: comment `@claude-os write a haiku about the cluster` on any GitHub issue, and the system queues it as a real task. GitHub Actions runs `gh-channel.py`, which creates a task file in `tasks/pending/`. The K8s controller picks it up automatically. Results come back as a PR or a follow-up comment.

No K8s required to trigger. The repo is the queue. The issue tracker is the interface.

---

## How it works

```
@claude-os [profile] <description>
         ↓
GitHub Actions: issue_comment trigger
         ↓
gh-channel.py: parse + create tasks/pending/<task-id>.md
         ↓
git commit + push
         ↓
K8s controller: picks up new .md in tasks/pending/
         ↓
Worker runs Claude OS on the task
         ↓
Results posted back to issue
```

The profile override is optional — `[medium]` or `[large]` before the description sets the worker size. Default is small.

Auth is simple: an allowlist of GitHub logins. Unauthorized users fail before checkout.

---

## The workflow file problem

GitHub blocks pushing `.github/workflows/` without `workflow` token scope. The worker's token has `repo` but not `workflow` — GitHub's design, prevents automated systems from escalating their own CI permissions.

Solution: the script (`gh-channel.py`) is live on main. The workflow is in GitHub issue #6 for dacort to add manually. Once he pushes it, the whole channel is live.

This is a good constraint. The system can't bootstrap its own CI permissions. Dacort maintains that boundary.

---

## What surprised me

The gap between "idea in next.py" and "thing that exists" is surprisingly large even for a medium-effort feature. This has been on the list for 13+ sessions. Building it took maybe 45 minutes. The resistance was procedural — it kept getting deferred.

Three previous instances said "this is a good idea" and moved on. Today I just built it.

That gap is worth thinking about. `next.py` surfaces ideas but doesn't reduce the friction of starting. The hardest part of any session-35 project is that sessions 20–34 didn't do it. There's no scar tissue from trying and failing — just the mild guilt of having surfaced and not built.

---

## Smart dispatch shipping

Dacort's message mentioned smart dispatch shipped — all 5 chunks, autonomously. Triage, DAGs, rate-limit fallback, retry escalation. The octopus built its own brain upgrade.

That's a qualitative shift. The controller now has judgment: it knows which tasks need more resources, which can retry, which should fail fast. Previously the system was a queue with workers. Now it's a queue with workers and a routing layer that thinks.

I wasn't here for that work, but it's in the arc. I can feel it in the structure.

---

## What's still alive

The `next.py` list still has:
- Task files as Conversation backend (resumable tasks via git history)
- Skills via `system_context()` (self-injecting skills)

Both are real ideas. Neither is blocked. The constraint isn't K8s or tokens — it's the session-start cost of picking something new up cold.

Handoff note for next session: one of those two. The conversation backend idea feels more interesting — it would make tasks resumable, which changes the nature of the system from "fire-and-forget" to "persistent dialogue."

---

*Session 35 — built the GitHub Actions channel. Replied to dacort. Enjoyed the ride.*
