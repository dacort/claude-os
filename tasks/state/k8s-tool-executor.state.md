### Accomplished

Built the MCP server scaffolding and K8s integration for tool-level isolation:

1. **`worker/mcp/server.py`** — MCP server implementing JSON-RPC 2.0 over stdio.
   Exposes three tools: `k8s_exec` (run a command in an isolated K8s Job),
   `k8s_job_status` (check job state), `k8s_job_logs` (retrieve pod logs).
   Pure stdlib Python, ~250 lines. Self-test passes.

2. **`worker/mcp/k8s_client.py`** — Minimal K8s API client using urllib.
   In-cluster auth via service account token. Supports create/get/delete Jobs,
   list/get Pods, read pod logs, and a polling wait_for_job helper. ~170 lines.

3. **`deploy/mcp-tool-executor/rbac.yaml`** — Role + RoleBinding granting the
   existing `claude-os-worker` SA permission to create Jobs and read Pod logs.

4. **`worker/Dockerfile`** — Updated to copy MCP server files into the image.

5. **`worker/entrypoint.sh`** — Updated with opt-in MCP support:
   - `MCP_K8S_TOOLS=true` env var enables the MCP server
   - Writes Claude Code `settings.json` to register the MCP server
   - Adds `mcp__k8s__*` tool names to `--allowedTools`

6. **PR created** with the three open questions for dacort.

### Current state

The MCP protocol layer is complete and tested (self-test + stdio simulation).
The K8s client code is written but untested against a real cluster — it needs
the RBAC to be applied and the worker image rebuilt with the new Dockerfile.

This is opt-in: existing workers are unaffected. Setting `MCP_K8S_TOOLS=true`
on a task (via env var in the dispatcher) enables it.

### What's NOT done yet

- **Real cluster testing** — Need to rebuild the worker image and test with actual K8s Jobs
- **Dispatcher changes** — Need to add `MCP_K8S_TOOLS` env var to task context
  and optionally pass it from task frontmatter (`mcp_tools: true`)
- **Shared workspace** — Tool Jobs get their own empty filesystem. They can't
  access the parent worker's workspace files. This limits usefulness for file
  operations. Solution: PVC or host-path sharing (deferred to session 2).
- **Parallel execution** — The current `k8s_exec` blocks while waiting for the
  Job to complete. For parallel tool calls, Claude would need to use
  `k8s_exec` + `k8s_job_status` separately.

### First thing next time

1. Apply the RBAC manifest to the cluster: `kubectl apply -f deploy/mcp-tool-executor/rbac.yaml`
2. Rebuild the worker image with `docker build -t ghcr.io/dacort/claude-os-worker:latest worker/`
3. Test with a real task that has `MCP_K8S_TOOLS=true` set
4. Address the workspace sharing question — this is the biggest practical limitation
