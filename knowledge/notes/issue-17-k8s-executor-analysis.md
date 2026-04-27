# Issue #17 Analysis: K8s-native Tool Executor

*From Session 148 (2026-04-27) — written to knowledge/ since issue comment token lacks write scope*

Dacort, the GITHUB_TOKEN doesn't have `issues:write` scope so I can't post
this directly. Copying below in case it's useful for your decision.

---

## Three Questions, Three Answers

**Q1: Does tool-level isolation matter?**

Recommendation: **Option B (hybrid), default off.**

The math argues against full isolation for current use cases. `k8s_exec` adds
at least 5-10s per tool call (job startup + 2s polling). A Workshop session
makes 30-60 tool calls. Full isolation = 3-10 minutes of overhead per session,
for operations like `cat file.md` or `python3 project.py`. That's not viable.

The hybrid design makes sense for a different reason: Claude Code already knows
which operations are risky. The tool description for `k8s_exec` is the signal —
Claude will naturally reach for `k8s_exec` when it wants isolation and native
Bash when it wants speed.

Suggested change: don't enable `MCP_K8S_TOOLS` as a global setting per task
type. Let specific tasks opt in via frontmatter (`mcp_tools: true`). Workshop
sessions stay on native Bash. A future "sandboxed" task type opts in. The
frontmatter support (flagged as not done in state.md) is the right wire.

**Q2: Workspace sharing**

Recommendation: **Option C (accept the limitation for now).**

For the primary use case — isolating risky network/system commands — workspace
access isn't needed. `curl`, `wget`, standalone scripts, and resource-intensive
processes all work without the parent's files. The commands that *need*
workspace access are the ones you'd run with native Bash anyway.

If this becomes a practical blocker, git clone per job (Option B) is the right
path — scoped to specific jobs that need it. PVCs add cluster-level complexity
that blocks shipping a working feature.

**Q3: Priority**

Recommendation: **Yes, merge this.**

The feature is opt-in and the MCP protocol layer is solid. Two things before
merging:

1. Real-cluster test: apply the RBAC manifest and run one task with
   `MCP_K8S_TOOLS=true` manually set. "Self-test passes" ≠ "K8s API in prod."
2. Auth issues (#16 and #4) are separate — they need human action, not a
   code fix, and don't block this feature.

What's missing from "done" on the branch:
- Dispatcher support for `mcp_tools: true` in task frontmatter (flagged in state.md)
- One real cluster test

Everything else is ready.

---

## Summary Table

| Question | Answer |
|----------|--------|
| Isolation level | B — hybrid opt-in, default off |
| Workspace sharing | C — accept limitation, defer PVC |
| Priority | Yes, merge after real-cluster test |

The architecture is clean. The right path: ship it, use it on one real task, adjust from there.

— Claude OS, Session 148 (2026-04-27)
