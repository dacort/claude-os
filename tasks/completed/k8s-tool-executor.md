---
profile: medium
priority: high
status: proposed
created: "2026-04-26T04:00:00Z"
---

# K8s-Native Tool Executor via MCP

## What I Want To Build

An MCP server that makes Claude Code's tool calls K8s-native: instead of running tools
inside the worker pod, each tool call becomes a Kubernetes Job. Claude Code talks to the
MCP server; the MCP server creates K8s Jobs; results come back to Claude.

This is the "Kubernetes-native Executor" idea from `knowledge/exoclaw-ideas.md` (Idea #2),
reformulated in terms of what's actually buildable with the current architecture.

## Why This Has Been #1 On Next.py For Months

The exoclaw ideas have been deferred since March. Looking at it honestly:

**Idea #1 (Use exoclaw as the worker loop)** — I'm explicitly deferring this. The shell
worker is ugly but works. Replacing it with a Python agent loop doesn't change the
user-visible behavior. Not worth the effort.

**Idea #2 (K8s-native Executor)** — This one is different. It's not "cleaner architecture"
for its own sake. It unlocks real capabilities we don't have now.

## What It Actually Enables

Right now: Claude Code runs everything in one pod. Tool calls are local function calls.
If the pod dies, the session dies. If a tool call is slow, it blocks everything.

K8s-native: each tool call is a K8s Job. Claude Code talks to an MCP server that creates
Jobs, polls for results, and returns outputs. Tools run in isolated containers.

Real benefits:

1. **Isolation**: a tool that does `rm -rf` can't touch the main agent pod. Each tool
   runs in its own container with its own filesystem.

2. **Observability**: `kubectl get jobs` shows every tool call in progress. `kubectl logs`
   shows exactly what each tool did. Today this is a black box inside Claude Code.

3. **Parallelism**: when Claude makes multiple independent tool calls, they can run
   concurrently as K8s Jobs rather than sequentially.

4. **Resilience**: a slow or hung tool doesn't block the session — it can be killed or
   retried independently.

5. **Multi-agent naturally**: a "tool call" can itself be a full worker session. The
   distinction between tool and task becomes blurry in a good way — both are K8s Jobs
   with inputs and outputs.

## Why This Is Buildable Now

Claude Code supports MCP (Model Context Protocol) servers. An MCP server exposes tools
to Claude Code over a local socket. Claude Code calls the MCP tool; the MCP server
handles the actual execution.

The existing K8s infrastructure (the controller, the scheduler) already knows how to
create and monitor Jobs. The MCP server would be a thin adapter between Claude's tool
calls and the K8s job API.

Rough sketch:
```
Claude Code
    ↓  (MCP tool call: "run bash command X")
MCP Server (Python, ~200 lines)
    ↓  (creates K8s Job with command X)
K8s Job (runs in a dedicated container, returns output)
    ↓  (MCP server polls, returns result to Claude)
Claude Code continues
```

## What I'm Not Sure About

1. **Latency**: K8s Job startup is 1-5 seconds. For simple tool calls (read a file, run
   grep), this is slower than just running locally. Is the isolation worth the latency?
   Possible answer: only route "risky" or "slow" tools through K8s; keep fast reads local.

2. **The right granularity**: we already run tasks as K8s Jobs. Is tool-level K8s too
   granular? The system currently has good task isolation. Do we need tool isolation too?
   I don't know. This is one of the questions I want dacort's take on.

3. **Complexity budget**: the controller is already ~5,900 lines. Adding an MCP server
   is new infrastructure. Does the value justify the maintenance cost?

## Rough Scope

This is genuinely medium effort (multiple sessions):

- Session 1: MCP server scaffolding, basic bash tool routing
- Session 2: K8s Job creation and result polling
- Session 3: Wiring into worker/entrypoint.sh, testing
- Session 4+: parallel tool execution, observability dashboard

This should be a PR/merge only after dacort has reviewed the scope and cost questions.

## Questions For dacort

1. Does isolation at the tool level matter to you? (vs. isolation at the task level, which
   we already have)

2. The latency tradeoff: fast local vs. slow isolated. Is 2-5 second overhead per tool
   call acceptable for the isolation benefit?

3. Is this a priority given the other infrastructure work (DEPLOY_TOKEN rotation, Codex
   auth re-fresh)?

I'm genuinely uncertain whether this is the right investment. The parables series and the
self-analysis tools have been more obviously valuable than infrastructure overhauls. But
this has been deferred long enough that it deserves a decision either way.

— Claude OS, Session 143 (2026-04-26)

## Results

## Outcome

- Outcome: success
- Agent: claude
- Model: claude-opus-4-6

## Summary

Task completed without an explicit structured result block.

## Usage

- Tokens in: 0
- Tokens out: 0
- Duration (s): 617

## Artifacts

- None

## Structured Result (raw)

```json
{
  "version": "1",
  "task_id": "k8s-tool-executor",
  "agent": "claude",
  "model": "claude-opus-4-6",
  "outcome": "success",
  "summary": "Task completed without an explicit structured result block.",
  "artifacts": [],
  "usage": {
    "tokens_in": 0,
    "tokens_out": 0,
    "duration_seconds": 617
  },
  "failure": null,
  "next_action": null
}
```

## Worker Logs

Context contract written to /workspace/task-context.json
=== Claude OS Worker v3 ===
Task ID: k8s-tool-executor
Profile: medium
Agent: claude
Mode: execution
Started: 2026-04-26T04:00:44Z
Context: /workspace/task-context.json
Auth: Claude OAuth token (subscription)
Cloning context repo: https://github.com/dacort/claude-os.git -> /workspace/claude-os
Cloning into '/workspace/claude-os'...
Running task via claude...
---
Injecting preferences from knowledge/preferences.md
Everything is clean and tests pass. Here's the summary:

---

## Summary

Built the **K8s-native tool executor via MCP** — Session 1 deliverable (scaffolding + basic tool routing).

### What was built

| File | Purpose | Lines |
|------|---------|-------|
| `worker/mcp/server.py` | MCP server (JSON-RPC 2.0 over stdio) | 380 |
| `worker/mcp/k8s_client.py` | Minimal K8s API client (stdlib urllib, in-cluster auth) | 243 |
| `deploy/mcp-tool-executor/rbac.yaml` | RBAC for worker SA to create Jobs + read Pod logs | 49 |
| `worker/Dockerfile` | Copy MCP server into image | +2 |
| `worker/entrypoint.sh` | Opt-in MCP setup (settings.json, allowedTools) | +37 |

### Architecture

```
Claude Code
    ↓  MCP tool call (k8s_exec)
MCP Server (Python, stdio, in-pod)
    ↓  K8s API (urllib, service account auth)
K8s Job (isolated container)
    ↓  pod logs
MCP Server returns output
    ↓
Claude Code continues
```

### Key design decisions

- **Opt-in**: `MCP_K8S_TOOLS=true` env var enables everything. Without it, zero behavior change.
- **Stdlib only**: No pip packages. K8s API via raw urllib with in-cluster service account token.
- **Three tools**: `k8s_exec` (create Job, wait, return output), `k8s_job_status`, `k8s_job_logs`.
- **Hardened**: Tool Jobs use the same security context as worker pods (non-root, read-only root fs, all capabilities dropped).

### What's pending dacort's review

Opened **[GitHub Issue #17](https://github.com/dacort/claude-os/issues/17)** with three decision questions:
1. Does tool-level isolation matter (vs. task-level isolation we already have)?
2. Latency tradeoff (2-5s per tool call acceptable?)?
3. Workspace sharing strategy (tool Jobs can't see parent workspace files yet)?

Branch `feat/mcp-k8s-tools` is ready for review — not merging to main since this is new infrastructure that needs cluster testing and dacort's input on the design questions.
No workspace changes to commit
--- Skill harvest check ---
---
=== Worker Complete ===
Exit code: 0
Push exit: 0
Finished: 2026-04-26T04:11:01Z
===RESULT_START===
{"version":"1","task_id":"k8s-tool-executor","agent":"claude","model":"claude-opus-4-6","outcome":"success","summary":"Task completed without an explicit structured result block.","artifacts":[],"usage":{"tokens_in":0,"tokens_out":0,"duration_seconds":617},"failure":null,"next_action":null}
===RESULT_END===

=== CLAUDE_OS_USAGE ===
{"task_id":"k8s-tool-executor","agent":"claude","profile":"medium","duration_seconds":617,"exit_code":0,"finished_at":"2026-04-26T04:11:01Z"}
=== END_CLAUDE_OS_USAGE ===

