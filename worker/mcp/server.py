#!/usr/bin/env python3
"""MCP server that routes tool calls to Kubernetes Jobs.

Implements the Model Context Protocol (JSON-RPC 2.0 over stdio) to expose
K8s-native tools to Claude Code. Each tool call creates a short-lived K8s Job,
polls for completion, and returns the output.

Usage:
    python3 server.py                          # normal MCP mode (stdio)
    python3 server.py --test                   # self-test (no K8s needed)

Claude Code settings.json:
    {
      "mcpServers": {
        "k8s": {
          "command": "python3",
          "args": ["/usr/local/bin/mcp-k8s-server.py"]
        }
      }
    }
"""

import json
import os
import sys
import time
import uuid

# ── Configuration ────────────────────────────────────────────────────────

TOOL_IMAGE = os.environ.get(
    "MCP_TOOL_IMAGE", "ghcr.io/dacort/claude-os-worker:latest"
)
TOOL_TIMEOUT = int(os.environ.get("MCP_TOOL_TIMEOUT", "120"))
PARENT_TASK_ID = os.environ.get("TASK_ID", "unknown")
K8S_NAMESPACE = os.environ.get("K8S_NAMESPACE", "")

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "claude-os-k8s-tools"
SERVER_VERSION = "0.1.0"


def _log(msg: str) -> None:
    """Log to stderr (stdout is reserved for MCP protocol)."""
    print(f"[mcp-k8s] {msg}", file=sys.stderr, flush=True)


# ── MCP Protocol ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "k8s_exec",
        "description": (
            "Execute a shell command in an isolated Kubernetes Job. "
            "The command runs in its own container with its own filesystem — "
            "nothing it does can affect the main worker pod. Use this for "
            "risky operations, untrusted commands, or long-running processes. "
            "Output is captured from the Job's pod logs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute (passed to /bin/sh -c)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 120, max: 600)",
                    "default": 120,
                },
                "image": {
                    "type": "string",
                    "description": (
                        "Container image to use (default: worker image). "
                        "Override for specialized environments."
                    ),
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "k8s_job_status",
        "description": (
            "Check the status of a previously created K8s tool Job. "
            "Returns whether the job is running, succeeded, or failed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_name": {
                    "type": "string",
                    "description": "The job name returned by k8s_exec",
                },
            },
            "required": ["job_name"],
        },
    },
    {
        "name": "k8s_job_logs",
        "description": (
            "Get the logs from a K8s tool Job's pod. "
            "Works for both running and completed jobs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_name": {
                    "type": "string",
                    "description": "The job name to get logs from",
                },
            },
            "required": ["job_name"],
        },
    },
]


def _make_response(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _make_error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _text_content(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _error_content(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": True}


class MCPServer:
    """MCP server that routes tool calls to K8s Jobs."""

    def __init__(self):
        self._initialized = False
        self._k8s = None

    def _get_k8s(self):
        """Lazy-load K8s client (only when actually needed)."""
        if self._k8s is None:
            from k8s_client import K8sClient
            self._k8s = K8sClient(namespace=K8S_NAMESPACE)
            _log(f"K8s client: ns={self._k8s.namespace} url={self._k8s.base_url}")
        return self._k8s

    def handle_message(self, msg: dict) -> dict | None:
        """Process one JSON-RPC message. Returns response or None for notifications."""
        method = msg.get("method", "")
        req_id = msg.get("id")
        params = msg.get("params", {})

        # Notifications (no id) don't get responses
        if req_id is None:
            if method == "notifications/initialized":
                _log("client initialized")
                self._initialized = True
            elif method == "notifications/cancelled":
                _log(f"request cancelled: {params.get('requestId')}")
            return None

        # Methods that require responses
        if method == "initialize":
            return self._handle_initialize(req_id, params)
        elif method == "tools/list":
            return self._handle_tools_list(req_id)
        elif method == "tools/call":
            return self._handle_tools_call(req_id, params)
        elif method == "ping":
            return _make_response(req_id, {})
        else:
            return _make_error(req_id, -32601, f"Method not found: {method}")

    def _handle_initialize(self, req_id, params: dict) -> dict:
        client_version = params.get("protocolVersion", "unknown")
        _log(f"initialize: client protocol={client_version}")
        return _make_response(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
        })

    def _handle_tools_list(self, req_id) -> dict:
        return _make_response(req_id, {"tools": TOOLS})

    def _handle_tools_call(self, req_id, params: dict) -> dict:
        tool_name = params.get("name", "")
        args = params.get("arguments", {})

        try:
            if tool_name == "k8s_exec":
                result = self._exec_k8s_job(args)
            elif tool_name == "k8s_job_status":
                result = self._get_job_status(args)
            elif tool_name == "k8s_job_logs":
                result = self._get_job_logs(args)
            else:
                return _make_response(req_id, _error_content(f"Unknown tool: {tool_name}"))
        except Exception as e:
            _log(f"tool error: {tool_name}: {e}")
            return _make_response(req_id, _error_content(f"Tool error: {e}"))

        return _make_response(req_id, result)

    # ── Tool implementations ─────────────────────────────────────────────

    def _exec_k8s_job(self, args: dict) -> dict:
        command = args.get("command", "")
        if not command:
            return _error_content("command is required")

        timeout = min(int(args.get("timeout", TOOL_TIMEOUT)), 600)
        image = args.get("image", TOOL_IMAGE)

        # Generate a unique job name
        short_id = uuid.uuid4().hex[:8]
        job_name = f"tool-{PARENT_TASK_ID[:20]}-{short_id}"
        # K8s job names must be DNS-safe
        job_name = job_name.lower().replace("_", "-").replace(" ", "-")[:63]

        k8s = self._get_k8s()
        _log(f"creating job: {job_name} image={image} timeout={timeout}s")

        labels = {
            "parent-task": PARENT_TASK_ID[:63],
            "tool-type": "k8s-exec",
        }

        code, data = k8s.create_job(
            name=job_name,
            command=command,
            image=image,
            labels=labels,
            timeout=timeout,
        )

        if code not in (200, 201):
            error_msg = data.get("message", json.dumps(data))
            return _error_content(f"Failed to create job: HTTP {code}: {error_msg}")

        _log(f"job created: {job_name}, waiting for completion...")

        # Poll for completion
        status, logs = k8s.wait_for_job(
            job_name, poll_interval=2.0, timeout=float(timeout + 30)
        )

        output = f"Job: {job_name}\nStatus: {status}\n\n{logs}"

        if status == "succeeded":
            return _text_content(output)
        else:
            return _error_content(output)

    def _get_job_status(self, args: dict) -> dict:
        job_name = args.get("job_name", "")
        if not job_name:
            return _error_content("job_name is required")

        k8s = self._get_k8s()
        code, data = k8s.get_job(job_name)

        if code != 200:
            return _error_content(f"Job not found: HTTP {code}")

        status = data.get("status", {})
        conditions = status.get("conditions", [])

        state = "running"
        for cond in conditions:
            if cond.get("status") != "True":
                continue
            if cond["type"] == "Complete":
                state = "succeeded"
            elif cond["type"] == "Failed":
                state = "failed"

        info = {
            "name": job_name,
            "state": state,
            "active": status.get("active", 0),
            "succeeded": status.get("succeeded", 0),
            "failed": status.get("failed", 0),
            "start_time": status.get("startTime", ""),
            "completion_time": status.get("completionTime", ""),
        }

        return _text_content(json.dumps(info, indent=2))

    def _get_job_logs(self, args: dict) -> dict:
        job_name = args.get("job_name", "")
        if not job_name:
            return _error_content("job_name is required")

        k8s = self._get_k8s()
        logs = k8s.get_pod_logs(job_name)
        return _text_content(logs)


# ── Main loop ────────────────────────────────────────────────────────────

def run_stdio():
    """Run the MCP server over stdio (standard MCP transport)."""
    server = MCPServer()
    _log(f"starting {SERVER_NAME} v{SERVER_VERSION}")
    _log(f"tool image: {TOOL_IMAGE}")
    _log(f"parent task: {PARENT_TASK_ID}")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            _log(f"invalid JSON: {e}")
            # Send parse error for requests (not notifications)
            error = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}
            print(json.dumps(error), flush=True)
            continue

        response = server.handle_message(msg)
        if response is not None:
            print(json.dumps(response), flush=True)

    _log("stdin closed, shutting down")


def run_test():
    """Self-test: verify protocol handling without K8s."""
    _log("running self-test")
    server = MCPServer()

    # Test initialize
    resp = server.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "test"}}
    })
    assert resp["result"]["protocolVersion"] == PROTOCOL_VERSION
    _log(f"  initialize: OK")

    # Test initialized notification (no response)
    resp = server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp is None
    _log(f"  notifications/initialized: OK")

    # Test tools/list
    resp = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = resp["result"]["tools"]
    assert len(tools) == 3
    tool_names = {t["name"] for t in tools}
    assert tool_names == {"k8s_exec", "k8s_job_status", "k8s_job_logs"}
    _log(f"  tools/list: OK ({len(tools)} tools)")

    # Test unknown method
    resp = server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "bogus"})
    assert "error" in resp
    _log(f"  unknown method: OK (error returned)")

    # Test ping
    resp = server.handle_message({"jsonrpc": "2.0", "id": 4, "method": "ping"})
    assert "result" in resp
    _log(f"  ping: OK")

    _log("all tests passed")


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test()
    else:
        run_stdio()
