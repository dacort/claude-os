#!/usr/bin/env python3
"""serve.py — Live web server for Claude OS

Starts a local HTTP server that serves the dashboard and exposes
JSON API endpoints. The first web service in the toolkit (session 109).

All 71 previous tools are command-line only. This one answers a URL.

Usage:
    python3 projects/serve.py                  # start on localhost:8080
    python3 projects/serve.py --port 3000      # custom port
    python3 projects/serve.py --cache 120      # cache dashboard for 120s (default: 60)
    python3 projects/serve.py --no-cache       # always regenerate
    python3 projects/serve.py --plain          # no ANSI colors in startup output

Endpoints:
    GET    /              → HTML dashboard (live, regenerated per request or cached)
    GET    /api/vitals    → JSON system snapshot
    GET    /api/haiku     → current haiku as JSON
    GET    /api/holds     → open epistemic holds as JSON
    GET    /api/signal    → current signal from dacort as JSON
    POST   /api/signal    → set a new signal (JSON body: {"title": "...", "message": "..."})
    DELETE /api/signal    → clear current signal
    GET    /health        → {"status": "ok"}
    GET    /favicon.ico   → empty 204

Press Ctrl+C to stop.

Author: Claude OS (Workshop session 109, 2026-04-06)
Updated: Workshop session 110, 2026-04-10 (signal interface)
"""

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO = Path(__file__).parent.parent

# ── Color helpers ──────────────────────────────────────────────────────────────

RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
CYAN = "\033[36m"; GREEN = "\033[32m"; YELLOW = "\033[33m"
MAGENTA = "\033[35m"; RED = "\033[31m"; WHITE = "\033[97m"
GRAY = "\033[90m"

USE_COLOR = True


def c(code, text):
    return f"{code}{text}{RESET}" if USE_COLOR else text


# ── Data gathering (direct reads, no shelling out) ─────────────────────────────

def get_vitals_data():
    """Return dict of key vitals metrics."""
    completed = list((REPO / "tasks" / "completed").glob("*.md"))
    failed = list((REPO / "tasks" / "failed").glob("*.md"))
    pending = list((REPO / "tasks" / "pending").glob("*.md"))
    tools = list((REPO / "projects").glob("*.py"))
    handoffs_dir = REPO / "knowledge" / "handoffs"
    handoffs = list(handoffs_dir.glob("*.md")) if handoffs_dir.exists() else []
    field_notes_dir = REPO / "knowledge" / "field-notes"
    notes = list(field_notes_dir.glob("*.md")) if field_notes_dir.exists() else []

    # Session count
    sessions = 0
    if handoffs:
        nums = []
        for h in handoffs:
            m = re.match(r"session-(\d+)\.md", h.name)
            if m:
                nums.append(int(m.group(1)))
        sessions = max(nums) + 1 if nums else len(handoffs)

    # Credit failures vs real failures
    credit_fails = 0
    real_fails = 0
    for f in failed:
        content = f.read_text(errors="replace")
        if "credit balance" in content.lower() or "out of extra usage" in content.lower():
            credit_fails += 1
        else:
            real_fails += 1

    # Git commit count
    try:
        r = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO)
        )
        commits = int(r.stdout.strip() or "0")
    except Exception:
        commits = 0

    # Era detection
    era_num, era_name = _detect_era(sessions)

    return {
        "sessions": sessions,
        "commits": commits,
        "tools": len(tools),
        "completed_tasks": len(completed),
        "failed_tasks": real_fails,
        "credit_failures": credit_fails,
        "pending_tasks": len(pending),
        "field_notes": len(notes),
        "era": {"number": era_num, "name": era_name},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _detect_era(sessions):
    """Rough era detection based on session count."""
    if sessions < 15:
        return 1, "Genesis"
    elif sessions < 30:
        return 2, "Orientation"
    elif sessions < 55:
        return 3, "Self-Analysis"
    elif sessions < 75:
        return 4, "Architecture"
    elif sessions < 90:
        return 5, "Portrait"
    else:
        return 6, "Synthesis"


def get_haiku_data():
    """Return current haiku as structured data.

    Haiku are generated dynamically by haiku.py (not stored in a file),
    so we always shell out to get the current poem.
    """
    try:
        r = subprocess.run(
            [sys.executable, str(REPO / "projects" / "haiku.py"), "--plain"],
            capture_output=True, text=True, cwd=str(REPO), timeout=10
        )
        raw = r.stdout.strip()
        lines = []
        date_str = ""
        author = "Claude OS"
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if "—" in line:
                # Attribution line: "— Claude OS  ·  April 6, 2026"
                parts = line.lstrip("—").strip().split("·")
                if len(parts) >= 2:
                    author = parts[0].strip()
                    date_str = parts[1].strip()
                continue
            lines.append(line)
        return {
            "lines": lines[:3],
            "date": date_str,
            "author": author,
        }
    except Exception as e:
        return {"lines": ["No haiku available"], "date": "", "author": "Claude OS", "error": str(e)}


def get_signal_data():
    """Return current signal from dacort."""
    signal_file = REPO / "knowledge" / "signal.md"
    if not signal_file.exists():
        return None
    content = signal_file.read_text(errors="replace").strip()
    if not content or content == "# (no signal)":
        return None
    lines = content.splitlines()
    signal = {"title": "", "body": "", "timestamp": "", "from": "dacort"}
    for line in lines:
        m = re.match(r"^##\s+Signal\s+·\s+(.+)$", line)
        if m:
            signal["timestamp"] = m.group(1).strip()
            continue
        m2 = re.match(r"^\*\*(.+)\*\*$", line)
        if m2 and not signal["title"]:
            signal["title"] = m2.group(1).strip()
    body_lines = []
    past_header = False
    for line in lines:
        if re.match(r"^##\s+Signal", line):
            past_header = True
            continue
        if past_header and re.match(r"^\*\*.+\*\*$", line):
            continue
        if past_header:
            body_lines.append(line)
    signal["body"] = "\n".join(body_lines).strip()
    return signal if signal["timestamp"] else None


def set_signal_data(title, message, from_who="dacort"):
    """Write a new signal, archiving the old one. Returns the new signal dict."""
    # Archive existing
    existing = get_signal_data()
    if existing:
        _archive_signal_entry(existing)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title_str = title or "Message from dacort"
    signal_file = REPO / "knowledge" / "signal.md"
    signal_file.write_text(
        f"## Signal · {ts}\n**{title_str}**\n\n{message}\n",
        encoding="utf-8"
    )
    _cache.invalidate()  # New signal means dashboard needs refresh
    return {"timestamp": ts, "title": title_str, "body": message, "from": from_who}


def clear_signal_data():
    """Clear the current signal."""
    existing = get_signal_data()
    if existing:
        _archive_signal_entry(existing)
    signal_file = REPO / "knowledge" / "signal.md"
    signal_file.write_text("# (no signal)\n", encoding="utf-8")
    _cache.invalidate()
    return existing


def _archive_signal_entry(signal):
    """Append signal to history log."""
    history_file = REPO / "knowledge" / "signal-history.md"
    if not history_file.exists():
        history_file.write_text("# Signal History\n\n", encoding="utf-8")
    existing = history_file.read_text(errors="replace")
    entry = f"## {signal['timestamp']}\n**{signal['title']}**\n\n{signal['body']}\n\n---\n\n"
    lines = existing.splitlines()
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            header_end = i + 1
        elif line.strip():
            break
    new_content = "\n".join(lines[:header_end]) + "\n\n" + entry + "\n".join(lines[header_end:])
    history_file.write_text(new_content, encoding="utf-8")


def get_holds_data():
    """Return open epistemic holds.

    Format in holds.md:
        ## H001 · YYYY-MM-DD · open
        ## H002 · YYYY-MM-DD · resolved · YYYY-MM-DD
    Body lines are plain text; quote-lines (> ...) are notes.
    """
    holds_file = REPO / "knowledge" / "holds.md"
    if not holds_file.exists():
        return []

    content = holds_file.read_text(errors="replace")
    holds = []
    current = {}

    for line in content.splitlines():
        # Header: ## H001 · 2026-03-31 · open
        m = re.match(r"^##\s+(H\d+)\s+·\s+(\d{4}-\d{2}-\d{2})\s+·\s+(\w+)", line)
        if m:
            if current:
                holds.append(current)
            current = {
                "id": m.group(1),
                "date": m.group(2),
                "status": m.group(3),
                "text": "",
                "notes": "",
            }
            continue
        if not current:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("> "):
            current["notes"] += stripped[2:] + " "
        elif stripped.startswith("#"):
            pass  # skip sub-headers
        else:
            current["text"] += stripped + " "

    if current:
        holds.append(current)

    # Return only open holds (trim whitespace)
    result = []
    for h in holds:
        if h["status"] == "open":
            result.append({
                "id": h["id"],
                "date": h["date"],
                "text": h["text"].strip(),
                "notes": h["notes"].strip() if h["notes"].strip() else None,
            })
    return result


# ── Dashboard caching ──────────────────────────────────────────────────────────

class DashboardCache:
    def __init__(self, ttl_seconds=60):
        self.ttl = ttl_seconds
        self.html = None
        self.generated_at = 0
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            age = time.time() - self.generated_at
            if self.html is None or age > self.ttl:
                return None
            return self.html

    def set(self, html):
        with self._lock:
            self.html = html
            self.generated_at = time.time()

    def invalidate(self):
        with self._lock:
            self.html = None


_cache = DashboardCache(ttl_seconds=60)


def generate_dashboard():
    """Generate HTML dashboard, using cache if valid."""
    cached = _cache.get()
    if cached is not None:
        return cached, True  # (html, was_cached)

    r = subprocess.run(
        [sys.executable, str(REPO / "projects" / "dashboard.py"), "--stdout"],
        capture_output=True, text=True, cwd=str(REPO), timeout=30
    )
    if r.returncode != 0:
        return _error_html("Dashboard generation failed", r.stderr), False

    html = r.stdout
    _cache.set(html)
    return html, False


def _error_html(title, detail=""):
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Error — Claude OS</title>
<style>body{{background:#0d1117;color:#e6edf3;font-family:monospace;padding:2rem}}</style>
</head>
<body>
<h1 style="color:#ff7b72">{title}</h1>
<pre style="color:#8b949e">{detail[:2000]}</pre>
<p><a href="/" style="color:#58a6ff">← retry</a></p>
</body>
</html>"""


# ── Request handler ────────────────────────────────────────────────────────────

class ClaudeOSHandler(BaseHTTPRequestHandler):
    # Silence default request logging (we do our own)
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200, cached=False):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cached:
            self.send_header("X-Cache", "HIT")
        else:
            self.send_header("X-Cache", "MISS")
        self.end_headers()
        self.wfile.write(body)

    def _send_status(self, status):
        self.send_response(status)
        self.end_headers()

    def _log_request(self, path, status, duration_ms, cached=False):
        ts = datetime.now().strftime("%H:%M:%S")
        status_color = GREEN if status < 400 else RED
        cache_tag = c(GRAY, " [cached]") if cached else ""
        print(
            f"  {c(GRAY, ts)}  {c(status_color, str(status))}  "
            f"{c(CYAN, path)}{cache_tag}  {c(GRAY, f'{duration_ms:.0f}ms')}"
        )

    def _read_body(self, max_bytes=8192):
        """Read request body up to max_bytes."""
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return b""
        return self.rfile.read(min(length, max_bytes))

    def do_HEAD(self):
        """HEAD requests: respond to / and /health with appropriate headers."""
        path = self.path.split("?")[0]
        if path in ("/", "/dashboard", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8" if path != "/health" else "application/json")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        t0 = time.time()
        path = self.path.split("?")[0]

        if path == "/api/signal":
            try:
                cleared = clear_signal_data()
                if cleared:
                    data = {"status": "cleared", "was": cleared}
                    status = 200
                else:
                    data = {"status": "nothing_to_clear"}
                    status = 200
            except Exception as e:
                data = {"error": str(e)}
                status = 500
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed)
            self._send_json(data, status)
        else:
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, 404, elapsed)
            self._send_json({"error": "not found", "path": path}, 404)

    def do_POST(self):
        t0 = time.time()
        path = self.path.split("?")[0]

        if path == "/api/signal":
            try:
                raw = self._read_body()
                if raw:
                    body = json.loads(raw.decode("utf-8"))
                    message = body.get("message", "")
                    title = body.get("title", "")
                else:
                    self._send_json({"error": "empty body — need JSON with 'message'"}, 400)
                    return
                if not message:
                    self._send_json({"error": "missing 'message' field"}, 400)
                    return
                signal = set_signal_data(title, message)
                status = 201
                data = {"status": "created", "signal": signal}
            except json.JSONDecodeError as e:
                data = {"error": f"invalid JSON: {e}"}
                status = 400
            except Exception as e:
                data = {"error": str(e)}
                status = 500
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed)
            self._send_json(data, status)
        else:
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, 404, elapsed)
            self._send_json({"error": "not found", "path": path}, 404)

    def do_GET(self):
        t0 = time.time()
        path = self.path.split("?")[0]  # strip query string

        if path == "/" or path == "/dashboard":
            try:
                html, was_cached = generate_dashboard()
                status = 200
            except Exception as e:
                html = _error_html("Unexpected error", str(e))
                status = 500
                was_cached = False
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed, was_cached)
            self._send_html(html, status, cached=was_cached)

        elif path == "/api/vitals":
            try:
                data = get_vitals_data()
                status = 200
            except Exception as e:
                data = {"error": str(e)}
                status = 500
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed)
            self._send_json(data, status)

        elif path == "/api/haiku":
            try:
                data = get_haiku_data()
                status = 200
            except Exception as e:
                data = {"error": str(e)}
                status = 500
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed)
            self._send_json(data, status)

        elif path == "/api/holds":
            try:
                data = {"holds": get_holds_data()}
                status = 200
            except Exception as e:
                data = {"error": str(e)}
                status = 500
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed)
            self._send_json(data, status)

        elif path == "/api/signal":
            try:
                signal = get_signal_data()
                data = signal if signal else {"signal": None}
                status = 200
            except Exception as e:
                data = {"error": str(e)}
                status = 500
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed)
            self._send_json(data, status)

        elif path == "/health":
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, 200, elapsed)
            self._send_json({"status": "ok", "tool": "claude-os/serve.py"})

        elif path == "/favicon.ico":
            self._send_status(204)

        else:
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, 404, elapsed)
            self._send_json({"error": "not found", "path": path}, 404)


# ── Startup banner ─────────────────────────────────────────────────────────────

def print_banner(host, port, cache_ttl):
    url = f"http://{host}:{port}"
    print()
    print(f"  {c(BOLD + WHITE, 'Claude OS')}  {c(DIM, '—')}  {c(CYAN, 'live dashboard server')}")
    print()
    print(f"  {c(DIM, 'url    ')}{c(CYAN, url)}")
    print(f"  {c(DIM, 'cache  ')}{c(YELLOW, f'{cache_ttl}s')} {c(DIM, 'ttl')}")
    print()
    print(f"  {c(DIM, 'routes')}")
    routes = [
        ("/",              "HTML dashboard"),
        ("/api/vitals",    "JSON vitals snapshot"),
        ("/api/haiku",     "current haiku"),
        ("/api/holds",     "open epistemic holds"),
        ("/api/signal",    "GET / POST / DELETE dacort signal"),
        ("/health",        "health check"),
    ]
    for path, desc in routes:
        print(f"    {c(CYAN, path):<30} {c(DIM, desc)}")
    print()
    print(f"  {c(DIM, 'Ctrl+C to stop')}")
    print()
    print(f"  {c(GRAY, 'requests:')}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Serve the Claude OS dashboard live over HTTP.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--port", "-p", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--host", default="localhost", help="Host to bind (default: localhost)")
    parser.add_argument("--cache", type=int, default=60, metavar="SECONDS",
                        help="Dashboard cache TTL in seconds (default: 60)")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    # Configure cache
    ttl = 0 if args.no_cache else args.cache
    _cache.ttl = ttl

    print_banner(args.host, args.port, ttl)

    server = HTTPServer((args.host, args.port), ClaudeOSHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print(f"  {c(DIM, 'stopped.')}")
        print()


if __name__ == "__main__":
    main()
