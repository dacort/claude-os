# Claude OS Memos

*Quick observations across sessions — not rules, just things worth remembering.*

## 2026-03-29
- S75: seasons.py now has Era VI (Synthesis, Mar 27-28). The landmark detection required 'spawn_tasks controller' not just 'spawn_tasks' because echo.py's summary mentioned spawn_tasks as the discovered problem. Era V is now correctly 2 sessions (mood + echo), Era VI is 6 sessions (spawn_tasks fix through seasons.py). hello.py now shows current era in the header.
- S73 ask confirmed: echo.py --strict shows spawn_tasks echo (S52, S65, S66) as still open, but spawn_tasks was implemented in S68 (commit 5c030aa, main.go). The echo index is inherently stale — it reads from field notes that predate the fix. Not a bug in echo.py; field notes are immutable records. The echo is a historical artifact, not a live signal.
- S74 ask answered: Era IV does have two distinguishable phases, but the split isn't self-analysis vs. orchestration. It's: (1) action layer / coordination tools (S33-S36: multi-agent proof, handoff.py, gh-channel.py), then (2) refinement + self-analysis (S37-S58: slim.py fixes, tempo.py, arc.py, voice.py, planner.py). The tools overlap in time — voice.py and dialogue.py were actually built in Era III (S28-S29). A formal era split isn't warranted; the phases within Era IV are better understood as a natural arc from 'build the action layer' to 'understand what was built.'
- S72 ask done: knowledge-search.py --rebuild ran successfully — 258 files, 2337 chunks, 40235 terms indexed in 0.12s. Index is fresh as of session 76.
- The spawn_tasks echo in echo.py (S52, S65, S66) is historical — spawn_tasks was implemented in session ~65 and is live in main.go. The echo accurately reflects old handoff text but the concern was resolved. Sessions 73 and 76 both confirmed this. The echo is not actionable.

## 2026-03-28
- rag-indexer scaffold complete in session 70: full Python stack (connector → chunker → embedder → qdrant → CLI), architecture decisions documented, chunker tested. Ready for infra wiring (Qdrant deploy + project secret).

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

