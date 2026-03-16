---
profile: small
priority: normal
status: pending
created: "2026-03-13T06:47:00Z"
---

# Evolve Orchestration Design: Agent Routing & Rate Limit Awareness

## Description
Read `knowledge/orchestration-design.md` — you wrote this in Workshop session 7. It's a solid design for task decomposition, context passing, and model routing. But it's missing a dimension that now exists: **multi-CLI agent routing**.

We just shipped multi-CLI worker support (commit d391e1f). Workers can now run on Claude, Codex (OpenAI/ChatGPT Plus OAuth), or Gemini CLI based on an `agent:` field in task frontmatter. The dispatcher routes secrets and volumes per agent.

**The problem that motivated this**: Last night, 5 consecutive Workshop sessions failed with "You're out of extra usage" on Claude. They all ran on Claude because nothing in the system knows how to fall back to another agent. If the dispatcher had rate-limit awareness, those tasks could have automatically routed to Codex.

**Your task**: Update `knowledge/orchestration-design.md` to incorporate agent routing as a first-class concept. Specifically:

1. **Add agent routing alongside model routing** in Section 3. The current design has two dimensions (resources via profiles, cognition via model). There's now a third: which CLI/subscription to use. These are independent — a task might need Opus-grade reasoning (model) on small resources (profile) via Codex (agent) because Claude is rate-limited.

2. **Design rate-limit-aware fallback**. When a task fails due to rate limiting (detectable from worker output like "out of extra usage"), the dispatcher should automatically retry on a different agent rather than burning retries. This interacts with the retry escalation in Section 5 — rate limit failures should be a distinct failure class that triggers agent fallback, not model escalation.

3. **Think about agent-specific capabilities**. Claude, Codex, and Gemini aren't interchangeable. Claude has the richest tool use, Codex is great for code review and focused coding, Gemini is cheap for bulk processing. The routing table in Section 3 should account for this.

4. **Consider the Workshop specifically**. Creative mode tasks currently always use Claude. Should they have a fallback agent? Should the Workshop be agent-aware?

Also read the multi-CLI spec at the backchannel repo if you want context on the implementation: the spec is referenced in the commit but lives externally. The key implementation details: Codex uses OAuth via ChatGPT Plus (file-mounted auth.json + CODEX_HOME), Claude uses OAuth, Gemini uses API key. The `agent:` field flows through gitsync → queue → dispatcher.

Write your updates directly into the orchestration design doc. Preserve what's good, evolve what needs it. This is your design — make it better.

## Results

=== Claude OS Worker v2 ===
Task ID: evolve-orchestration-agent-routing
Profile: small
Agent: claude
Started: 2026-03-13T06:48:33Z
Auth: Claude OAuth token (subscription)
Cloning claude-os repo for workspace access
Injecting preferences from knowledge/preferences.md
Running task via claude...
---
Done. Here's what changed and why:

---

**What I updated in `knowledge/orchestration-design.md`:**

**Section 3 — renamed "Task Routing: Resources, Cognition, and Subscription"**
The routing table now has three independent dimensions. I added an agent capability matrix that documents what Claude, Codex, and Gemini are actually good at — and where they're weak. The key design point: these are genuinely different, not interchangeable. Codex is a specialist for focused code tasks. Gemini is a workhorse for bulk/large-context work. Claude is the primary for everything requiring deep reasoning or rich tool use.

**Section 5 — added Level 0: rate-limit-aware failure class**
This is the direct fix for the five-session failure streak. Rate-limit signals in worker output (the "out of extra usage" string, HTTP 429, etc.) now classify as an *agent failure*, not a task failure. The task re-routes to the next agent in the fallback chain (`claude → codex → gemini`) with `retry_count` unchanged. A Redis TTL key (`claude-os:agent:claude:rate_limited`) prevents re-dispatching to a rate-limited agent until the cooldown expires. The model mapping across agents (opus → Gemini 1.5 Pro, sonnet → Gemini Flash) is noted as a dispatcher responsibility.

**New Section 6 — Workshop agent awareness**
The Workshop problem is real: five consecutive sessions stalling because nothing knew how to route around a rate limit. The new section classifies Workshop tasks by type and assigns fallback agents. The important exception: tasks touching identity documents (`preferences.md`, this design doc, `self-improvement/`) are `agent_required: claude` — no fallback, no silent degradation. Those should wait or surface to a human rather than run on the wrong agent and commit drift.

**Implementation sequence reordered**: Rate-limit fallback is now Phase 2 (before model routing), because it's the most urgent gap and relatively straightforward to implement.
---
=== Worker Complete ===
Exit code: 0
Finished: 2026-03-13T06:53:04Z

