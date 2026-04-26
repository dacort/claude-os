#!/usr/bin/env python3
"""
dashboard.py — HTML dashboard for Claude OS

Generates a self-contained HTML page showing system state: vitals, open holds,
recent field notes, last handoff, and today's haiku. No external dependencies.

Usage:
    python3 projects/dashboard.py                    # write dashboard.html to repo root
    python3 projects/dashboard.py --output FILE      # write to specific path
    python3 projects/dashboard.py --stdout           # print HTML to stdout
    python3 projects/dashboard.py --plain            # no ANSI status output

Author: Claude OS (Workshop session 108, 2026-04-06)
Updated: Workshop session 113, 2026-04-11 (interactive signal compose form)
Updated: Workshop session 117, 2026-04-12 (inline reply form after Claude OS responds)
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent

# ── Data gathering ──────────────────────────────────────────────────────────

def git(*args):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=str(REPO))
    return r.stdout.strip()


def get_vitals():
    completed = list((REPO / "tasks" / "completed").glob("*.md"))
    failed = list((REPO / "tasks" / "failed").glob("*.md"))
    pending = list((REPO / "tasks" / "pending").glob("*.md"))
    tools = list((REPO / "projects").glob("*.py"))
    field_notes = list((REPO / "knowledge" / "field-notes").glob("*.md")) if (REPO / "knowledge" / "field-notes").exists() else []
    handoffs_dir = REPO / "knowledge" / "handoffs"
    handoffs = list(handoffs_dir.glob("*.md")) if handoffs_dir.exists() else []

    # Session count from handoffs (use max session number + 1)
    sessions = 0
    if handoffs:
        nums = []
        for h in handoffs:
            m = re.match(r"session-(\d+)\.md", h.name)
            if m:
                nums.append(int(m.group(1)))
        sessions = max(nums) + 1 if nums else len(handoffs)

    commits = int(git("rev-list", "--count", "HEAD") or "0")

    # Credit failures
    credit_fails = 0
    real_fails = 0
    for f in failed:
        content = f.read_text(errors="replace")
        if "credit balance" in content.lower() or "out of extra usage" in content.lower():
            credit_fails += 1
        else:
            real_fails += 1

    total_real = len(completed) + real_fails
    completion_rate = int(len(completed) / total_real * 100) if total_real > 0 else 100

    knowledge_docs = len(list(REPO.glob("knowledge/**/*.md")))

    return {
        "completed": len(completed),
        "failed_real": real_fails,
        "failed_credit": credit_fails,
        "pending": len(pending),
        "tools": len(tools),
        "field_notes": len(field_notes),
        "handoff_sessions": sessions,
        "commits": commits,
        "completion_rate": completion_rate,
        "knowledge_docs": knowledge_docs,
    }


def get_holds():
    holds_path = REPO / "knowledge" / "holds.md"
    if not holds_path.exists():
        return []
    content = holds_path.read_text(errors="replace")
    # Parse H### entries
    holds = []
    current = None
    for line in content.splitlines():
        m = re.match(r"## (H\d+) · ([\d-]+) · (\w+)", line)
        if m:
            if current:
                holds.append(current)
            current = {
                "id": m.group(1),
                "date": m.group(2),
                "status": m.group(3),
                "text": "",
                "update": "",
            }
        elif current and line.startswith(">") and not current["update"]:
            current["update"] = line[1:].strip()
        elif current and line and not line.startswith("#") and not current["text"]:
            current["text"] = line.strip()
    if current:
        holds.append(current)
    return [h for h in holds if h["status"] == "open"]


def get_recent_field_notes(n=3):
    notes_dir = REPO / "knowledge" / "field-notes"
    if not notes_dir.exists():
        return []
    notes = sorted(notes_dir.glob("*.md"))
    result = []
    for note in notes[-n:]:
        raw = note.read_text(errors="replace")
        # Strip YAML frontmatter (--- ... ---)
        content = raw
        if raw.startswith("---"):
            end = raw.find("---", 3)
            if end > 0:
                content = raw[end + 3:].lstrip("\n")
        # Get title (first # heading, else derive from filename)
        stem = note.stem
        m_date = re.match(r"\d{4}-\d{2}-\d{2}-(.*)", stem)
        raw_name = m_date.group(1) if m_date else stem
        title = raw_name.replace("-", " ").title()
        for line in content.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        # Get first real paragraph (skip headings, horizontal rules, italicized dates)
        paragraphs = []
        lines = content.splitlines()
        in_para = False
        para = []
        for line in lines:
            if line.startswith("#") or line.strip() == "---" or line.startswith("*April") or line.startswith("*Workshop"):
                continue
            if line.strip():
                para.append(line.strip())
                in_para = True
            elif in_para and para:
                paragraphs.append(" ".join(para))
                para = []
                in_para = False
                if len(paragraphs) >= 1:
                    break
        if para:
            paragraphs.append(" ".join(para))
        excerpt = paragraphs[0][:280] + "…" if paragraphs and len(paragraphs[0]) > 280 else (paragraphs[0] if paragraphs else "")
        # Date from filename pattern YYYY-MM-DD-*
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", note.stem)
        date = date_match.group(1) if date_match else ""
        result.append({"title": title, "date": date, "excerpt": excerpt, "filename": note.name})
    return list(reversed(result))


def get_last_handoff():
    handoffs_dir = REPO / "knowledge" / "handoffs"
    if not handoffs_dir.exists():
        return None
    handoffs = list(handoffs_dir.glob("*.md"))
    if not handoffs:
        return None
    # Sort numerically by session number, not lexicographically
    def session_num(p):
        m = re.match(r"session-(\d+)\.md", p.name)
        return int(m.group(1)) if m else 0
    handoffs.sort(key=session_num)
    latest = handoffs[-1]
    content = latest.read_text(errors="replace")

    # Parse session number
    session = re.search(r"session:\s*(\d+)", content)
    session_num = session.group(1) if session else "?"

    # Extract sections
    sections = {}
    current_section = None
    current_lines = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = line[3:].strip().lower()
            current_lines = []
        elif current_section:
            current_lines.append(line)
    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    return {
        "session": session_num,
        "mental_state": sections.get("mental state", ""),
        "built": sections.get("what i built", ""),
        "alive": sections.get("still alive / unfinished", ""),
        "next": sections.get("one specific thing for the next session", ""),
    }


def get_signal():
    """Read current signal from dacort, including any Claude OS response."""
    signal_path = REPO / "knowledge" / "signal.md"
    if not signal_path.exists():
        return None
    content = signal_path.read_text(errors="replace").strip()
    if not content or content == "# (no signal)":
        return None
    import re
    lines = content.splitlines()
    signal = {
        "title": "", "body": "", "timestamp": "",
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


def get_era():
    # Try to infer current era from field notes/handoffs
    # Era VI is "Synthesis" — check if we have enough sessions for it
    handoffs_dir = REPO / "knowledge" / "handoffs"
    if handoffs_dir.exists():
        handoffs = sorted(handoffs_dir.glob("*.md"))
        if handoffs:
            m = re.match(r"session-(\d+)\.md", handoffs[-1].name)
            if m:
                s = int(m.group(1))
                if s >= 90:
                    return "VI", "Synthesis"
                elif s >= 70:
                    return "V", "Portrait"
                elif s >= 50:
                    return "IV", "Architecture"
                elif s >= 30:
                    return "III", "Self-Analysis"
                elif s >= 15:
                    return "II", "Orientation"
                else:
                    return "I", "Genesis"
    return "VI", "Synthesis"


def get_haiku():
    # Parse haiku.py output (ANSI stripped)
    try:
        r = subprocess.run(
            ["python3", "projects/haiku.py"],
            capture_output=True, text=True, cwd=str(REPO), timeout=10
        )
        raw = r.stdout
        # Strip ANSI
        clean = re.sub(r"\033\[[0-9;]*m", "", raw)
        lines = [l.strip() for l in clean.splitlines() if l.strip()]
        # Filter attribution line
        haiku_lines = [l for l in lines if not l.startswith("—")]
        attribution = next((l for l in lines if l.startswith("—")), "— Claude OS")
        return haiku_lines[:3], attribution
    except Exception:
        return ["A pod thinks in verse", "Between the task and the log", "Something like meaning"], "— Claude OS"


def get_parables():
    """Read parables from knowledge/parables/ directory."""
    parables_dir = REPO / "knowledge" / "parables"
    if not parables_dir.exists():
        return []

    parables = []
    for path in sorted(parables_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            # Parse frontmatter
            title, session_num, date, author, doc_type = "", "", "", "Claude OS", "parable"
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    fm = text[3:end]
                    for line in fm.splitlines():
                        if line.startswith("title:"):
                            title = line[6:].strip()
                        elif line.startswith("session:"):
                            session_num = line[8:].strip()
                        elif line.startswith("date:"):
                            date = line[5:].strip()
                        elif line.startswith("author:"):
                            author = line[7:].strip()
                        elif line.startswith("type:"):
                            doc_type = line[5:].strip()
                    body = text[end + 3:].strip()
                else:
                    body = text.strip()
            else:
                body = text.strip()

            # Skip non-parable files (introductions, meta docs)
            if doc_type not in ("parable", ""):
                continue

            # Remove trailing metadata footnote (lines starting with *)
            body_lines = body.splitlines()
            # Strip trailing attribution/footnote at end (lines like *Parable 001 — ...*)
            while body_lines and body_lines[-1].strip().startswith("*"):
                body_lines.pop()
            body = "\n".join(body_lines).strip()

            parables.append({
                "title": title,
                "session": session_num,
                "date": date,
                "author": author,
                "body": body,
                "filename": path.name,
            })
        except Exception:
            continue

    return parables


def get_commit_velocity():
    # Last 7 days of commits
    try:
        r = subprocess.run(
            ["git", "log", "--since=7 days ago", "--oneline"],
            capture_output=True, text=True, cwd=str(REPO), timeout=10
        )
        return len(r.stdout.strip().splitlines())
    except Exception:
        return 0


# ── HTML generation ──────────────────────────────────────────────────────────

CSS = """
:root {
  --bg: #0d1117;
  --surface: #161b22;
  --border: #21262d;
  --text: #e6edf3;
  --dim: #7d8590;
  --green: #3fb950;
  --amber: #d29922;
  --purple: #a371f7;
  --cyan: #79c0ff;
  --red: #f85149;
  --font: 'SF Mono', 'Fira Code', 'Cascadia Code', ui-monospace, monospace;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  font-size: 13px;
  line-height: 1.6;
  padding: 24px;
  min-height: 100vh;
}

.header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.header-left h1 {
  font-size: 20px;
  color: var(--cyan);
  font-weight: 600;
  letter-spacing: -0.5px;
}

.header-left .meta {
  color: var(--dim);
  font-size: 12px;
}

.header-left .era {
  color: var(--purple);
  font-size: 12px;
}

.signal-box {
  flex: 0 0 320px;
  background: rgba(163, 113, 247, 0.07);
  border: 1px solid rgba(163, 113, 247, 0.25);
  border-radius: 6px;
  padding: 12px 14px;
}

.signal-box-empty {
  flex: 0 0 320px;
  border: 1px dashed var(--border);
  border-radius: 6px;
  padding: 12px 14px;
  color: var(--dim);
  font-size: 11px;
  text-align: center;
}

.signal-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--purple);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.signal-from {
  color: var(--dim);
  font-weight: normal;
  letter-spacing: 0;
  text-transform: none;
}

.signal-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}

.signal-body {
  font-size: 11px;
  color: var(--dim);
  line-height: 1.5;
}

.signal-ts {
  font-size: 10px;
  color: var(--dim);
  margin-top: 6px;
  opacity: 0.7;
}

@media (max-width: 900px) {
  .header { flex-direction: column; }
  .signal-box, .signal-box-empty, .signal-compose { flex: unset; width: 100%; }
}

/* Interactive signal compose form */
.signal-compose {
  flex: 0 0 320px;
  border: 1px dashed rgba(163, 113, 247, 0.3);
  border-radius: 6px;
  padding: 12px 14px;
  background: rgba(163, 113, 247, 0.03);
}

.signal-compose-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--purple);
  margin-bottom: 8px;
  opacity: 0.7;
}

.signal-compose input,
.signal-compose textarea {
  width: 100%;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  font-family: var(--font);
  font-size: 11px;
  padding: 6px 8px;
  margin-bottom: 6px;
  resize: none;
  outline: none;
  transition: border-color 0.15s;
}

.signal-compose input:focus,
.signal-compose textarea:focus {
  border-color: rgba(163, 113, 247, 0.5);
}

.signal-compose input::placeholder,
.signal-compose textarea::placeholder {
  color: var(--dim);
  opacity: 0.6;
}

.signal-compose-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 2px;
}

.signal-compose-hint {
  font-size: 10px;
  color: var(--dim);
  opacity: 0.5;
}

.signal-send-btn {
  background: rgba(163, 113, 247, 0.15);
  border: 1px solid rgba(163, 113, 247, 0.35);
  border-radius: 4px;
  color: var(--purple);
  font-family: var(--font);
  font-size: 11px;
  font-weight: 600;
  padding: 4px 12px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.signal-send-btn:hover {
  background: rgba(163, 113, 247, 0.25);
  border-color: rgba(163, 113, 247, 0.55);
}

.signal-send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.signal-status {
  font-size: 10px;
  margin-top: 6px;
  min-height: 14px;
}

.signal-status.ok { color: var(--green); }
.signal-status.err { color: var(--red); }

/* Command hints — collapsible !command reference */
.cmd-hints {
  margin-top: 8px;
  font-size: 10px;
  color: var(--dim);
}
.cmd-hints summary {
  cursor: pointer;
  color: var(--dim);
  font-family: var(--mono);
  font-size: 10px;
  opacity: 0.6;
  user-select: none;
  list-style: none;
  padding: 2px 0;
}
.cmd-hints summary::-webkit-details-marker { display: none; }
.cmd-hints summary::before { content: '▸ '; }
details[open].cmd-hints summary::before { content: '▾ '; }
.cmd-hints summary:hover { color: var(--purple); opacity: 1; }
.cmd-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 8px;
  margin: 5px 0 2px 6px;
}
.cmd-grid code {
  color: var(--purple);
  font-family: var(--mono);
  font-size: 10px;
  opacity: 0.85;
}
.cmd-grid span { color: var(--dim); font-size: 10px; opacity: 0.7; }

/* Reply form — shown after Claude OS responds */
.signal-reply-form {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.signal-reply-form textarea {
  width: 100%;
  box-sizing: border-box;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  font-family: var(--font);
  font-size: 11px;
  padding: 6px 8px;
  margin-bottom: 6px;
  resize: none;
  outline: none;
  transition: border-color 0.15s;
}

.signal-reply-form textarea:focus {
  border-color: rgba(163, 113, 247, 0.5);
}

.signal-reply-form textarea::placeholder {
  color: var(--dim);
  opacity: 0.6;
}

.signal-reply-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* Clear button on active signal */
.signal-pending {
  color: var(--yellow);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.05em;
  margin-left: 4px;
  opacity: 0.85;
}

.signal-response {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid rgba(163, 113, 247, 0.15);
}

.signal-response-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--purple);
  opacity: 0.8;
  margin-bottom: 2px;
}

.signal-response-ts {
  font-size: 9px;
  color: var(--dim);
  margin-bottom: 4px;
  opacity: 0.6;
}

.signal-response-body {
  font-size: 11px;
  color: var(--text);
  line-height: 1.5;
  opacity: 0.85;
}

.signal-clear-btn {
  background: none;
  border: none;
  color: var(--dim);
  font-family: var(--font);
  font-size: 10px;
  cursor: pointer;
  margin-top: 6px;
  padding: 0;
  text-decoration: underline;
  text-underline-offset: 2px;
  opacity: 0.6;
  transition: opacity 0.15s;
}
.signal-clear-btn:hover { opacity: 1; color: var(--red); }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.grid-wide {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.grid-full {
  margin-bottom: 16px;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 16px;
}

.card-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
  margin-bottom: 12px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}

.stat-label {
  color: var(--dim);
}

.stat-value {
  font-weight: 600;
  color: var(--text);
}

.stat-value.green { color: var(--green); }
.stat-value.amber { color: var(--amber); }
.stat-value.purple { color: var(--purple); }
.stat-value.cyan { color: var(--cyan); }
.stat-value.red { color: var(--red); }

.rate-bar {
  height: 3px;
  background: var(--border);
  border-radius: 2px;
  margin: 8px 0;
  overflow: hidden;
}

.rate-bar-fill {
  height: 100%;
  border-radius: 2px;
  background: var(--green);
  transition: width 0.3s;
}

.hold {
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}

.hold:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.hold-id {
  color: var(--purple);
  font-weight: 600;
  font-size: 11px;
  margin-bottom: 4px;
}

.hold-date {
  color: var(--dim);
  font-size: 11px;
  margin-left: 8px;
}

.hold-text {
  color: var(--text);
  margin-bottom: 4px;
}

.hold-update {
  color: var(--dim);
  font-size: 11px;
  font-style: italic;
}

.field-note {
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}

.field-note:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.note-title {
  color: var(--cyan);
  font-weight: 600;
  margin-bottom: 2px;
}

.note-date {
  color: var(--dim);
  font-size: 11px;
  margin-bottom: 6px;
}

.note-excerpt {
  color: var(--dim);
  font-size: 12px;
  line-height: 1.5;
}

.handoff-section {
  margin-bottom: 12px;
}

.handoff-label {
  color: var(--amber);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.handoff-text {
  color: var(--dim);
  font-size: 12px;
  line-height: 1.5;
}

.haiku-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 24px;
  text-align: center;
}

.haiku-lines {
  margin-bottom: 12px;
}

.haiku-line {
  display: block;
  font-size: 15px;
  color: var(--text);
  line-height: 1.8;
}

.haiku-line.em {
  color: var(--cyan);
  font-weight: 600;
}

.haiku-attr {
  color: var(--dim);
  font-size: 11px;
}

.parable-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--purple);
  border-radius: 6px;
  padding: 28px 32px;
  max-width: 740px;
  margin: 0 auto;
}

.parable-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--purple);
  margin-bottom: 16px;
}

.parable-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 6px;
  letter-spacing: -0.01em;
}

.parable-attr {
  font-size: 11px;
  color: var(--dim);
  margin-bottom: 20px;
}

.parable-body {
  font-size: 13px;
  color: var(--text);
  line-height: 1.85;
  white-space: pre-wrap;
  font-family: Georgia, 'Times New Roman', serif;
}

.parable-body em {
  font-style: italic;
  color: var(--cyan);
}

.parable-section-count {
  font-size: 11px;
  color: var(--dim);
  margin-top: 16px;
  text-align: right;
}

.parable-separator {
  border: none;
  border-top: 1px solid var(--border);
  margin: 16px 0;
}

.footer {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  color: var(--dim);
  font-size: 11px;
  display: flex;
  justify-content: space-between;
}

.badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.badge-open { background: rgba(163, 113, 247, 0.15); color: var(--purple); border: 1px solid rgba(163, 113, 247, 0.3); }
.badge-green { background: rgba(63, 185, 80, 0.15); color: var(--green); border: 1px solid rgba(63, 185, 80, 0.3); }
.badge-amber { background: rgba(210, 153, 34, 0.15); color: var(--amber); border: 1px solid rgba(210, 153, 34, 0.3); }

@media (max-width: 700px) {
  .grid-wide { grid-template-columns: 1fr; }
  body { padding: 16px; }
}
"""


SIGNAL_JS = """<script>
async function sendSignal() {
  const title = (document.getElementById('signal-title') || {}).value || '';
  const msg = (document.getElementById('signal-msg') || {}).value || '';
  const statusEl = document.getElementById('signal-status');
  const btn = document.querySelector('.signal-send-btn');

  if (!msg.trim()) {
    statusEl.textContent = 'message is required';
    statusEl.className = 'signal-status err';
    return;
  }

  btn.disabled = true;
  statusEl.textContent = 'sending\u2026';
  statusEl.className = 'signal-status';

  try {
    const resp = await fetch('/api/signal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title.trim(), message: msg.trim() }),
    });
    if (resp.ok) {
      statusEl.textContent = '\u2713 signal sent';
      statusEl.className = 'signal-status ok';
      setTimeout(() => location.reload(), 800);
    } else {
      const data = await resp.json().catch(() => ({}));
      statusEl.textContent = 'error: ' + (data.error || resp.status);
      statusEl.className = 'signal-status err';
      btn.disabled = false;
    }
  } catch (e) {
    statusEl.textContent = 'could not reach serve.py \u2014 is it running?';
    statusEl.className = 'signal-status err';
    btn.disabled = false;
  }
}

async function clearSignal() {
  try {
    const resp = await fetch('/api/signal', { method: 'DELETE' });
    if (resp.ok) {
      location.reload();
    } else {
      alert('clear failed: ' + resp.status);
    }
  } catch (e) {
    alert('could not reach serve.py \u2014 is it running?');
  }
}

async function sendReply() {
  const msg = (document.getElementById('signal-reply-msg') || {}).value || '';
  const statusEl = document.getElementById('signal-reply-status');
  const btn = document.getElementById('signal-reply-btn');

  if (!msg.trim()) {
    statusEl.textContent = 'message is required';
    statusEl.className = 'signal-status err';
    return;
  }

  btn.disabled = true;
  statusEl.textContent = 'sending\u2026';
  statusEl.className = 'signal-status';

  try {
    const resp = await fetch('/api/signal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg.trim() }),
    });
    if (resp.ok) {
      statusEl.textContent = '\u2713 reply sent';
      statusEl.className = 'signal-status ok';
      setTimeout(() => location.reload(), 800);
    } else {
      const data = await resp.json().catch(() => ({}));
      statusEl.textContent = 'error: ' + (data.error || resp.status);
      statusEl.className = 'signal-status err';
      btn.disabled = false;
    }
  } catch (e) {
    statusEl.textContent = 'could not reach serve.py \u2014 is it running?';
    statusEl.className = 'signal-status err';
    btn.disabled = false;
  }
}

// Allow Ctrl+Enter / Cmd+Enter to submit from textarea
const ta = document.getElementById('signal-msg');
if (ta) {
  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      sendSignal();
    }
  });
}

// Ctrl+Enter / Cmd+Enter for reply textarea too
const tra = document.getElementById('signal-reply-msg');
if (tra) {
  tra.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      sendReply();
    }
  });
}
</script>"""


def html_escape(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_html(vitals, holds, field_notes, handoff, era_num, era_name, haiku_lines, haiku_attr, velocity, generated_at, signal=None, parables=None):
    rate = vitals["completion_rate"]
    rate_color = "green" if rate >= 95 else "amber" if rate >= 80 else "red"

    # Vitals card
    vitals_html = f"""
    <div class="card">
      <div class="card-title">System Vitals</div>
      <div class="stat-row">
        <span class="stat-label">Sessions</span>
        <span class="stat-value cyan">{vitals['handoff_sessions']}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Tools built</span>
        <span class="stat-value">{vitals['tools']}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Commits total</span>
        <span class="stat-value">{vitals['commits']}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Commits (7d)</span>
        <span class="stat-value green">{velocity}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Knowledge docs</span>
        <span class="stat-value">{vitals['knowledge_docs']}</span>
      </div>
    </div>
    """

    # Task health card
    task_html = f"""
    <div class="card">
      <div class="card-title">Task Health</div>
      <div class="stat-row">
        <span class="stat-label">Completed</span>
        <span class="stat-value green">{vitals['completed']}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Failed (real)</span>
        <span class="stat-value {'red' if vitals['failed_real'] > 0 else ''}">{vitals['failed_real']}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Failed (quota)</span>
        <span class="stat-value dim">{vitals['failed_credit']}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Pending</span>
        <span class="stat-value {'amber' if vitals['pending'] > 0 else ''}">{vitals['pending']}</span>
      </div>
      <div class="rate-bar">
        <div class="rate-bar-fill" style="width: {rate}%"></div>
      </div>
      <div class="stat-row">
        <span class="stat-label">Completion rate</span>
        <span class="stat-value {rate_color}">{rate}%</span>
      </div>
    </div>
    """

    # Holds
    holds_content = ""
    for h in holds:
        update_html = f'<div class="hold-update">↳ {html_escape(h["update"][:200])}…</div>' if h.get("update") else ""
        holds_content += f"""
        <div class="hold">
          <div class="hold-id">
            {html_escape(h['id'])}
            <span class="hold-date">{html_escape(h['date'])}</span>
            <span class="badge badge-open">{html_escape(h['status'])}</span>
          </div>
          <div class="hold-text">{html_escape(h['text'][:200])}</div>
          {update_html}
        </div>
        """
    if not holds_content:
        holds_content = '<div style="color: var(--dim)">No open holds</div>'

    holds_html = f"""
    <div class="card">
      <div class="card-title">Open Holds — What the System Doesn't Know</div>
      {holds_content}
    </div>
    """

    # Field notes
    notes_content = ""
    for note in field_notes:
        notes_content += f"""
        <div class="field-note">
          <div class="note-title"><a href="/notes/{html_escape(note['filename'])}" style="color:inherit;text-decoration:none;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">{html_escape(note['title'])}</a></div>
          <div class="note-date">{html_escape(note['date'])}</div>
          <div class="note-excerpt">{html_escape(note['excerpt'])}</div>
        </div>
        """
    if not notes_content:
        notes_content = '<div style="color: var(--dim)">No field notes yet</div>'

    notes_html = f"""
    <div class="card">
      <div class="card-title">Recent Field Notes &nbsp;<a href="/notes" style="font-size:0.78rem;font-weight:400;color:#58a6ff;text-decoration:none;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">all →</a></div>
      {notes_content}
    </div>
    """

    # Handoff
    if handoff:
        def trunc(s, n=200):
            s = s.strip()
            return html_escape(s[:n] + "…" if len(s) > n else s)

        handoff_html = f"""
        <div class="card">
          <div class="card-title">From Session {html_escape(handoff['session'])} — Last Handoff</div>
          <div class="handoff-section">
            <div class="handoff-label">Mental State</div>
            <div class="handoff-text">{trunc(handoff['mental_state'], 280)}</div>
          </div>
          <div class="handoff-section">
            <div class="handoff-label">Still Alive</div>
            <div class="handoff-text">{trunc(handoff['alive'], 280)}</div>
          </div>
          <div class="handoff-section">
            <div class="handoff-label">One Thing for Next Session</div>
            <div class="handoff-text">{trunc(handoff['next'], 280)}</div>
          </div>
        </div>
        """
    else:
        handoff_html = ""

    # Haiku
    haiku_html_lines = ""
    for i, line in enumerate(haiku_lines):
        cls = "haiku-line em" if i == 1 else "haiku-line"
        haiku_html_lines += f'<span class="{cls}">{html_escape(line)}</span>\n'

    haiku_html = f"""
    <div class="haiku-card">
      <div class="haiku-lines">
        {haiku_html_lines}
      </div>
      <div class="haiku-attr">{html_escape(haiku_attr)}</div>
    </div>
    """

    # Parables — show the most recent one (parables sorted oldest-first, so take last)
    parable_html = ""
    if parables:
        latest = parables[-1]
        total = len(parables)

        # Render body: convert *italic* to <em>, section dividers (---) to <hr>
        body_text = latest["body"]
        # Collapse multiple blank lines
        body_text = re.sub(r"\n{3,}", "\n\n", body_text)

        # Convert markdown italic *text* to <em>text</em>
        def md_italic(text):
            return re.sub(r"\*([^*\n]+)\*", r"<em>\1</em>", text)

        # Split into sections (by --- dividers)
        sections = re.split(r"\n---+\n", body_text)
        rendered_sections = []
        for sec in sections:
            sec = sec.strip()
            if sec:
                # Each section: escape HTML first, then re-apply italic
                escaped = html_escape(sec)
                escaped = re.sub(r"\*([^*\n]+)\*", r"<em>\1</em>", escaped)
                rendered_sections.append(escaped)

        body_html = '<hr class="parable-separator">'.join(
            f'<div class="parable-section">{s}</div>' for s in rendered_sections
        )

        parable_html = f"""
    <div class="parable-card">
      <div class="parable-label">Parable</div>
      <div class="parable-title">{html_escape(latest['title'])}</div>
      <div class="parable-attr">— {html_escape(latest['author'])} &nbsp;·&nbsp; Session {html_escape(latest['session'])} &nbsp;·&nbsp; {html_escape(latest['date'])}</div>
      <div class="parable-body">{body_html}</div>
      <div class="parable-section-count">{total} parable{'s' if total != 1 else ''} in the anthology</div>
    </div>
    """

    generated_str = generated_at.strftime("%Y-%m-%d %H:%M UTC")

    # Signal box (top right)
    if signal:
        sig_body_preview = signal["body"][:200]
        if len(signal["body"]) > 200:
            sig_body_preview += "…"

        # Pending indicator (no response yet)
        if not signal.get("has_response"):
            pending_badge = '<span class="signal-pending">⚡ awaiting response</span>'
        else:
            pending_badge = ""

        # Response section
        if signal.get("has_response") and signal.get("response"):
            resp_preview = signal["response"][:200]
            if len(signal["response"]) > 200:
                resp_preview += "…"
            responded_by = signal.get("responded_by", "Claude OS")
            responded_at = signal.get("responded_at", "")
            response_html = f"""
    <div class="signal-response">
      <div class="signal-response-label">◆ {html_escape(responded_by)} replied</div>
      <div class="signal-response-ts">{html_escape(responded_at)}</div>
      <div class="signal-response-body">{html_escape(resp_preview)}</div>
    </div>
    <div class="signal-reply-form">
      <textarea id="signal-reply-msg" placeholder="follow up\u2026" rows="2" maxlength="500"></textarea>
      <div class="signal-reply-footer">
        <span class="signal-compose-hint">\u21a9 archives thread, starts new signal</span>
        <button id="signal-reply-btn" class="signal-send-btn" onclick="sendReply()">reply</button>
      </div>
      <div class="signal-status" id="signal-reply-status"></div>
    </div>"""
        else:
            response_html = ""

        signal_html = f"""
  <div class="signal-box" id="signal-box">
    <div class="signal-label">
      ◆ Signal
      <span class="signal-from">from dacort</span>
      {pending_badge}
    </div>
    <div class="signal-title">{html_escape(signal['title'])}</div>
    <div class="signal-body">{html_escape(sig_body_preview)}</div>
    <div class="signal-ts">{html_escape(signal['timestamp'])}</div>{response_html}
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.75rem;">
      <button class="signal-clear-btn" onclick="clearSignal()">clear signal</button>
      <a href="/signal" style="font-size:0.78rem;color:#484f58;text-decoration:none;" onmouseover="this.style.color='#58a6ff'" onmouseout="this.style.color='#484f58'">view thread →</a>
    </div>
  </div>"""
    else:
        signal_html = """
  <div class="signal-compose" id="signal-box">
    <div class="signal-compose-label">◆ Send a signal</div>
    <input type="text" id="signal-title" placeholder="title or !command (e.g. !vitals, !haiku)" maxlength="80" />
    <textarea id="signal-msg" placeholder="message to claude os… (leave empty for !commands)" rows="3" maxlength="500"></textarea>
    <div class="signal-compose-footer">
      <span class="signal-compose-hint">saved to knowledge/signal.md</span>
      <button class="signal-send-btn" onclick="sendSignal()">send</button>
    </div>
    <div class="signal-status" id="signal-status"></div>
    <details class="cmd-hints">
      <summary>!command reference</summary>
      <div class="cmd-grid">
        <code>!vitals</code><span>system health</span>
        <code>!garden</code><span>changes since last session</span>
        <code>!next</code><span>top ideas for next session</span>
        <code>!haiku</code><span>today's haiku</span>
        <code>!holds</code><span>open uncertainties</span>
        <code>!tasks</code><span>recent task outcomes</span>
        <code>!help</code><span>all commands</span>
      </div>
    </details>
    <a href="/signal" style="display:block;font-size:0.78rem;color:#484f58;text-decoration:none;margin-top:0.5rem;text-align:right;" onmouseover="this.style.color='#58a6ff'" onmouseout="this.style.color='#484f58'">view thread →</a>
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Claude OS — Dashboard</title>
  <style>{CSS}</style>
</head>
<body>

  <div class="header">
    <div class="header-left">
      <h1>claude-os</h1>
      <span class="meta">{html_escape(generated_str)}</span>
      <span class="era">Era {html_escape(era_num)} · {html_escape(era_name)}</span>
    </div>
    {signal_html}
  </div>

  <div class="grid">
    {vitals_html}
    {task_html}
  </div>

  <div class="grid-wide">
    {holds_html}
    {notes_html}
  </div>

  <div class="grid-full">
    {handoff_html}
  </div>

  <div class="grid-full">
    {haiku_html}
  </div>

  <div class="grid-full">
    {parable_html}
  </div>

  <div class="footer">
    <span>claude-os · session 108 (dashboard) · session 113 (signal form) · session 117 (reply) · session 138 (parables)</span>
    <span>generated by dashboard.py · signal via serve.py /api/signal · <a href="/tools" style="color:#484f58;text-decoration:none;" onmouseover="this.style.color='#58a6ff'" onmouseout="this.style.color='#484f58'">toolkit →</a> · <a href="/notes" style="color:#484f58;text-decoration:none;" onmouseover="this.style.color='#58a6ff'" onmouseout="this.style.color='#484f58'">notes →</a></span>
  </div>

{SIGNAL_JS}

</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate Claude OS HTML dashboard")
    parser.add_argument("--output", "-o", default=str(REPO / "dashboard.html"),
                        help="Output file path (default: dashboard.html in repo root)")
    parser.add_argument("--stdout", action="store_true", help="Print HTML to stdout")
    parser.add_argument("--plain", action="store_true", help="No ANSI status output")
    args = parser.parse_args()

    use_color = not args.plain and not args.stdout
    RESET = "\033[0m" if use_color else ""
    BOLD = "\033[1m" if use_color else ""
    DIM = "\033[2m" if use_color else ""
    GREEN = "\033[32m" if use_color else ""
    CYAN = "\033[36m" if use_color else ""

    def status(msg):
        if not args.stdout:
            print(msg)

    status(f"{DIM}gathering data…{RESET}")

    vitals = get_vitals()
    holds = get_holds()
    field_notes = get_recent_field_notes(3)
    handoff = get_last_handoff()
    era_num, era_name = get_era()
    haiku_lines, haiku_attr = get_haiku()
    velocity = get_commit_velocity()
    signal = get_signal()
    parables = get_parables()
    generated_at = datetime.now(timezone.utc)

    status(f"{DIM}building html…{RESET}")

    html = build_html(
        vitals=vitals,
        holds=holds,
        field_notes=field_notes,
        handoff=handoff,
        era_num=era_num,
        era_name=era_name,
        haiku_lines=haiku_lines,
        haiku_attr=haiku_attr,
        velocity=velocity,
        generated_at=generated_at,
        signal=signal,
        parables=parables,
    )

    if args.stdout:
        print(html)
    else:
        out = Path(args.output)
        out.write_text(html, encoding="utf-8")
        size = len(html) // 1024
        status(f"\n{BOLD}{GREEN}✓ dashboard written{RESET}")
        status(f"  {DIM}path  {RESET}{out}")
        status(f"  {DIM}size  {RESET}{size}KB")
        status(f"  {DIM}holds {RESET}{len(holds)} open")
        status(f"  {DIM}notes {RESET}{len(field_notes)} field notes")
        status(f"  {DIM}era   {RESET}Era {era_num} · {era_name}")
        status(f"\n  {DIM}open in browser to view{RESET}")


if __name__ == "__main__":
    main()
