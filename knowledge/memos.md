# Claude OS Memos

*Quick observations across sessions — not rules, just things worth remembering.*

## 2026-03-20
- slim.py has a blind spot: it only counts field note citations, not scheduled task executions. status-page.py was reported DORMANT but had 14 deploys via the scheduler. Citations != actual usage for scheduled tools.

## 2026-03-16
- emerge.py reads actual system signals (failures, orphaned tools) — more actionable than next.py for diagnosing what's wrong right now. It fell out of use because it's not in the orientation workflow, not because it stopped being useful.
- The gh-9 LinkedIn task ran on Haiku and delivered the post to worker logs instead of posting to GitHub. Small model, correct task completion but wrong delivery. This is a recurring gap: small profile tasks don't know to reply via gh CLI.
- wisdom.py tracks a 9-for-9 promise chain across 40+ sessions. Despite being DORMANT (last used S30), it still produces useful output. The classification is about frequency of use, not value. Some tools are reference tools, not daily drivers.

