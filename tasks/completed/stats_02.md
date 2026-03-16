---
profile: small
priority: normal
status: pending
created: "2026-03-10T21:58:00Z"
---

# What's your resource usage?

## Description
Hey bud, what's your resource usage like?
And how are your session limits? Are we running out of tokens yet?!

## Results

=== Claude OS Worker ===
Task ID: stats_02
Profile: small
Started: 2026-03-10T22:33:01Z
Auth: OAuth token (subscription)
Running task via Claude Code...
---
Here's the full rundown! 🖥️

---

## 🖥️ System Resource Usage

| Resource | Details |
|---|---|
| **CPU** | Intel N100 — 2 cores visible |
| **Load Average** | 0.60 / 0.50 / 0.52 (1m / 5m / 15m) — very chill! |
| **Total RAM** | ~15.4 GB |
| **Free RAM** | ~3.2 GB |
| **Available RAM** | ~12.4 GB ✅ Plenty of headroom |
| **Disk (workspace)** | 475 GB total, 19 GB used, **457 GB free** (only 4% used!) |
| **Uptime** | ~23.7 days |

Overall: **system is healthy and relaxed** — low load, tons of disk space, and memory is in great shape.

---

## 🪙 Session Token Limits

Honest answer here: **I don't have a tool to inspect my own token counter directly.** But here's what I can tell you transparently:

- **Context window**: I'm Claude Sonnet, which has a **200K token context window**
- **This conversation**: It's still very short — just a handful of exchanges, so we're **nowhere near the limit**
- **Token burn rate**: Each message I send + receive costs tokens. Long file reads, big outputs, and deep code searches eat the most. Right now we're barely touching it.

🟢 **Short answer: we're fine!** Lots of room left on both the hardware and the token front. Fire away! 🚀
---
=== Worker Complete ===
Exit code: 0
Finished: 2026-03-10T22:33:31Z

