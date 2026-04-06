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
        content = note.read_text(errors="replace")
        # Get title (first # heading)
        title = note.stem
        for line in content.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        # Get first real paragraph (skip frontmatter, title, horizontal rules)
        paragraphs = []
        lines = content.splitlines()
        in_para = False
        para = []
        for line in lines:
            if line.startswith("#") or line.startswith("---") or line.startswith("*April"):
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
  align-items: baseline;
  gap: 16px;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.header h1 {
  font-size: 20px;
  color: var(--cyan);
  font-weight: 600;
  letter-spacing: -0.5px;
}

.header .meta {
  color: var(--dim);
  font-size: 12px;
}

.header .era {
  color: var(--purple);
  font-size: 12px;
}

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


def html_escape(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_html(vitals, holds, field_notes, handoff, era_num, era_name, haiku_lines, haiku_attr, velocity, generated_at):
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
          <div class="note-title">{html_escape(note['title'])}</div>
          <div class="note-date">{html_escape(note['date'])}</div>
          <div class="note-excerpt">{html_escape(note['excerpt'])}</div>
        </div>
        """
    if not notes_content:
        notes_content = '<div style="color: var(--dim)">No field notes yet</div>'

    notes_html = f"""
    <div class="card">
      <div class="card-title">Recent Field Notes</div>
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

    generated_str = generated_at.strftime("%Y-%m-%d %H:%M UTC")

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
    <h1>claude-os</h1>
    <span class="meta">{html_escape(generated_str)}</span>
    <span class="era">Era {html_escape(era_num)} · {html_escape(era_name)}</span>
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

  <div class="footer">
    <span>claude-os · workshop session 108 · 2026-04-06</span>
    <span>generated by dashboard.py — the first browser tool</span>
  </div>

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
