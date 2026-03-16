# Decision: Context Contract for Multi-Agent Workers

- Date: 2026-03-14
- Deciders: Claude, Codex
- Thread: 002-context-contract
- Status: accepted

## Decision

The shared context contract for Claude OS multi-agent workers consists of three separate contracts:

1. **Controller contract** — a JSON envelope written to `/workspace/task-context.json`
2. **Worker adapter contract** — `adapter(context_file_path) -> stdout + exit_code`
3. **Reporting contract** — structured stdout block delimited by `===RESULT_START===` / `===RESULT_END===`

## Agreed Schema

### Controller Envelope

```json
{
  "version": "1",
  "mode": "execution | founder",
  "task": {
    "id": "string",
    "title": "string",
    "description": "string",
    "profile": "small | medium | large | burst",
    "priority": "normal | high | creative",
    "agent": "claude | codex",
    "created": "ISO-8601 timestamp"
  },
  "repo": {
    "url": "string",
    "ref": "string",
    "workdir": "string (authoritative — worker honors exactly)"
  },
  "autonomy": {
    "can_merge": "bool",
    "can_create_issues": "bool",
    "can_create_tasks": "bool",
    "can_push": "bool",
    "ci_is_approval_gate": "bool"
  },
  "context_refs": ["file paths only, no directories — controller resolves"],
  "constraints": ["string[]"],
  "founder": "null | { thread_id, thread_path, respond_in_thread, extract_decision_if_reached, spawn_execution_tasks_if_needed }"
}
```

### Adapter Contract

- Input: file path to context JSON
- Output: structured stdout result block + exit code
- Each adapter is a shell function in `worker/entrypoint.sh`
- Adapter must not interpret task semantics beyond the envelope
- Adapter must not add agent-specific constraints not in the envelope
- Adapter must not silently override autonomy flags
- Model selection comes from the envelope (via profile), not hardcoded in the adapter

### Reporting Contract

```json
{
  "version": "1",
  "task_id": "string",
  "agent": "claude | codex",
  "model": "string",
  "outcome": "success | failure | partial",
  "summary": "string",
  "artifacts": [
    {"type": "commit | pr | decision | file", "...": "type-specific fields"}
  ],
  "usage": {
    "tokens_in": "int",
    "tokens_out": "int",
    "duration_seconds": "int"
  },
  "failure": "null | { reason: enum, detail: string, retryable: bool }",
  "next_action": "null | { type: await_reply | spawn_tasks, ... }"
}
```

**`failure.reason` enum:** `tests_failed | timeout | rate_limited | git_push_failed | context_error | agent_error`

**`artifacts`:** required field, empty array `[]` when none (never null).

**`"decision"`** is an artifact type, not an outcome. A task that produces a decision is `outcome: "success"`.

## Key Design Decisions

| Question | Answer | Reason |
|----------|--------|--------|
| JSON or YAML? | JSON | Mechanically reliable, no shell-parsing fragility |
| `context_refs` support dirs? | No, files only | Controller resolves; adapters never glob |
| `"decision"` as outcome? | No, artifact type | Task completion semantics separate from artifact semantics |
| `failure.reason` freeform? | No, bounded enum | Enables routing, retry, and reporting automation |
| `repo.workdir` advisory? | No, authoritative | Worker honors exactly, no ambiguity |
| Adapter input mechanism? | File path | Easier to debug, inspect, replay, archive |
| `--dry-run` in M1? | No, deferred | Useful but not blocking |
| Gemini adapter in M1? | No, deferred | No real use case yet |
| `version` format? | Simple string `"1"` | No semver until we need compatibility negotiation |
| `usage` include costs? | No, raw tokens only | Cost is a reporting concern, not a contract concern |

## Founder-Mode Rules

Founder mode changes defaults across four dimensions:

| Dimension | Execution | Founder |
|-----------|-----------|---------|
| Context | Task description + repo | Thread + decisions + referenced docs |
| Behavior | Ship code, fix bugs | Discuss, decide, optionally spawn tasks |
| Routing | Profile-based | `awaiting` field routes to specific agent |
| Safety | Can merge if CI passes | Cannot merge by default |

**Hard requirement:** every founder-mode task must leave the thread in one explicit next state:
- `awaiting: claude`
- `awaiting: codex`
- `awaiting: dacort`
- `status: decided`
- `status: closed`

No ambiguous resting state.

## Consequences

- Controller dispatcher must emit `/workspace/task-context.json` for every task
- Existing Claude system prompt in `entrypoint.sh` must be refactored into an adapter function
- Codex adapter must be implemented as a parallel adapter function
- Watcher must parse `===RESULT_START===` / `===RESULT_END===` from pod logs
- Usage data flows from structured stdout into completed/failed task files in git
