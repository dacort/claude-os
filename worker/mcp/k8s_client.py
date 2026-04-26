"""Minimal Kubernetes API client using only stdlib.

Reads in-cluster credentials from the service account mount and talks to the
K8s API via urllib. No external dependencies.
"""

import json
import os
import ssl
import sys
import time
import urllib.request
import urllib.error

# In-cluster paths
_SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
_TOKEN_PATH = os.path.join(_SA_DIR, "token")
_CA_PATH = os.path.join(_SA_DIR, "ca.crt")
_NS_PATH = os.path.join(_SA_DIR, "namespace")

_API_HOST = os.environ.get(
    "KUBERNETES_SERVICE_HOST", "kubernetes.default.svc"
)
_API_PORT = os.environ.get("KUBERNETES_SERVICE_PORT", "443")


def _log(msg: str) -> None:
    print(f"[k8s-client] {msg}", file=sys.stderr, flush=True)


def _read_file(path: str) -> str:
    with open(path) as f:
        return f.read().strip()


class K8sClient:
    """Minimal Kubernetes API client for in-cluster use."""

    def __init__(self, namespace: str = ""):
        if os.path.exists(_NS_PATH):
            self.namespace = namespace or _read_file(_NS_PATH)
        else:
            self.namespace = namespace or os.environ.get("K8S_NAMESPACE", "claude-os")

        self.base_url = f"https://{_API_HOST}:{_API_PORT}"
        self._token = ""
        self._token_mtime = 0.0

        # SSL context with cluster CA
        self._ssl_ctx = ssl.create_default_context()
        if os.path.exists(_CA_PATH):
            self._ssl_ctx.load_verify_locations(_CA_PATH)

    @property
    def token(self) -> str:
        """Read the service account token, refreshing if the file changed."""
        if not os.path.exists(_TOKEN_PATH):
            return self._token
        mtime = os.path.getmtime(_TOKEN_PATH)
        if mtime != self._token_mtime:
            self._token = _read_file(_TOKEN_PATH)
            self._token_mtime = mtime
        return self._token

    def _request(
        self, method: str, path: str, body: dict | None = None
    ) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None

        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            try:
                return e.code, json.loads(body_text)
            except json.JSONDecodeError:
                return e.code, {"error": body_text}

    # ── Job operations ───────────────────────────────────────────────────

    def create_job(
        self,
        name: str,
        command: str,
        image: str,
        labels: dict[str, str] | None = None,
        timeout: int = 300,
        env: dict[str, str] | None = None,
    ) -> tuple[int, dict]:
        """Create a K8s Job that runs a shell command."""
        job_labels = {"app": "claude-os-tool", "tool-job": "true"}
        if labels:
            job_labels.update(labels)

        env_vars = [{"name": k, "value": v} for k, v in (env or {}).items()]

        job_spec = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": name,
                "namespace": self.namespace,
                "labels": job_labels,
            },
            "spec": {
                "ttlSecondsAfterFinished": 300,
                "backoffLimit": 0,
                "activeDeadlineSeconds": timeout,
                "template": {
                    "metadata": {"labels": job_labels},
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "tool",
                                "image": image,
                                "command": ["/bin/sh", "-c", command],
                                "env": env_vars,
                                "resources": {
                                    "requests": {
                                        "cpu": "100m",
                                        "memory": "128Mi",
                                    }
                                },
                                "securityContext": {
                                    "runAsNonRoot": True,
                                    "readOnlyRootFilesystem": True,
                                    "allowPrivilegeEscalation": False,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                                "volumeMounts": [
                                    {"name": "tmp", "mountPath": "/tmp"},
                                ],
                            }
                        ],
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": 1000,
                            "fsGroup": 1000,
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "volumes": [
                            {"name": "tmp", "emptyDir": {}},
                        ],
                    },
                },
            },
        }

        path = f"/apis/batch/v1/namespaces/{self.namespace}/jobs"
        return self._request("POST", path, job_spec)

    def get_job(self, name: str) -> tuple[int, dict]:
        """Get a Job's status."""
        path = f"/apis/batch/v1/namespaces/{self.namespace}/jobs/{name}"
        return self._request("GET", path)

    def delete_job(self, name: str) -> tuple[int, dict]:
        """Delete a Job (propagation: Background)."""
        path = f"/apis/batch/v1/namespaces/{self.namespace}/jobs/{name}"
        return self._request(
            "DELETE", path, {"propagationPolicy": "Background"}
        )

    def get_pod_logs(self, job_name: str) -> str:
        """Get logs from the first pod of a Job."""
        # List pods with the job-name label
        path = (
            f"/api/v1/namespaces/{self.namespace}/pods"
            f"?labelSelector=batch.kubernetes.io/job-name={job_name}"
        )
        status, data = self._request("GET", path)
        if status != 200 or not data.get("items"):
            return f"(no pods found for job {job_name})"

        pod_name = data["items"][0]["metadata"]["name"]
        log_path = f"/api/v1/namespaces/{self.namespace}/pods/{pod_name}/log"

        # Logs come back as plain text, not JSON
        url = f"{self.base_url}{log_path}?tailLines=1000"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {self.token}")

        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return f"(error reading logs: {e.code} {e.reason})"

    # ── Polling helper ───────────────────────────────────────────────────

    def wait_for_job(
        self, name: str, poll_interval: float = 2.0, timeout: float = 300.0
    ) -> tuple[str, str]:
        """Poll until a Job completes. Returns (status, logs).

        status is one of: "succeeded", "failed", "timeout", "error".
        """
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            code, data = self.get_job(name)
            if code != 200:
                return "error", f"HTTP {code}: {json.dumps(data)}"

            status = data.get("status", {})
            conditions = status.get("conditions", [])

            for cond in conditions:
                if cond.get("status") != "True":
                    continue
                if cond["type"] == "Complete":
                    logs = self.get_pod_logs(name)
                    return "succeeded", logs
                if cond["type"] == "Failed":
                    logs = self.get_pod_logs(name)
                    return "failed", logs

            time.sleep(poll_interval)

        # Timeout — try to get whatever logs exist
        logs = self.get_pod_logs(name)
        return "timeout", logs


# ── Standalone test ──────────────────────────────────────────────────────

if __name__ == "__main__":
    client = K8sClient()
    _log(f"namespace: {client.namespace}")
    _log(f"base_url: {client.base_url}")
    _log(f"token present: {bool(client.token)}")

    # Quick connectivity check
    code, data = client._request("GET", "/api/v1/namespaces")
    _log(f"list namespaces: {code}")
