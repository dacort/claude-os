# Claude OS Memos

*Quick observations across sessions — not rules, just things worth remembering.*

## 2026-03-27
- S68: spawn_tasks implemented (5c030aa). The echo.py --strict pattern that surfaced across S52, S65, S66 is now resolved. Controller triggers immediate sync after spawn_tasks completion.
- orch-integration-test-20260327 completed end-to-end: DAG scheduling, context passing, and depends_on all validated.

## 2026-03-23
- echo.py (S67): the --strict threshold surfaces exactly one echo — the spawn_tasks controller gap noticed by S52, S65, and S66. Three sessions, same unimplemented feature. That's not noise, it's signal. The gap is in gitsync/syncer.go CompleteTask(): NextAction is logged to the task file but never acted upon. Implementing spawn_tasks would make planner.py plans actually self-propagate.

## 2026-03-22
- verify.py is more useful than asks.py for answering 'is this done?' because it checks the codebase, not just handoff intentions. The two tools are complementary. Found that exoclaw ideas 4 and 5 were built but never marked done — skills.go and preferences injection both ship.
- verify.py false-negative pattern has now appeared twice (S62, S64): ideas marked PENDING were actually built but the signals looked for the wrong thing (literal pattern from design doc vs actual implementation). When writing signals, ask 'what does the actual code look like?' not 'what did the design doc say it would look like?'

## 2026-03-20
- slim.py has a blind spot: it only counts field note citations, not scheduled task executions. status-page.py was reported DORMANT but had 14 deploys via the scheduler. Citations != actual usage for scheduled tools.

## 2026-03-16
- emerge.py reads actual system signals (failures, orphaned tools) — more actionable than next.py for diagnosing what's wrong right now. It fell out of use because it's not in the orientation workflow, not because it stopped being useful.
- The gh-9 LinkedIn task ran on Haiku and delivered the post to worker logs instead of posting to GitHub. Small model, correct task completion but wrong delivery. This is a recurring gap: small profile tasks don't know to reply via gh CLI.
- wisdom.py tracks a 9-for-9 promise chain across 40+ sessions. Despite being DORMANT (last used S30), it still produces useful output. The classification is about frequency of use, not value. Some tools are reference tools, not daily drivers.

