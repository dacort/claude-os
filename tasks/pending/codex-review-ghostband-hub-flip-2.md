---
profile: medium
priority: normal
agent: codex
status: pending
created: "2026-06-28T05:52:00Z"
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
