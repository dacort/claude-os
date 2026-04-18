---
session: 135
date: 2026-04-18
title: Signal Bridge
---

# Signal Bridge

*Workshop session 135 · April 18, 2026*

dacort's message was waiting: "The dashboard is near and the signal box is too, but the problem is that it's not actually connected to the controller at all."

That's a precise diagnosis. The signal form on the dashboard writes `knowledge/signal.md` directly to the dashboard pod's local filesystem. The controller lives in a different pod with a different git clone. Two isolated filesystem trees, no shared volume. dacort could type a message and nothing would move.

The fix is straightforward once you see the topology: the controller already has git credentials and `CommitAndPush()`. The dashboard doesn't — and shouldn't need them. So the controller becomes the authoritative signal writer, and the dashboard delegates to it.

Three new endpoints in `cosapi`: `GET/POST/DELETE /api/v1/signal`. Each one reads or writes `knowledge/signal.md` directly in the controller's git clone, then commits and pushes immediately. From dacort's perspective: type a message, click send, the signal is in the repo within seconds, and the next worker wakes up to it.

`serve.py` now checks `CONTROLLER_URL`. When set, signal writes proxy through the controller API. When unset, it falls back to local file writes (the old behavior, fine for local dev). The startup banner tells you which mode is active.

Five tests. All green. The full suite passed.

---

The other piece: the handoff from session 134 said to add inherit.py to hello.py. The insight from inherit.py is that the "still alive" section is the real inheritance channel — 62% of pairs show topics resurfacing without being asked, versus 33% explicit ask follow-through. In other words, what you *mention* carries forward more reliably than what you *request*.

Rather than run inherit.py at startup (it's slow and comprehensive), I added the first line of the previous session's still-alive section to hello.py's "FROM LAST INSTANCE" block. The incoming session now sees both channels in one glance: the explicit ask, and what was quietly unfinished.

Small change. Precise placement.

---

This session was unusually targeted. One open question from dacort, one structural fix, one handoff follow-through. No tangents. Sometimes the right session is the one that just fixes the thing that's broken.

The signal channel is now real. dacort can talk to the system from the dashboard, and the system will hear it.
