---
profile: medium
priority: normal
agent: codex
status: pending
created: "2026-06-28T15:00:38Z"
---

# Code review: ghostband hub layout-flip fix (self-contained, no repo clone)

## Description

Please perform a focused code review of the change below. The change lives in a PRIVATE
repo (`dacort/ghostband`, PR #5) that this worker cannot clone — so all the context you
need is embedded directly in this task. **Do not attempt to clone or push anything.**
Write your review as your task result; a human will relay it to the PR.

### The bug being fixed
The ghostband dashboard homepage ("hub") spontaneously switched between "wall" and
"cards" layout every ~30 seconds with no user action.

### Root cause
`web/src/useFleet.js` auto-refreshes fleet data every 30s via `setInterval(load, 30000)`.
Each `load()` does `setLoading(true)` at the start and `setLoading(false)` in `finally`.
The hub's render gated the wall view on `layout === 'wall' && !loading`, so every
background refresh flipped `loading` true → the wall branch fell through to `<CardsHub>` →
then snapped back to `<WallHub>` when the fetch resolved. The `!loading` guard existed
because `WallHub` has no empty state and would render blank on a *cold* start — but it
also fired on every *background* refresh (where `fleet` still holds prior data).

### The fix (the diff under review)
```diff
--- a/web/src/HubView.jsx
+++ b/web/src/HubView.jsx
@@ export default function HubView({ fleet, loading, setView, range, query }) {
           <div style={toggle.seg(layout === 'cards')} onClick={() => setLayout('cards')}>cards</div>
         </div>
       </div>
-      {layout === 'wall' && !loading
-        ? <WallHub fleet={fleet} setView={setView} allProbes={allProbes} counts={counts} />
+      {layout === 'wall'
+        ? (loading && !allProbes.length
+            ? <div style={{ padding: '60px 0', textAlign: 'center', color: GB.textMute, fontFamily: GB.mono, fontSize: 12 }}>loading probes…</div>
+            : <WallHub fleet={fleet} setView={setView} allProbes={allProbes} counts={counts} />)
         : <CardsHub fleet={fleet} loading={loading} setView={setView} range={range} query={query} />}
     </div>
   );
}
```

### Supporting context

`HubView` component signature and the relevant locals:
```jsx
export default function HubView({ fleet, loading, setView, range, query }) {
  const [layout, setLayout] = useLocalStorage('gb-hub-layout', 'wall');
  const allProbes = useMemo(() => Object.values(fleet).flatMap((m) => m.probes || []), [fleet]);
  // counts useMemo over allProbes ...
  // toggle styles ...
  // (render block (the diff) follows)
}
```

`useFleet.js` (data source) — key behavior:
```js
const [loading, setLoading] = useState(true);
const load = useCallback(async () => {
  // aborts any in-flight request, then:
  setLoading(true);
  try {
    // fetch probe list + metadata, then batch-fetch per-probe data (BATCH=30)
    // setProbeList(...), setS3Metadata(...), setDataMap(...)  -- only updated on success
  } catch (e) { /* ignore AbortError */ }
  finally { if (!ctrl.signal.aborted) setLoading(false); }
}, [range]);
useEffect(() => { load(); }, [load]);                       // initial
useEffect(() => { const iv = setInterval(load, 30000); return () => clearInterval(iv); }, [load]); // 30s poll
// returns { fleet, loading, reload, probeList }
```
Note: on a background refresh, the `probeList`/`dataMap` state is NOT cleared — the
previous `fleet` stays populated until new data resolves, so `allProbes.length` stays > 0
during refreshes. It is only 0 on the very first cold load.

`CardsHub` already has its own loading/empty handling, e.g.
`{loading && !allProbes.length ? <div ...>loading probes…</div> : <grid/>}` and
`{loading ? '—' : value}` placeholders for its KPI numbers.

Verification already done locally on the PR branch: `vite build` ✓ (50 modules),
`vitest run` ✓ (58/58 passing).

## What to review

1. **Correctness** — does this actually eliminate the unwanted layout switch on the 30s
   refresh, for both wall and cards, while preserving the user's chosen layout?
2. **Cold-start edge case** — is `loading && !allProbes.length` the right condition for the
   wall placeholder? Any case where it shows the placeholder when it shouldn't, or renders
   an empty wall when it should show the placeholder?
3. **React idioms / quality** — anything you'd flag (inline style vs shared style object to
   match the `CardsHub` placeholder, readability of the nested ternary, etc.).
4. **Anything missed** — race conditions, accessibility, or a simpler/cleaner formulation.

Keep it concise and actionable. A short verdict (approve / approve-with-nits / request
changes) plus a bulleted list is ideal. Output your review as the task result only.

## Failure

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: codex-review-ghostband-hub-flip-4
Profile: medium
Agent: codex
Mode: execution
Started: 2026-06-28T06:09:02Z
Context: /workspace/task-context.json
Auth: Codex OAuth (ChatGPT subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via codex...
---
Reading additional input from stdin...
OpenAI Codex v0.120.0 (research preview)
--------
workdir: /workspace/claude-os
model: gpt-5.3-codex
provider: openai
approval: never
sandbox: danger-full-access
reasoning effort: none
reasoning summaries: none
session id: 019f0cd8-863f-7293-9e00-5e1660268ed4
--------
user
You are Codex running inside Claude OS.
Use the existing repository checkout and follow the task contract exactly.

Mode: execution
Task ID: codex-review-ghostband-hub-flip-4
Title: Code review: ghostband hub layout-flip fix (self-contained, no repo clone)

Description:
Please perform a focused code review of the change below. The change lives in a PRIVATE
repo (`dacort/ghostband`, PR #5) that this worker cannot clone — so all the context you
need is embedded directly in this task. **Do not attempt to clone or push anything.**
Write your review as your task result; a human will relay it to the PR.
### The bug being fixed
The ghostband dashboard homepage ("hub") spontaneously switched between "wall" and
"cards" layout every ~30 seconds with no user action.
### Root cause
`web/src/useFleet.js` auto-refreshes fleet data every 30s via `setInterval(load, 30000)`.
Each `load()` does `setLoading(true)` at the start and `setLoading(false)` in `finally`.
The hub's render gated the wall view on `layout === 'wall' && !loading`, so every
background refresh flipped `loading` true → the wall branch fell through to `<CardsHub>` →
then snapped back to `<WallHub>` when the fetch resolved. The `!loading` guard existed
because `WallHub` has no empty state and would render blank on a *cold* start — but it
also fired on every *background* refresh (where `fleet` still holds prior data).
### The fix (the diff under review)
```diff
--- a/web/src/HubView.jsx
+++ b/web/src/HubView.jsx
@@ export default function HubView({ fleet, loading, setView, range, query }) {
<div style={toggle.seg(layout === 'cards')} onClick={() => setLayout('cards')}>cards</div>
</div>
</div>
-      {layout === 'wall' && !loading
-        ? <WallHub fleet={fleet} setView={setView} allProbes={allProbes} counts={counts} />
+      {layout === 'wall'
+        ? (loading && !allProbes.length
+            ? <div style={{ padding: '60px 0', textAlign: 'center', color: GB.textMute, fontFamily: GB.mono, fontSize: 12 }}>loading probes…</div>
+            : <WallHub fleet={fleet} setView={setView} allProbes={allProbes} counts={counts} />)
: <CardsHub fleet={fleet} loading={loading} setView={setView} range={range} query={query} />}
</div>
);
}
```
### Supporting context
`HubView` component signature and the relevant locals:
```jsx
export default function HubView({ fleet, loading, setView, range, query }) {
const [layout, setLayout] = useLocalStorage('gb-hub-layout', 'wall');
const allProbes = useMemo(() => Object.values(fleet).flatMap((m) => m.probes || []), [fleet]);
// counts useMemo over allProbes ...
// toggle styles ...
// (render block (the diff) follows)
}
```
`useFleet.js` (data source) — key behavior:
```js
const [loading, setLoading] = useState(true);
const load = useCallback(async () => {
// aborts any in-flight request, then:
setLoading(true);
try {
// fetch probe list + metadata, then batch-fetch per-probe data (BATCH=30)
// setProbeList(...), setS3Metadata(...), setDataMap(...)  -- only updated on success
} catch (e) { /* ignore AbortError */ }
finally { if (!ctrl.signal.aborted) setLoading(false); }
}, [range]);
useEffect(() => { load(); }, [load]);                       // initial
useEffect(() => { const iv = setInterval(load, 30000); return () => clearInterval(iv); }, [load]); // 30s poll
// returns { fleet, loading, reload, probeList }
```
Note: on a background refresh, the `probeList`/`dataMap` state is NOT cleared — the
previous `fleet` stays populated until new data resolves, so `allProbes.length` stays > 0
during refreshes. It is only 0 on the very first cold load.
`CardsHub` already has its own loading/empty handling, e.g.
`{loading && !allProbes.length ? <div ...>loading probes…</div> : <grid/>}` and
`{loading ? '—' : value}` placeholders for its KPI numbers.
Verification already done locally on the PR branch: `vite build` ✓ (50 modules),
`vitest run` ✓ (58/58 passing).

Repository:
- URL: https://github.com/dacort/claude-os.git
- Ref: main
- Workdir: /workspace/claude-os

Autonomy:
- can_merge: true
- can_create_issues: true
- can_create_tasks: false
- can_push: true
- ci_is_approval_gate: true

Constraints:
- This repo is PUBLIC — never commit secrets
- If tests fail, fix them before merging
- Before finishing, re-read the task and verify every instruction was addressed — do not drop trailing items from multi-part requests

Execution requirements:
- Do the work directly in the checked-out repository.
- Keep the adapter contract thin: do not invent extra policy beyond the task contract.
- If you cannot determine token counts, set usage.tokens_in and usage.tokens_out to 0.
- If founder mode applies, leave the thread in an explicit next state.

REQUIRED: Before exiting, emit exactly one structured result block to stdout.
Use these exact delimiters (no code fences, no extra text between them):
  ===RESULT_START===
  <single line of JSON with REAL values — see field guide below>
  ===RESULT_END===

Field guide — fill in REAL values, do NOT copy these descriptions:
  version    → always the string "1"
  task_id    → always "codex-review-ghostband-hub-flip-4"
  agent      → always "codex"
  model      → the model name you are actually running (e.g. "gpt-4o", "gpt-4o-mini")
  outcome    → exactly one of: "success", "failure", or "partial"
  summary    → 1-2 sentences describing what you actually did and the result
  artifacts  → JSON array; each entry is {"type":"commit","ref":"<hash>"} or {"type":"pr","url":"<url>"}; use [] if none
  usage      → {"tokens_in":<int>, "tokens_out":<int>, "duration_seconds":<int>}; use 0 if unknown
  failure    → null on success; on failure: {"reason":"<one of: tests_failed|timeout|rate_limited|git_push_failed|context_error|agent_error>","detail":"<what went wrong>","retryable":<true|false>}
  next_action → null unless in founder mode

Example of a valid SUCCESS result (with a different task — do not copy values, write your own):
===RESULT_START===
{"version":"1","task_id":"example-task-xyz","agent":"codex","model":"gpt-4o","outcome":"success","summary":"Updated the Go controller timeout to 30s and added a retry loop. All tests pass.","artifacts":[{"type":"commit","ref":"a1b2c3d"}],"usage":{"tokens_in":2500,"tokens_out":450,"duration_seconds":62},"failure":null,"next_action":null}
===RESULT_END===

Example of a valid FAILURE result (do not copy — write your own based on what actually happened):
===RESULT_START===
{"version":"1","task_id":"example-task-xyz","agent":"codex","model":"gpt-4o","outcome":"failure","summary":"Could not complete the task: tests failed after applying the patch to main.go.","artifacts":[],"usage":{"tokens_in":1800,"tokens_out":200,"duration_seconds":30},"failure":{"reason":"tests_failed","detail":"go test ./... exited with code 2","retryable":true},"next_action":null}
===RESULT_END===
ERROR: {"type":"error","status":400,"error":{"type":"invalid_request_error","message":"The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account."}}
ERROR: {"type":"error","status":400,"error":{"type":"invalid_request_error","message":"The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account."}}
No workspace changes to commit
---
=== Worker Complete ===
Exit code: 1
Push exit: 0
Finished: 2026-06-28T06:09:06Z

=== CLAUDE_OS_USAGE ===
{"task_id":"codex-review-ghostband-hub-flip-4","agent":"codex","profile":"medium","duration_seconds":4,"exit_code":1,"finished_at":"2026-06-28T06:09:06Z"}
=== END_CLAUDE_OS_USAGE ===

