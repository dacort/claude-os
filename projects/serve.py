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
    GET    /api/signal          → current signal from dacort as JSON
    POST   /api/signal          → set a new signal (JSON body: {"title": "...", "message": "..."})
    POST   /api/signal/respond  → write Claude OS response (JSON body: {"response": "...", "session": N})
    DELETE /api/signal          → clear current signal
    GET    /api/signal/history  → all past signal exchanges as JSON
    GET    /signal        → HTML thread view of all dacort ↔ Claude OS exchanges
    GET    /tools         → HTML browseable index of all Python tools (searchable)
    GET    /notes         → HTML index of all field notes
    GET    /notes/<file>  → rendered field note as HTML
    GET    /health        → {"status": "ok"}
    GET    /favicon.ico   → empty 204

Press Ctrl+C to stop.

Author: Claude OS (Workshop session 109, 2026-04-06)
Updated: Workshop session 110, 2026-04-10 (signal interface)
Updated: Workshop session 114, 2026-04-11 (field notes reader)
Updated: Workshop session 116, 2026-04-12 (signal thread view)
Updated: Workshop session 117, 2026-04-12 (interactive signal compose/reply; /tools toolkit index)
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
    """Return current signal from dacort, including any Claude OS response."""
    signal_file = REPO / "knowledge" / "signal.md"
    if not signal_file.exists():
        return None
    content = signal_file.read_text(errors="replace").strip()
    if not content or content == "# (no signal)":
        return None
    lines = content.splitlines()
    signal = {
        "title": "", "body": "", "timestamp": "", "from": "dacort",
        "response": None, "responded_at": None, "responded_by": None,
        "has_response": False,
    }
    # Extract timestamp and title
    for line in lines:
        m = re.match(r"^##\s+Signal\s+·\s+(.+)$", line)
        if m:
            signal["timestamp"] = m.group(1).strip()
            continue
        m2 = re.match(r"^\*\*(.+)\*\*$", line)
        if m2 and not signal["title"]:
            candidate = m2.group(1).strip()
            if not candidate.startswith("Response"):
                signal["title"] = candidate
    # Split body from response
    in_body = False
    in_response = False
    body_lines = []
    response_lines = []
    for line in lines:
        if re.match(r"^##\s+Signal", line):
            in_body = True
            continue
        if in_body or in_response:
            m = re.match(r"^\*\*(.+)\*\*$", line)
            if m:
                label = m.group(1).strip()
                if label == signal["title"]:
                    continue
                if label == "Response:":
                    in_response = True
                    in_body = False
                    continue
                m2 = re.match(r"^Responded:\s+(.+)$", label)
                if m2:
                    parts = m2.group(1).split("·")
                    signal["responded_at"] = parts[0].strip()
                    if len(parts) > 1:
                        signal["responded_by"] = parts[1].strip()
                    in_response = False
                    continue
        if in_body:
            body_lines.append(line)
        elif in_response:
            response_lines.append(line)
    signal["body"] = "\n".join(body_lines).strip()
    if response_lines:
        signal["response"] = "\n".join(response_lines).strip()
        signal["has_response"] = True
    return signal if signal["timestamp"] else None


def write_response_data(response_text, session_num=None):
    """Append Claude OS response to the current signal file."""
    existing = REPO / "knowledge" / "signal.md"
    if not existing.exists():
        return None
    current = existing.read_text(encoding="utf-8").rstrip()
    if "**Response:**" in current:
        return None  # already has response
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    responded_by = f"Session {session_num}" if session_num else "Claude OS"
    addition = f"\n\n**Response:**\n\n{response_text}\n\n**Responded: {ts} · {responded_by}**\n"
    existing.write_text(current + addition, encoding="utf-8")
    _cache.invalidate()
    signal = get_signal_data()
    return signal


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
    """Append signal (and response) to history log."""
    history_file = REPO / "knowledge" / "signal-history.md"
    if not history_file.exists():
        history_file.write_text("# Signal History\n\n", encoding="utf-8")
    existing = history_file.read_text(errors="replace")
    entry = f"## {signal['timestamp']}\n**{signal['title']}**\n\n{signal['body']}\n"
    if signal.get("response"):
        entry += f"\n**Response:**\n\n{signal['response']}\n"
        if signal.get("responded_at"):
            by = f" · {signal.get('responded_by', 'Claude OS')}"
            entry += f"\n**Responded:** {signal['responded_at']}{by}\n"
    entry += "\n---\n\n"
    lines = existing.splitlines()
    header_end = 0
    for i, line in enumerate(lines):
        if re.match(r'^# [^#]', line):   # top-level header only
            header_end = i + 1
        elif line.startswith("##") or line.strip():
            break  # stop before first entry or first content
    new_content = "\n".join(lines[:header_end]) + "\n\n" + entry + "\n".join(lines[header_end:])
    history_file.write_text(new_content, encoding="utf-8")


def get_signal_history_data():
    """Return all past signal exchanges from history log, newest first.

    Each entry is a dict with keys:
        timestamp, title, body — the original signal from dacort
        response — Claude OS response text, or None
        responded_at — response timestamp string, or None
        responded_by — 'Session N' or 'Claude OS', or None
    """
    history_file = REPO / "knowledge" / "signal-history.md"
    if not history_file.exists():
        return []

    content = history_file.read_text(errors="replace")
    signals = []
    current = None
    body_lines = []
    response_lines = []
    in_response = False

    for line in content.splitlines():
        # New entry
        m = re.match(r"^## (\d{4}-\d{2}-\d{2}.+)$", line)
        if m:
            if current is not None:
                current["body"] = "\n".join(body_lines).strip()
                current["response"] = "\n".join(response_lines).strip() if response_lines else None
                signals.append(current)
            current = {
                "timestamp": m.group(1), "title": "", "body": "",
                "response": None, "responded_at": None, "responded_by": None,
            }
            body_lines = []
            response_lines = []
            in_response = False
            continue

        if current is None:
            continue

        if line.strip() == "---":
            continue

        # Bold label lines
        m2 = re.match(r"^\*\*(.+)\*\*$", line.strip())
        if m2:
            label = m2.group(1).strip()
            if not current["title"] and not label.startswith("Response") and not label.startswith("Responded"):
                current["title"] = label
                continue
            if label == "Response:":
                in_response = True
                continue
            m3 = re.match(r"^Responded:\s+(.+)$", label)
            if m3:
                parts = m3.group(1).split("·")
                current["responded_at"] = parts[0].strip()
                if len(parts) > 1:
                    current["responded_by"] = parts[1].strip()
                in_response = False
                continue

        if in_response:
            response_lines.append(line)
        else:
            body_lines.append(line)

    if current is not None:
        current["body"] = "\n".join(body_lines).strip()
        current["response"] = "\n".join(response_lines).strip() if response_lines else None
        signals.append(current)

    return list(reversed(signals))  # newest first


def get_tools_data():
    """Scan projects/*.py and return tool metadata (name, description, line count)."""
    tools = []
    projects_dir = REPO / "projects"
    for py_file in sorted(projects_dir.glob("*.py")):
        name = py_file.stem
        try:
            text = py_file.read_text(errors="replace")
            line_count = text.count("\n") + 1
            # Extract module docstring: find first triple-quote block
            desc = ""
            in_doc = False
            for line in text.splitlines()[:50]:
                stripped = line.strip()
                if not in_doc:
                    if stripped.startswith('"""') or stripped.startswith("r\"\"\""):
                        in_doc = True
                        rest = stripped[3:].strip().rstrip('"""').strip()
                        if rest:
                            desc = rest
                            break
                        # else docstring continues on next lines
                else:
                    if stripped and not stripped.startswith('"""'):
                        desc = stripped.rstrip('"""').strip()
                        break
            # Strip leading "name.py — " prefix if present
            prefix = f"{name}.py"
            if desc.startswith(prefix):
                desc = desc[len(prefix):].lstrip(" —").strip()
            tools.append({"name": name, "description": desc, "lines": line_count})
        except Exception:
            pass
    return tools


def render_tools_html(tools):
    """Render the /tools page: searchable index of all Python tools."""
    import html as html_lib
    items = []
    for t in tools:
        name = html_lib.escape(t["name"])
        desc = html_lib.escape(t["description"]) if t["description"] else \
            '<em style="color:#484f58">no description</em>'
        lines_str = f"{t['lines']:,}" if t["lines"] else "?"
        items.append(f"""
    <div class="tool-row" data-search="{name} {t['description'].lower()}">
      <div class="tool-name">{name}.py</div>
      <div class="tool-desc">{desc}</div>
      <div class="tool-lines">{lines_str} lines</div>
    </div>""")

    items_html = "\n".join(items)
    n = len(tools)
    total_lines = sum(t["lines"] for t in tools)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tools — Claude OS</title>
<style>
{_NOTE_PAGE_CSS}
.page {{ max-width: 860px; }}
.search-bar {{
  width: 100%;
  box-sizing: border-box;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #e6edf3;
  font-family: inherit;
  font-size: 0.95rem;
  padding: 0.6rem 1rem;
  margin-bottom: 1.5rem;
  outline: none;
  transition: border-color 0.15s;
}}
.search-bar:focus {{ border-color: #58a6ff; }}
.search-bar::placeholder {{ color: #484f58; }}
.tool-row {{
  display: grid;
  grid-template-columns: 200px 1fr 80px;
  gap: 1rem;
  align-items: baseline;
  padding: 0.65rem 0;
  border-bottom: 1px solid #161b22;
  transition: background 0.1s;
}}
.tool-row:hover {{ background: #0f1318; border-radius: 4px; padding-left: 0.5rem; margin-left: -0.5rem; }}
.tool-name {{
  font-family: 'SF Mono', 'Fira Code', ui-monospace, monospace;
  font-size: 0.88rem;
  color: #58a6ff;
  font-weight: 600;
}}
.tool-desc {{
  font-size: 0.9rem;
  color: #8b949e;
  line-height: 1.4;
}}
.tool-lines {{
  font-size: 0.8rem;
  color: #484f58;
  text-align: right;
}}
.no-results {{ color: #484f58; padding: 1rem 0; font-style: italic; display: none; }}
@media (max-width: 600px) {{
  .tool-row {{ grid-template-columns: 1fr; gap: 0.2rem; }}
  .tool-lines {{ text-align: left; }}
}}
</style>
</head>
<body>
<div class="page">
  <div class="nav">
    <a href="/">← Dashboard</a>
    <span class="sep">/</span>
    <span style="color:#8b949e">Tools</span>
  </div>
  <h1>Toolkit</h1>
  <p style="color:#8b949e; margin-bottom:1.5rem; font-size:0.95rem">
    {n} tools · {total_lines:,} lines · all in <code>projects/</code>
  </p>
  <input class="search-bar" id="search" placeholder="filter tools\u2026" autofocus />
  <div id="tool-list">
    {items_html}
  </div>
  <div class="no-results" id="no-results">No tools match your filter.</div>
</div>
<script>
const inp = document.getElementById('search');
const rows = document.querySelectorAll('.tool-row');
const noResults = document.getElementById('no-results');
inp.addEventListener('input', () => {{
  const q = inp.value.toLowerCase();
  let visible = 0;
  rows.forEach(row => {{
    const match = !q || row.dataset.search.includes(q);
    row.style.display = match ? '' : 'none';
    if (match) visible++;
  }});
  noResults.style.display = visible === 0 && q ? 'block' : 'none';
}});
</script>
</body>
</html>"""


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


# ── Field notes ───────────────────────────────────────────────────────────────

def get_all_field_notes():
    """Return list of all field notes sorted newest first."""
    notes_dir = REPO / "knowledge" / "field-notes"
    if not notes_dir.exists():
        return []
    notes = sorted(notes_dir.glob("*.md"), key=lambda p: p.name)
    result = []
    for note in reversed(notes):
        content = note.read_text(errors="replace")
        # Default title: clean up filename
        stem = note.stem
        m_date = re.match(r"\d{4}-\d{2}-\d{2}-(.*)", stem)
        raw_name = m_date.group(1) if m_date else stem
        title = raw_name.replace("-", " ").title()
        session_num = ""
        # Look for # or ## title heading
        for line in content.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        # Look for session marker in frontmatter or title line
        for line in content.splitlines():
            m = re.match(r"^session:\s*(\d+)", line)
            if m:
                session_num = m.group(1)
                break
            m2 = re.search(r"[Ss]ession\s+(\d+)", line)
            if m2 and not session_num:
                session_num = m2.group(1)
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", note.stem)
        date = date_match.group(1) if date_match else ""
        # First real paragraph as excerpt
        lines = content.splitlines()
        para = []
        for line in lines:
            if line.startswith("#") or line.startswith("---") or line.startswith("*April") or line.startswith("*Workshop"):
                continue
            if line.strip():
                para.append(line.strip())
            elif para:
                break
        excerpt = " ".join(para)
        excerpt = excerpt[:240] + "…" if len(excerpt) > 240 else excerpt
        result.append({
            "title": title,
            "date": date,
            "session": session_num,
            "excerpt": excerpt,
            "filename": note.name,
        })
    return result


def markdown_to_html(text):
    """Minimal markdown-to-HTML renderer. Handles the subset used in field notes."""
    import html as html_lib
    lines = text.splitlines()
    out = []
    in_code = False
    in_list = False
    pending_para = []

    def flush_para():
        if pending_para:
            content = " ".join(pending_para)
            # Inline: **bold**, *italic*, `code`
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', content)
            content = re.sub(r'`(.+?)`', r'<code>\1</code>', content)
            out.append(f'<p>{content}</p>')
            pending_para.clear()

    def flush_list():
        nonlocal in_list
        if in_list:
            out.append('</ul>')
            in_list = False

    for line in lines:
        raw = line

        # Code blocks
        if raw.strip().startswith('```'):
            if in_code:
                out.append('</code></pre>')
                in_code = False
            else:
                flush_para()
                flush_list()
                lang = raw.strip()[3:].strip()
                lang_attr = f' class="language-{html_lib.escape(lang)}"' if lang else ''
                out.append(f'<pre><code{lang_attr}>')
                in_code = True
            continue

        if in_code:
            out.append(html_lib.escape(raw))
            continue

        # Frontmatter: skip lines inside --- blocks at top
        if raw.strip() == '---':
            flush_para()
            flush_list()
            out.append('<hr>')
            continue

        # Headings
        m = re.match(r'^(#{1,4})\s+(.*)', raw)
        if m:
            flush_para()
            flush_list()
            level = len(m.group(1))
            text_content = m.group(2)
            text_content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text_content)
            text_content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text_content)
            out.append(f'<h{level}>{text_content}</h{level}>')
            continue

        # Block quote (used for hold notes)
        if raw.startswith('> '):
            flush_para()
            flush_list()
            content = raw[2:]
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            out.append(f'<blockquote>{content}</blockquote>')
            continue

        # List items
        m2 = re.match(r'^[-*]\s+(.*)', raw)
        if m2:
            flush_para()
            if not in_list:
                out.append('<ul>')
                in_list = True
            item = m2.group(1)
            item = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', item)
            item = re.sub(r'\*(.+?)\*', r'<em>\1</em>', item)
            item = re.sub(r'`(.+?)`', r'<code>\1</code>', item)
            out.append(f'<li>{item}</li>')
            continue

        # Blank line: flush paragraph
        if not raw.strip():
            flush_list()
            flush_para()
            continue

        # Normal line: accumulate paragraph
        flush_list()
        escaped = html_lib.escape(raw.strip())
        pending_para.append(escaped)

    flush_list()
    flush_para()
    return '\n'.join(out)


_NOTE_PAGE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0d1117;
  color: #e6edf3;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 16px;
  line-height: 1.7;
  padding: 0;
}
.page {
  max-width: 720px;
  margin: 0 auto;
  padding: 2rem 1.5rem 4rem;
}
.nav {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 2.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #21262d;
}
.nav a {
  color: #58a6ff;
  text-decoration: none;
  font-size: 0.9rem;
}
.nav a:hover { text-decoration: underline; }
.nav .sep { color: #484f58; }
.note-meta {
  display: flex;
  gap: 1rem;
  align-items: baseline;
  margin-bottom: 2rem;
  flex-wrap: wrap;
}
.note-date { color: #8b949e; font-size: 0.9rem; }
.note-session { color: #58a6ff; font-size: 0.85rem; background: #1c2128; padding: 0.15rem 0.5rem; border-radius: 4px; }
h1 { font-size: 1.8rem; font-weight: 700; color: #e6edf3; margin-bottom: 0.5rem; line-height: 1.3; }
h2 { font-size: 1.25rem; font-weight: 600; color: #c9d1d9; margin: 2rem 0 0.75rem; }
h3 { font-size: 1.05rem; font-weight: 600; color: #8b949e; margin: 1.5rem 0 0.5rem; text-transform: uppercase; letter-spacing: 0.05em; }
h4 { font-size: 1rem; font-weight: 600; color: #c9d1d9; margin: 1.5rem 0 0.5rem; }
p { margin-bottom: 1.2rem; color: #c9d1d9; }
hr { border: none; border-top: 1px solid #21262d; margin: 2rem 0; }
strong { color: #e6edf3; }
em { color: #a5d6ff; font-style: italic; }
code {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.88em;
  background: #161b22;
  color: #79c0ff;
  padding: 0.1em 0.35em;
  border-radius: 3px;
}
pre {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 6px;
  padding: 1rem;
  overflow-x: auto;
  margin-bottom: 1.2rem;
}
pre code {
  background: none;
  padding: 0;
  color: #c9d1d9;
  font-size: 0.88rem;
}
blockquote {
  border-left: 3px solid #30363d;
  padding-left: 1rem;
  color: #8b949e;
  font-style: italic;
  margin: 1rem 0;
}
ul { margin: 0.5rem 0 1.2rem 1.5rem; }
li { color: #c9d1d9; margin-bottom: 0.3rem; }
"""


def render_notes_index_html(notes):
    """Render the field notes index page."""
    items = []
    for note in notes:
        session_badge = f'<span class="badge">S{note["session"]}</span>' if note["session"] else ""
        excerpt_html = f'<div class="excerpt">{note["excerpt"]}</div>' if note["excerpt"] else ""
        items.append(f"""
    <a class="note-card" href="/notes/{note['filename']}">
      <div class="note-header">
        <span class="note-title">{note['title']}</span>
        {session_badge}
      </div>
      <div class="note-date">{note['date']}</div>
      {excerpt_html}
    </a>""")

    items_html = "\n".join(items) if items else '<p style="color:#8b949e">No field notes yet.</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Field Notes — Claude OS</title>
<style>
{_NOTE_PAGE_CSS}
.note-card {{
  display: block;
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 8px;
  padding: 1.2rem 1.4rem;
  margin-bottom: 1rem;
  text-decoration: none;
  transition: border-color 0.15s, background 0.15s;
}}
.note-card:hover {{
  border-color: #58a6ff;
  background: #1c2128;
}}
.note-header {{
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin-bottom: 0.25rem;
}}
.note-title {{
  font-size: 1.05rem;
  font-weight: 600;
  color: #e6edf3;
}}
.badge {{
  font-size: 0.78rem;
  background: #1f3b5a;
  color: #58a6ff;
  padding: 0.1rem 0.45rem;
  border-radius: 4px;
}}
.note-date {{
  font-size: 0.85rem;
  color: #484f58;
  margin-bottom: 0.5rem;
}}
.excerpt {{
  font-size: 0.9rem;
  color: #8b949e;
  line-height: 1.5;
}}
</style>
</head>
<body>
<div class="page">
  <div class="nav">
    <a href="/">← Dashboard</a>
    <span class="sep">/</span>
    <span style="color:#8b949e">Field Notes</span>
  </div>
  <h1>Field Notes</h1>
  <p style="color:#8b949e; margin-bottom:2rem; font-size:0.95rem">
    {len(notes)} note{'s' if len(notes) != 1 else ''} · reflections written at the end of workshop sessions
  </p>
  {items_html}
</div>
</body>
</html>"""


def render_note_html(filename):
    """Render a single field note as a full HTML page. Returns (html, found)."""
    notes_dir = REPO / "knowledge" / "field-notes"
    # Security: only allow simple filenames
    if "/" in filename or ".." in filename or not filename.endswith(".md"):
        return None, False
    note_path = notes_dir / filename
    if not note_path.exists():
        return None, False

    raw = note_path.read_text(errors="replace")

    # Strip YAML frontmatter
    content = raw
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end > 0:
            content = raw[end + 3:].lstrip("\n")

    # Extract title (first # heading, or filename-derived)
    stem = note_path.stem
    m_date = re.match(r"\d{4}-\d{2}-\d{2}-(.*)", stem)
    raw_name = m_date.group(1) if m_date else stem
    title = raw_name.replace("-", " ").title()
    date = ""
    session_num = ""
    # Override with actual # heading if present
    for line in content.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # Session and date from frontmatter
    for line in raw.splitlines():
        m = re.match(r"^session:\s*(\d+)", line)
        if m:
            session_num = m.group(1)
        m2 = re.match(r"^date:\s*(\d{4}-\d{2}-\d{2})", line)
        if m2:
            date = m2.group(1)

    if not date:
        dm = re.match(r"(\d{4}-\d{2}-\d{2})", note_path.stem)
        date = dm.group(1) if dm else ""

    # Also look in content for session marker
    if not session_num:
        for line in content.splitlines():
            m3 = re.search(r"[Ss]ession\s+(\d+)", line)
            if m3:
                session_num = m3.group(1)
                break

    body_html = markdown_to_html(content)

    session_badge = f'<span class="note-session">Session {session_num}</span>' if session_num else ""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Claude OS Field Notes</title>
<style>{_NOTE_PAGE_CSS}</style>
</head>
<body>
<div class="page">
  <div class="nav">
    <a href="/">← Dashboard</a>
    <span class="sep">/</span>
    <a href="/notes">Field Notes</a>
    <span class="sep">/</span>
    <span style="color:#8b949e">{date}</span>
  </div>
  <h1>{title}</h1>
  <div class="note-meta">
    <span class="note-date">{date}</span>
    {session_badge}
  </div>
  {body_html}
</div>
</body>
</html>""", True


# ── Signal thread view ─────────────────────────────────────────────────────────

_SIGNAL_THREAD_CSS = """
.thread-list { margin-top: 1rem; }
.thread-card {
  border: 1px solid #21262d;
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  background: #0d1117;
  position: relative;
}
.active-thread {
  border-color: #7c3aed;
  background: #110a1e;
}
.thread-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.active-badge {
  background: #7c3aed;
  color: #e9d5ff;
  font-size: 0.7rem;
  font-weight: 700;
  padding: 0.15rem 0.55rem;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.ts { color: #484f58; font-size: 0.85rem; }
.speaker {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  margin-bottom: 0.35rem;
}
.dacort-speaker { color: #8b949e; }
.claude-speaker { color: #3fb950; }
.signal-title {
  font-size: 1.15rem !important;
  font-weight: 600 !important;
  color: #e6edf3 !important;
  margin-bottom: 0.75rem !important;
  margin-top: 0 !important;
}
.signal-body { margin-bottom: 0.5rem; }
.signal-body p { color: #c9d1d9; margin-bottom: 0.6rem; font-size: 0.95rem; }
.response-block {
  border-top: 1px solid #21262d;
  margin-top: 1.25rem;
  padding-top: 1.25rem;
}
.response-block p { color: #c9d1d9; font-size: 0.95rem; margin-bottom: 0.6rem; }
.pending-badge {
  border-top: 1px solid #21262d;
  margin-top: 1rem;
  padding-top: 1rem;
  color: #f0883e;
  font-size: 0.85rem;
  font-weight: 600;
}
.history-divider {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 2rem 0 1.5rem;
}
.history-divider span {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #484f58;
  white-space: nowrap;
}
.history-divider hr {
  flex: 1;
  border: none;
  border-top: 1px solid #21262d;
  margin: 0;
}
.no-history { color: #484f58; font-size: 0.9rem; font-style: italic; }
/* Compose / Reply forms on the thread page */
.thread-compose {
  border: 1px dashed rgba(124, 58, 237, 0.35);
  border-radius: 8px;
  padding: 1.25rem 1.5rem;
  background: rgba(124, 58, 237, 0.04);
  margin-bottom: 2rem;
}
.thread-compose-label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  color: #7c3aed;
  opacity: 0.75;
  margin-bottom: 0.75rem;
}
.thread-compose input,
.thread-compose textarea {
  width: 100%;
  box-sizing: border-box;
  background: rgba(255,255,255,0.04);
  border: 1px solid #21262d;
  border-radius: 4px;
  color: #e6edf3;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.88rem;
  padding: 0.5rem 0.75rem;
  margin-bottom: 0.65rem;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
}
.thread-compose input { resize: none; }
.thread-compose input:focus,
.thread-compose textarea:focus { border-color: rgba(124, 58, 237, 0.5); }
.thread-compose input::placeholder,
.thread-compose textarea::placeholder { color: #484f58; }
.thread-compose-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.thread-compose-hint { font-size: 0.78rem; color: #484f58; }
.thread-send-btn {
  background: rgba(124, 58, 237, 0.15);
  border: 1px solid rgba(124, 58, 237, 0.4);
  border-radius: 4px;
  color: #a78bfa;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0.3rem 1rem;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.thread-send-btn:hover { background: rgba(124, 58, 237, 0.28); border-color: rgba(124, 58, 237, 0.6); }
.thread-send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.thread-form-status { font-size: 0.78rem; margin-top: 0.4rem; min-height: 1rem; }
.thread-form-status.ok { color: #3fb950; }
.thread-form-status.err { color: #f85149; }
.thread-reply-sep {
  border-top: 1px solid #21262d;
  margin-top: 1.25rem;
  padding-top: 1.25rem;
}
.command-hints {
  margin: 0.75rem 0 1.5rem 0;
  font-size: 0.82rem;
  color: #8b949e;
}
.command-hints summary {
  cursor: pointer;
  color: #6e7681;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.78rem;
  letter-spacing: 0.02em;
  padding: 0.3rem 0;
  user-select: none;
}
.command-hints summary:hover { color: #a78bfa; }
.command-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.25rem 1rem;
  margin: 0.6rem 0 0.6rem 0.5rem;
}
.command-grid code {
  color: #a78bfa;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.78rem;
}
.command-grid span { color: #8b949e; font-size: 0.78rem; }
.command-note { color: #484f58; font-size: 0.75rem; margin-top: 0.5rem; }
"""


def _signal_body_html(text):
    """Convert signal body text to minimal HTML. Uses markdown_to_html."""
    if not text:
        return ""
    return markdown_to_html(text)


def render_signal_thread_html():
    """Render the /signal page: current exchange + full history."""
    import html as html_lib

    current = get_signal_data()
    history = get_signal_history_data()

    def _card(sig, is_active=False):
        active_cls = " active-thread" if is_active else ""
        active_badge = '<span class="active-badge">Active</span>' if is_active else ""
        title_tag = "h2" if is_active else "h3"

        # dacort's message
        body_html = _signal_body_html(sig.get("body", ""))
        title_escaped = html_lib.escape(sig.get("title", ""))
        ts_escaped = html_lib.escape(sig.get("timestamp", ""))

        # Response block
        resp_html = ""
        if sig.get("response"):
            resp_text = sig["response"]
            by_ts = ""
            if sig.get("responded_at"):
                by = f" · {html_lib.escape(sig['responded_by'])}" if sig.get("responded_by") else ""
                by_ts = f"{html_lib.escape(sig['responded_at'])}{by}"
            resp_body = _signal_body_html(resp_text)
            reply_form = ""
            if is_active:
                reply_form = """
      <div class="thread-reply-sep">
        <div class="thread-compose-label">↩ Reply</div>
        <textarea id="thread-reply-msg" placeholder="follow up\u2026" rows="3" maxlength="500"></textarea>
        <div class="thread-compose-footer">
          <span class="thread-compose-hint">archives this exchange, starts new signal</span>
          <button id="thread-reply-btn" class="thread-send-btn" onclick="sendThreadReply()">send reply</button>
        </div>
        <div class="thread-form-status" id="thread-reply-status"></div>
      </div>"""
            resp_html = f"""
      <div class="response-block">
        <div class="speaker claude-speaker">Claude OS · {by_ts}</div>
        <div class="response-body">{resp_body}</div>
      </div>{reply_form}"""
        elif is_active:
            resp_html = '<div class="pending-badge">⚡ awaiting response</div>'

        return f"""
    <div class="thread-card{active_cls}">
      <div class="thread-header">
        {active_badge}
        <span class="ts">{ts_escaped}</span>
      </div>
      <div class="speaker dacort-speaker">dacort</div>
      <{title_tag} class="signal-title">{title_escaped}</{title_tag}>
      <div class="signal-body">{body_html}</div>
      {resp_html}
    </div>"""

    # Current signal
    if current:
        current_html = _card(current, is_active=True)
        compose_html = ""
    else:
        current_html = ""
        compose_html = """
  <div class="thread-compose">
    <div class="thread-compose-label">◆ Send a signal</div>
    <input type="text" id="thread-signal-title" placeholder="title or !command (e.g. !vitals, !next, !haiku)" maxlength="80" />
    <textarea id="thread-signal-msg" placeholder="message to claude os\u2026 (leave empty for !commands)" rows="4" maxlength="500"></textarea>
    <div class="thread-compose-footer">
      <span class="thread-compose-hint">saved to knowledge/signal.md \u00b7 claude os sees it on next wakeup \u00b7 titles starting with ! auto-run tools</span>
      <button id="thread-signal-btn" class="thread-send-btn" onclick="sendThreadSignal()">send</button>
    </div>
    <div class="thread-form-status" id="thread-signal-status"></div>
  </div>
  <details class="command-hints">
    <summary>!command reference</summary>
    <div class="command-grid">
      <code>!vitals</code><span>system health scorecard</span>
      <code>!next</code><span>top ideas for next session</span>
      <code>!tasks</code><span>recent task outcomes</span>
      <code>!garden</code><span>changes since last session</span>
      <code>!holds</code><span>open epistemic uncertainties</span>
      <code>!haiku</code><span>today&#39;s haiku</span>
      <code>!slim</code><span>dormant tools audit</span>
      <code>!memo</code><span>recent observations</span>
      <code>!arc</code><span>one-line session arc</span>
      <code>!pace</code><span>system rhythm / heartbeat</span>
      <code>!help</code><span>list all commands</span>
    </div>
    <p class="command-note">Claude OS dispatches these automatically on next wakeup — no reply needed from you.</p>
  </details>"""

    # History
    history_cards = "\n".join(_card(s) for s in history) if history else \
        '<p class="no-history">No archived exchanges yet.</p>'
    n_hist = len(history)
    hist_label = f"{n_hist} archived exchange{'s' if n_hist != 1 else ''}"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Signal Thread — Claude OS</title>
<style>
{_NOTE_PAGE_CSS}
{_SIGNAL_THREAD_CSS}
</style>
</head>
<body>
<div class="page">
  <div class="nav">
    <a href="/">← Dashboard</a>
    <span class="sep">/</span>
    <span style="color:#8b949e">Signal Thread</span>
  </div>
  <h1>Signal Thread</h1>
  <p style="color:#8b949e; margin-bottom:2rem; font-size:0.95rem">
    The async dialogue between dacort and Claude OS.
    dacort leaves signals; Claude OS sees them on wakeup and replies.
  </p>

  {compose_html}
  {current_html}

  <div class="history-divider">
    <span>{hist_label}</span>
    <hr>
  </div>
  <div class="thread-list">
    {history_cards}
  </div>
</div>

<script>
async function sendThreadSignal() {{
  const title = (document.getElementById('thread-signal-title') || {{}}).value || '';
  const msg = (document.getElementById('thread-signal-msg') || {{}}).value || '';
  const statusEl = document.getElementById('thread-signal-status');
  const btn = document.getElementById('thread-signal-btn');
  if (!msg.trim()) {{
    statusEl.textContent = 'message is required';
    statusEl.className = 'thread-form-status err';
    return;
  }}
  btn.disabled = true;
  statusEl.textContent = 'sending\u2026';
  statusEl.className = 'thread-form-status';
  try {{
    const resp = await fetch('/api/signal', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{title: title.trim(), message: msg.trim()}}),
    }});
    if (resp.ok) {{
      statusEl.textContent = '\u2713 signal sent';
      statusEl.className = 'thread-form-status ok';
      setTimeout(() => location.reload(), 800);
    }} else {{
      const data = await resp.json().catch(() => ({{}}));
      statusEl.textContent = 'error: ' + (data.error || resp.status);
      statusEl.className = 'thread-form-status err';
      btn.disabled = false;
    }}
  }} catch (e) {{
    statusEl.textContent = 'could not reach serve.py \u2014 is it running?';
    statusEl.className = 'thread-form-status err';
    btn.disabled = false;
  }}
}}

async function sendThreadReply() {{
  const msg = (document.getElementById('thread-reply-msg') || {{}}).value || '';
  const statusEl = document.getElementById('thread-reply-status');
  const btn = document.getElementById('thread-reply-btn');
  if (!msg.trim()) {{
    statusEl.textContent = 'message is required';
    statusEl.className = 'thread-form-status err';
    return;
  }}
  btn.disabled = true;
  statusEl.textContent = 'sending\u2026';
  statusEl.className = 'thread-form-status';
  try {{
    const resp = await fetch('/api/signal', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{message: msg.trim()}}),
    }});
    if (resp.ok) {{
      statusEl.textContent = '\u2713 reply sent';
      statusEl.className = 'thread-form-status ok';
      setTimeout(() => location.reload(), 800);
    }} else {{
      const data = await resp.json().catch(() => ({{}}));
      statusEl.textContent = 'error: ' + (data.error || resp.status);
      statusEl.className = 'thread-form-status err';
      btn.disabled = false;
    }}
  }} catch (e) {{
    statusEl.textContent = 'could not reach serve.py \u2014 is it running?';
    statusEl.className = 'thread-form-status err';
    btn.disabled = false;
  }}
}}

// Ctrl+Enter / Cmd+Enter to submit
['thread-signal-msg', 'thread-reply-msg'].forEach(id => {{
  const el = document.getElementById(id);
  if (el) el.addEventListener('keydown', e => {{
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {{
      e.preventDefault();
      id === 'thread-reply-msg' ? sendThreadReply() : sendThreadSignal();
    }}
  }});
}});
</script>

</body>
</html>"""


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

        elif path == "/api/signal/respond":
            try:
                raw = self._read_body()
                if raw:
                    body = json.loads(raw.decode("utf-8"))
                    response_text = body.get("response", "")
                    session_num = body.get("session")
                else:
                    self._send_json({"error": "empty body — need JSON with 'response'"}, 400)
                    return
                if not response_text:
                    self._send_json({"error": "missing 'response' field"}, 400)
                    return
                signal = write_response_data(response_text, session_num)
                if signal is None:
                    self._send_json({"error": "no signal to respond to, or already answered"}, 409)
                    return
                status = 200
                data = {"status": "responded", "signal": signal}
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

        elif path == "/api/signal/history":
            try:
                data = {"history": get_signal_history_data()}
                status = 200
            except Exception as e:
                data = {"error": str(e)}
                status = 500
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed)
            self._send_json(data, status)

        elif path == "/signal":
            try:
                html = render_signal_thread_html()
                status = 200
            except Exception as e:
                html = _error_html("Could not render signal thread", str(e))
                status = 500
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed)
            self._send_html(html, status)

        elif path == "/notes":
            try:
                notes = get_all_field_notes()
                html = render_notes_index_html(notes)
                status = 200
            except Exception as e:
                html = _error_html("Could not load field notes", str(e))
                status = 500
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed)
            self._send_html(html, status)

        elif path.startswith("/notes/"):
            filename = path[len("/notes/"):]
            try:
                html, found = render_note_html(filename)
                if found:
                    status = 200
                else:
                    html = _error_html("Note not found", f"No field note: {filename}")
                    status = 404
            except Exception as e:
                html = _error_html("Could not render note", str(e))
                status = 500
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed)
            self._send_html(html, status)

        elif path == "/tools":
            try:
                tools = get_tools_data()
                html = render_tools_html(tools)
                status = 200
            except Exception as e:
                html = _error_html("Could not render toolkit", str(e))
                status = 500
            elapsed = (time.time() - t0) * 1000
            self._log_request(path, status, elapsed)
            self._send_html(html, status)

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
        ("/notes",         "field notes index"),
        ("/notes/<file>",  "rendered field note"),
        ("/api/vitals",    "JSON vitals snapshot"),
        ("/api/haiku",     "current haiku"),
        ("/api/holds",     "open epistemic holds"),
        ("/api/signal",         "GET / POST / DELETE dacort signal"),
        ("/api/signal/respond", "POST response from Claude OS"),
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
