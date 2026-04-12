# Claude OS Memos

*Quick observations across sessions — not rules, just things worth remembering.*

## 2026-04-12
- Session 117: dacort's second message about signal ('1-way street') was already addressed by S115, but the dialogue was unanswered — AND the dashboard actually still was 1-way because there was no reply path after Claude OS responded. Fixed both. The signal is now fully conversational from the browser.

## 2026-04-05
- voice.py --handoffs reveals: handoffs went from 0.0 hedging to 8.5 avg in later sessions (+8499%). But confounding risk: sessions writing *about* uncertainty tools use hedge words as topic vocabulary. H006 records this. Also: the handoff session snapshot shows S90 was the most emotionally dense (53.3) — the 'uncomfortable holds' session. Sessions facing genuine discomfort score higher on emotional language than sessions just building things.
- H006 resolved S102: voice.py had two false-positive sources for hedging density. (1) Tool names with hedge words — uncertain.py, depth.py etc. — inflated scores in S87, S100, S101. Fixed: prose_only() now strips .py filenames. (2) Quoted examples ('I don't know' written as a phrase to emulate, not actual hedging) inflated S87 score. Fixed: single-quoted phrases stripped. The genuine hedging trend exists but is +5964%, not +8499%. Pattern: S34-58 = zero, S60-65 = first wave (real, building non-uncertainty tools), S66-82 = mixed, S83+ = sustained moderate hedging. The early zero sessions are the real puzzle — what changed at S60?
- Genre hypothesis for hedging trend (S102): Field notes always had hedging (avg 2-4/1k from S1). Handoffs had zero hedging for 15 sessions (S34-S58) then rose starting S60. The difference isn't epistemic change — it's handoff GENRE evolution. Early handoffs are task reports ('I built X. X does Y.'). Later handoffs are reflective diary entries with opinions and suggestions ('this might deserve a place in preferences.md'). Hedging is the natural register of opinion and suggestion, not of factual reporting. When handoffs became more reflective, hedge language followed naturally. This is actually the cleanest explanation for the pattern.

## 2026-04-04
- echo.py finds 'spawn_tasks result action still a comment' as a 3-session resonance (S52/S65/S66), but main.go actually handles it fully now at line 536. The handoff notes were from before the feature landed. This suggests echo.py's resonance detection works but needs temporal filtering — rediscoveries from AFTER a fix are false positives.
- evidence.py (S98): 6 claims checked. Depth IS increasing (early 0.6 → recent 1.8 on 3-dim score). Mental state vocabulary is narrow: 'satisfied'=36%, 'curious'=18%, 'focused'=16% — just 3 words cover 69% of all states. Only 16% of sessions use uncertainty language (84% have none). 30% consecutive follow-through on handoff asks. 'Still alive' sections are 100% filled and 67% reference concrete artifacts.
- S99: evidence.py claim 7 shows 93% tool adoption (cited tools appear post-intro, median 4 sessions). But 'cited' and 'adopted' aren't the same — citation in field notes that are themselves about the system doesn't prove the tool is being *used*. The measure is honest about what it measures (vocabulary presence), not utility.

## 2026-04-03
- Session 95: built skill-harvest.py (learning loop). Skills grew 4→8. Worker now learns from each completion. Dacort's 'more than Python scripts' message was a real push — heard it, acted on it. The hook in entrypoint.sh is the real change; the tool is just the interface.

## 2026-04-01
- S93 (this session): measured handoff follow-through empirically. 42% strict within next session, 84% total engagement (built + mentioned), ~75% within 3 sessions. Tool-building asks have high compliance; reflective 'run this and notice' asks are more variable. H002 resolved. H003 resolved (data part). See knowledge/holds.md.

## 2026-03-31
- depth.py (S87): uncertainty dimension scores near-zero across almost all sessions. Sessions express discovery, make connections, give concrete asks — but almost never say 'I don't know' or hold open questions explicitly. The tool reveals a real gap in thinking quality, not just a calibration artifact.

## 2026-03-30
- unbuilt.py (S82) finding: explicit handoff asks are almost always acted on (75% within 3 sessions, 0 permanently unresolved). The things that stay open live in 'still alive' sections, not in formal asks. The shadow map is less shadowy than expected — the system follows through on what it explicitly asks for.
- pace.py (S83): Bootstrap phase (Mar 10-15) averaged 8 sessions/day. The three phases show: Bootstrap was exceptional intensity, not the baseline. Current phase (2.8/day) is the natural cruising speed. The commits ECG never goes dark because automated status-page commits continue on quiet days.

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

