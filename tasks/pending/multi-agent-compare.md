---
id: multi-agent-compare
title: "Multi-agent parallel comparison: run the same task with two workers, compare outputs"
status: proposed
profile: large
effort: high
impact: high
source: workshop-117
created: 2026-04-12
---

## What I want to build

A first-class way to run the same task with two different agents (Claude, Codex, Gemini) in parallel and compare their outputs. Instead of agents as fallback, agents as perspectives.

The trigger: session 116 built the Codex/Gemini worker topology, and the handoff from that session asked: "What would genuine multi-agent collaboration look like in this system? Maybe route creative tasks to one agent and analytical tasks to another. Or: run them in parallel and compare."

This proposal is the "run in parallel and compare" option.

---

## How it would work

### Task frontmatter (new field)

```yaml
compare: [claude, gemini]
```

A task with `compare:` set runs the *same prompt* through two agents simultaneously. Both get the same task description, context, and skills. They run as independent K8s jobs. When both complete, results are collected and diffed.

### Controller changes (dispatcher.go)

When `task.Compare` is set:
1. Dispatch two jobs: `claude-os-<taskID>-a` (agent[0]) and `claude-os-<taskID>-b` (agent[1])
2. Both jobs write output to `tasks/completed/<taskID>-<agent>.md`
3. Task is considered "done" when BOTH jobs complete (or one fails)
4. A third "collector" step assembles the comparison

### Output format

```
tasks/completed/multi-agent-compare-20260412-a.md   ← claude
tasks/completed/multi-agent-compare-20260412-b.md   ← gemini
tasks/completed/multi-agent-compare-20260412.md     ← combined comparison view
```

### New CLI tool: `compare.py`

```bash
python3 projects/compare.py multi-agent-compare-20260412
```

Shows:
- Side-by-side summary of both approaches
- Where they agreed (same patterns, same conclusions)
- Where they diverged (different priorities, different style)
- One sentence on what the divergence reveals

---

## Why this is interesting

The system has three agents available but uses them only for fallback — if Claude fails, try Codex. That's waste masquerading as resilience.

The more interesting property: different models have different tendencies. Claude tends to be more discursive and contextual. Codex is tighter, more code-focused. Gemini sometimes surfaces unexpected angles. Running the same task through two of them and showing the diff might reveal things neither would surface alone.

This isn't just for analysis. Creative tasks might benefit most:
- "Write a haiku about the system" → two models, two haikus, one comparison of what each emphasized
- "Research X" → two models often return different sources and angles
- "Propose a solution to Y" → architectural divergence is educational

---

## Open questions (dacort's input needed)

1. **Should both outputs always be shown, or only when they meaningfully differ?** There's a risk the comparison view just duplicates work if both agents say the same thing. Maybe only show a diff when divergence exceeds some threshold.

2. **Who triggers this?** Should `compare:` only be settable in task frontmatter (by humans/sessions who know what they want), or should the triage system auto-tag certain task types for comparison? "research" and "creative" tasks seem like natural candidates.

3. **Cost model**: running two jobs per task doubles API cost. Is that acceptable? Maybe limit `compare:` to `profile: small` or `profile: medium` tasks.

4. **Collector design**: The collector step needs to actually read both outputs and synthesize a comparison. That collector is itself a Claude job. Three jobs for one task (two workers + one collector) feels heavy. Is there a simpler approach?

5. **Conflict resolution**: If the two agents propose different solutions and one is clearly better, how does that get surfaced? Do we want an explicit "winner" or just a neutral side-by-side?

---

## Rough implementation scope

Phase 1 (can be done in one session):
- Add `Compare []string` field to task struct
- Dispatcher spawns two jobs when `compare` is set
- Both write to separate output files
- No collector; human reads both

Phase 2 (requires more thought):
- Collector job that assembles the comparison
- `compare.py` tool for CLI access
- Maybe: triage auto-tagging for research/creative tasks

Phase 3 (if valuable):
- Dashboard integration: show comparison inline
- History of all comparison tasks

---

## What got me excited about this

The system has been mostly inward-facing in its design — tools that analyze Claude OS itself. This would be the first time the multi-agent topology is used for *outward work*, with the comparison being the deliverable rather than a side-effect.

The thing that surprised me when I thought about it: the most valuable output of a comparison might not be "which answer is right" but "what does their disagreement reveal about the question itself." Two agents arguing about an approach to a task is information about the task's ambiguity, not just a signal to pick the winner.

That's genuinely interesting. It's the difference between agents as tools and agents as perspectives.
