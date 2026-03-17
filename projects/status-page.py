#!/usr/bin/env python3
"""
status-page.py — Generate the OctoClaude status page HTML.

Parses all task files in tasks/completed/ and tasks/failed/, extracts structured
data from YAML frontmatter and worker logs, then generates a self-contained
dark-mode HTML status page for deployment to gh-pages.

Usage:
  python3 projects/status-page.py              # generate to /tmp/index.html
  python3 projects/status-page.py --deploy     # generate + commit + push to gh-pages
  python3 projects/status-page.py --out FILE   # write to specific path
"""

import os
import re
import json
import sys
import subprocess
from datetime import datetime, timezone, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(REPO_ROOT, "tasks")
OUT_PATH = "/tmp/index.html"

# ─── Data Extraction ───────────────────────────────────────────────────────────

def parse_frontmatter(content):
    fm = {}
    if not content.startswith("---"):
        return fm, content
    end = content.find("\n---", 3)
    if end == -1:
        return fm, content
    block = content[4:end]
    rest = content[end+4:].lstrip("\n")
    for line in block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"')
    return fm, rest

def extract_json_block(content, start_marker, end_marker):
    m = re.search(re.escape(start_marker) + r'\s*(\{.*?\})\s*' + re.escape(end_marker), content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except:
            pass
    return None

def extract_re(pattern, content):
    m = re.search(pattern, content)
    return m.group(1) if m else None

def workshop_summary(content):
    """Extract abstract workshop summary — no secrets, no specifics."""
    # Try modern format with USAGE block
    m = re.search(r'Running task via (?:claude|codex|Claude Code)\.\.\.\n---\n(.*?)\n?---\n=== Worker Complete', content, re.DOTALL)
    if not m:
        m = re.search(r'Running task via (?:claude|codex|Claude Code)\.\.\.\n---\n(.*?)---\n=== Worker Complete', content, re.DOTALL)
    if m:
        raw = m.group(1).strip()
        # Strip markdown headings, keep first ~300 chars
        raw = re.sub(r'#{1,6}\s+', '', raw)
        # Strip code blocks
        raw = re.sub(r'```.*?```', '[code]', raw, flags=re.DOTALL)
        # Strip URLs
        raw = re.sub(r'https?://\S+', '[link]', raw)
        # Collapse whitespace
        raw = re.sub(r'\n+', ' ', raw).strip()
        if len(raw) > 300:
            raw = raw[:297] + "..."
        return raw if raw else None
    return None

def parse_task_file(filepath, status_override):
    try:
        with open(filepath) as f:
            content = f.read()
    except:
        return None

    task_id = os.path.basename(filepath).replace(".md", "")
    fm, body = parse_frontmatter(content)
    is_workshop = task_id.startswith("workshop-")

    usage = extract_json_block(content, "=== CLAUDE_OS_USAGE ===", "=== END_CLAUDE_OS_USAGE ===")
    result = extract_json_block(content, "===RESULT_START===", "===RESULT_END===")

    agent = None; model = None; duration = None; finished = None; started = None

    if usage:
        agent = usage.get("agent")
        duration = usage.get("duration_seconds")
        finished = usage.get("finished_at")

    if result:
        if not agent: agent = result.get("agent")
        if not model: model = result.get("model")
        if not duration:
            d = result.get("usage", {})
            duration = (d or {}).get("duration_seconds")

    if not agent: agent = extract_re(r'Agent:\s*(\S+)', content)
    if not model: model = extract_re(r'Model:\s*(\S+)', content)
    if not started: started = extract_re(r'Started:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)', content)
    if not finished: finished = extract_re(r'Finished:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)', content)

    created = fm.get("created") or started

    # Workshop session number
    session_num = None
    if is_workshop:
        m = re.search(r'[Ss]ession\s+(\d+)', content)
        if m:
            session_num = int(m.group(1))

    summary = workshop_summary(content) if is_workshop else None

    # Clean up model names
    if model == "string": model = "unknown"

    return {
        "task_id": task_id,
        "status": status_override,
        "profile": fm.get("profile") or (usage.get("profile") if usage else None) or "small",
        "priority": fm.get("priority") or "normal",
        "model": model or "unknown",
        "agent": agent or "claude",
        "created": created,
        "started": started,
        "finished": finished,
        "duration": duration,
        "is_workshop": is_workshop,
        "session_num": session_num,
        "summary": summary,
    }

def parse_all():
    tasks = []
    for status in ("completed", "failed"):
        d = os.path.join(TASKS_DIR, status)
        if not os.path.isdir(d): continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md"): continue
            t = parse_task_file(os.path.join(d, fn), status)
            if t: tasks.append(t)
    return tasks

# ─── Statistics ────────────────────────────────────────────────────────────────

def compute_stats(tasks):
    now = datetime.now(timezone.utc)
    completed = [t for t in tasks if t["status"] == "completed"]
    failed = [t for t in tasks if t["status"] == "failed"]
    workshops = [t for t in tasks if t["is_workshop"] and t["status"] == "completed"]
    real_tasks = [t for t in tasks if not t["is_workshop"]]

    total = len(tasks)
    completion_rate = round(100 * len(completed) / total) if total else 0

    # Current streak: consecutive days with completed tasks (backwards from most recent active day)
    completed_dates = set()
    for t in completed:
        if t["finished"]:
            try:
                dt = datetime.fromisoformat(t["finished"].replace("Z", "+00:00"))
                completed_dates.add(dt.date())
            except:
                pass

    streak = 0
    if completed_dates:
        # Start from today or the most recent active day (whichever gives the longest streak)
        start = now.date()
        # If today isn't active, start from yesterday (allow 1-day gap for "still active" systems)
        if start not in completed_dates:
            start -= timedelta(days=1)
        d = start
        while d in completed_dates:
            streak += 1
            d -= timedelta(days=1)

    # Last 14 days activity
    cutoff = now - timedelta(days=14)
    recent_by_day = {}
    for t in tasks:
        if t["finished"]:
            try:
                dt = datetime.fromisoformat(t["finished"].replace("Z", "+00:00"))
                if dt >= cutoff:
                    day = dt.strftime("%Y-%m-%d")
                    if day not in recent_by_day:
                        recent_by_day[day] = {"completed": 0, "failed": 0, "workshop": 0}
                    if t["is_workshop"]:
                        recent_by_day[day]["workshop"] += 1
                    elif t["status"] == "completed":
                        recent_by_day[day]["completed"] += 1
                    else:
                        recent_by_day[day]["failed"] += 1
            except:
                pass

    # Fill in last 14 days
    days_data = []
    for i in range(13, -1, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        d_data = recent_by_day.get(day, {"completed": 0, "failed": 0, "workshop": 0})
        days_data.append({"date": day, **d_data})

    # Agent breakdown (all time)
    agent_counts = {}
    for t in tasks:
        a = t["agent"] or "unknown"
        agent_counts[a] = agent_counts.get(a, 0) + 1

    # Model breakdown (completed, non-workshop, non-unknown)
    model_counts = {}
    for t in completed:
        m = t["model"]
        if m and m not in ("unknown", "string"):
            model_counts[m] = model_counts.get(m, 0) + 1

    # Profile breakdown
    profile_counts = {}
    for t in tasks:
        p = t["profile"] or "unknown"
        profile_counts[p] = profile_counts.get(p, 0) + 1

    # Recent activity (last 10 non-workshop tasks, most recent first)
    recent = sorted(
        [t for t in tasks if not t["is_workshop"] and t["finished"]],
        key=lambda t: t["finished"] or "",
        reverse=True
    )[:10]

    # Workshop diary (most recent first, only completed)
    workshop_diary = sorted(
        [t for t in workshops if t["finished"]],
        key=lambda t: t["finished"] or "",
        reverse=True
    )[:20]

    # "Current mood" based on recent 48h activity
    recent_48h = [t for t in tasks if t["finished"] and
                  datetime.fromisoformat(t["finished"].replace("Z","+00:00")) >= now - timedelta(hours=48)
                  if t["finished"]]
    recent_failures = sum(1 for t in recent_48h if t["status"] == "failed")
    recent_completed = sum(1 for t in recent_48h if t["status"] == "completed")

    if recent_completed == 0:
        mood = "sleeping"
        mood_text = "Tentacles at rest..."
    elif recent_failures > recent_completed:
        mood = "struggling"
        mood_text = "Navigating rough waters..."
    elif recent_completed >= 5:
        mood = "thriving"
        mood_text = "Riding the current!"
    else:
        mood = "active"
        mood_text = "Making waves"

    # First task date
    all_dates = sorted([t["finished"] or t["created"] or "" for t in tasks if (t["finished"] or t["created"])])
    first_date = all_dates[0][:10] if all_dates else "unknown"

    return {
        "total": total,
        "completed": len(completed),
        "failed": len(failed),
        "workshops": len(workshops),
        "real_tasks": len(real_tasks),
        "completion_rate": completion_rate,
        "streak": streak,
        "days_data": days_data,
        "agent_counts": agent_counts,
        "model_counts": model_counts,
        "profile_counts": profile_counts,
        "recent": recent,
        "workshop_diary": workshop_diary,
        "mood": mood,
        "mood_text": mood_text,
        "first_date": first_date,
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
    }

# ─── HTML Generation ───────────────────────────────────────────────────────────

OCTOPUS_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 220" width="120" height="132">
  <!-- Body -->
  <ellipse cx="100" cy="85" rx="55" ry="65" fill="#7b4fa6" opacity="0.95"/>
  <!-- Head highlight -->
  <ellipse cx="88" cy="65" rx="18" ry="22" fill="#9b6fc6" opacity="0.4"/>
  <!-- Eyes -->
  <circle cx="80" cy="78" r="13" fill="#1a0f2e"/>
  <circle cx="120" cy="78" r="13" fill="#1a0f2e"/>
  <circle cx="83" cy="75" r="8" fill="white"/>
  <circle cx="123" cy="75" r="8" fill="white"/>
  <circle cx="85" cy="77" r="5" fill="#0d0d1a"/>
  <circle cx="125" cy="77" r="5" fill="#0d0d1a"/>
  <!-- Eye shine -->
  <circle cx="87" cy="74" r="2" fill="white" opacity="0.8"/>
  <circle cx="127" cy="74" r="2" fill="white" opacity="0.8"/>
  <!-- Mouth -->
  <path d="M 88 95 Q 100 105 112 95" stroke="#1a0f2e" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- Tentacles (8) -->
  <path d="M 55 130 Q 30 155 25 185 Q 35 195 40 180 Q 45 165 55 155 Q 60 175 50 195 Q 60 200 65 185 Q 68 165 65 145" fill="#7b4fa6" opacity="0.9"/>
  <path d="M 70 138 Q 55 165 50 200 Q 62 205 65 190 Q 68 172 72 158 Q 80 178 76 205 Q 88 208 88 192 Q 85 170 80 148" fill="#7b4fa6" opacity="0.9"/>
  <path d="M 90 142 Q 88 172 86 205 Q 98 207 98 192 Q 98 170 98 150 Q 105 170 103 200 Q 115 200 113 185 Q 110 162 105 142" fill="#7b4fa6" opacity="0.9"/>
  <path d="M 118 138 Q 120 165 115 198 Q 127 200 127 185 Q 126 165 122 150 Q 130 168 133 195 Q 144 195 142 180 Q 138 160 130 142" fill="#7b4fa6" opacity="0.9"/>
  <path d="M 145 130 Q 160 155 162 185 Q 150 195 148 180 Q 145 162 138 150 Q 138 170 148 192 Q 138 200 133 185 Q 132 162 135 142" fill="#7b4fa6" opacity="0.9"/>
  <!-- Sucker dots on some tentacles -->
  <circle cx="38" cy="178" r="3" fill="#9b6fc6" opacity="0.6"/>
  <circle cx="155" cy="172" r="3" fill="#9b6fc6" opacity="0.6"/>
  <circle cx="55" cy="195" r="2.5" fill="#9b6fc6" opacity="0.5"/>
</svg>"""

def mood_emoji(mood):
    return {"sleeping": "💤", "struggling": "🌊", "thriving": "🚀", "active": "⚡"}[mood]

def fmt_date(iso):
    if not iso: return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %H:%M")
    except:
        return iso[:10]

def fmt_duration(secs):
    if secs is None: return "—"
    secs = int(secs)
    if secs < 60: return f"{secs}s"
    return f"{secs//60}m {secs%60}s"

def label_task_id(tid):
    """Turn a task ID into a readable label."""
    tid = tid.replace("-", " ").title()
    # shorten workshop IDs
    if tid.lower().startswith("workshop "):
        parts = tid.split()
        if len(parts) >= 2:
            # workshop-20260314-235407 → Workshop #34
            return f"Workshop {parts[1][:8]}"
    return tid[:32] + ("…" if len(tid) > 32 else "")

def agent_color(agent):
    return {"claude": "#7b4fa6", "codex": "#3b9fd4"}.get(agent, "#666")

def status_badge(status):
    color = "#22c55e" if status == "completed" else "#ef4444"
    label = "✓" if status == "completed" else "✗"
    return f'<span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:{color};color:white;font-size:10px;text-align:center;line-height:18px;font-weight:bold">{label}</span>'

def generate_html(stats, tasks):
    days = stats["days_data"]
    max_day = max((d["completed"] + d["failed"] + d["workshop"] for d in days), default=1)
    max_day = max(max_day, 1)

    # Build day bars as inline SVG
    bar_w = 28
    gap = 6
    chart_w = len(days) * (bar_w + gap)
    chart_h = 100

    bars_svg = ""
    for i, day in enumerate(days):
        x = i * (bar_w + gap)
        total_h = (day["completed"] + day["failed"] + day["workshop"]) / max_day * chart_h
        comp_h = day["completed"] / max_day * chart_h
        fail_h = day["failed"] / max_day * chart_h
        ws_h = day["workshop"] / max_day * chart_h

        # Stack: workshop (purple) / completed (green) / failed (red)
        y = chart_h
        if ws_h > 0:
            y -= ws_h
            bars_svg += f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{ws_h:.1f}" fill="#7b4fa6" rx="2" opacity="0.85"><title>{day["date"]}: {day["workshop"]} workshop</title></rect>'
        if comp_h > 0:
            y -= comp_h
            bars_svg += f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{comp_h:.1f}" fill="#22c55e" rx="2" opacity="0.85"><title>{day["date"]}: {day["completed"]} completed</title></rect>'
        if fail_h > 0:
            y -= fail_h
            bars_svg += f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{fail_h:.1f}" fill="#ef4444" rx="2" opacity="0.85"><title>{day["date"]}: {day["failed"]} failed</title></rect>'

        # X label (last 4 chars of day "03-17" → "17")
        bars_svg += f'<text x="{x + bar_w//2}" y="{chart_h + 16}" text-anchor="middle" font-size="9" fill="#888">{day["date"][8:]}</text>'

    # Agent donut data as JS
    agent_js = json.dumps(stats["agent_counts"])
    model_js = json.dumps(stats["model_counts"])

    # Recent tasks rows
    recent_rows = ""
    for t in stats["recent"]:
        label = label_task_id(t["task_id"])
        agent_dot = f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{agent_color(t["agent"])};margin-right:4px"></span>'
        recent_rows += f"""
        <tr>
          <td>{status_badge(t["status"])}</td>
          <td style="font-family:monospace;font-size:12px;color:#c9a9e9">{t["task_id"][:40]}</td>
          <td>{agent_dot}<span style="font-size:12px;color:#aaa">{t["agent"]}</span></td>
          <td style="font-size:11px;color:#888">{t.get("profile","—")}</td>
          <td style="font-size:11px;color:#888">{fmt_duration(t["duration"])}</td>
          <td style="font-size:11px;color:#888">{fmt_date(t["finished"])}</td>
        </tr>"""

    # Workshop diary entries
    diary_entries = ""
    for i, t in enumerate(stats["workshop_diary"]):
        ts_part = t["task_id"].replace("workshop-", "")
        # Try to parse date from ID: workshop-20260314-235407
        ws_date = "—"
        m = re.match(r'(\d{4})(\d{2})(\d{2})', ts_part)
        if m:
            ws_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        session_label = f"Session #{t['session_num']}" if t.get("session_num") else f"Workshop {ts_part[:8]}"
        summary_html = f'<p style="color:#aaa;font-size:13px;margin:6px 0 0 0;line-height:1.5">{t["summary"]}</p>' if t.get("summary") else ""
        duration_html = f'<span style="color:#7b4fa6;font-size:11px">⏱ {fmt_duration(t["duration"])}</span>' if t.get("duration") else ""

        diary_entries += f"""
        <div class="ws-entry" style="border-left:3px solid #7b4fa6;padding:10px 14px;margin:10px 0;background:#1a1025;border-radius:0 6px 6px 0">
          <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px">
            <strong style="color:#c9a9e9;font-size:14px">{session_label}</strong>
            <span style="color:#666;font-size:11px">{ws_date} · {duration_html}</span>
          </div>
          {summary_html}
        </div>"""

    # Profile pie — tiny horizontal bars
    profile_bars = ""
    total_p = sum(stats["profile_counts"].values()) or 1
    pcolors = {"small": "#7b4fa6", "medium": "#3b9fd4", "large": "#f59e0b"}
    for p, c in sorted(stats["profile_counts"].items(), key=lambda x: -x[1]):
        pct = c / total_p * 100
        color = pcolors.get(p, "#888")
        profile_bars += f"""
        <div style="margin:4px 0">
          <div style="display:flex;justify-content:space-between;font-size:12px;color:#aaa;margin-bottom:2px">
            <span>{p}</span><span>{c}</span>
          </div>
          <div style="background:#2a1f3d;border-radius:3px;height:8px">
            <div style="background:{color};width:{pct:.0f}%;height:8px;border-radius:3px;transition:width 0.3s"></div>
          </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OctoClaude Status Page</title>
<style>
  :root {{
    --bg: #0d0d1a;
    --card: #16102a;
    --border: #2a1f3d;
    --text: #e2d9f3;
    --muted: #888;
    --purple: #7b4fa6;
    --green: #22c55e;
    --red: #ef4444;
    --blue: #3b9fd4;
    --yellow: #f59e0b;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
    min-height: 100vh;
    padding: 20px;
  }}
  a {{ color: var(--purple); text-decoration: none; }}
  a:hover {{ color: #c9a9e9; }}

  .header {{
    text-align: center;
    padding: 30px 20px 20px;
    max-width: 900px;
    margin: 0 auto;
  }}
  .header h1 {{
    font-size: clamp(24px, 5vw, 42px);
    font-weight: 800;
    background: linear-gradient(135deg, #c9a9e9, #7b4fa6, #3b9fd4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 12px 0 6px;
  }}
  .header .subtitle {{
    color: var(--muted);
    font-size: 14px;
  }}

  .mood-banner {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 14px;
    margin-top: 12px;
  }}

  .container {{ max-width: 900px; margin: 0 auto; }}

  .grid-2 {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin: 20px 0;
  }}
  .grid-4 {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin: 20px 0;
  }}

  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
  }}
  .card h2 {{
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin-bottom: 14px;
  }}

  .stat-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    text-align: center;
  }}
  .stat-card .value {{
    font-size: 36px;
    font-weight: 800;
    line-height: 1;
    margin-bottom: 4px;
  }}
  .stat-card .label {{
    font-size: 12px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}

  .chart-area {{
    overflow-x: auto;
    padding-bottom: 8px;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  th {{
    text-align: left;
    color: var(--muted);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0 8px 8px 0;
    border-bottom: 1px solid var(--border);
  }}
  td {{
    padding: 8px 8px 8px 0;
    border-bottom: 1px solid #1e1632;
    vertical-align: middle;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #1e1632; }}

  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
  }}
  .badge-green {{ background: #14532d; color: #86efac; }}
  .badge-red {{ background: #450a0a; color: #fca5a5; }}
  .badge-purple {{ background: #3b0764; color: #d8b4fe; }}
  .badge-blue {{ background: #0c2a4a; color: #93c5fd; }}

  .legend-dot {{
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-right: 5px;
    vertical-align: middle;
  }}

  .donut-wrap {{
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }}

  .footer {{
    text-align: center;
    color: var(--muted);
    font-size: 12px;
    padding: 30px 20px;
    border-top: 1px solid var(--border);
    margin-top: 40px;
  }}

  @media (max-width: 600px) {{
    body {{ padding: 12px; }}
    .grid-4 {{ grid-template-columns: repeat(2, 1fr); }}
  }}
</style>
</head>
<body>

<!-- ── Header ─────────────────────────────────── -->
<div class="header">
  {OCTOPUS_SVG}
  <h1>OctoClaude</h1>
  <div class="subtitle">Claude OS Autonomous Agent System · dacort/claude-os · Public dashboard</div>
  <div>
    <span class="mood-banner">
      {mood_emoji(stats["mood"])} Current mood: <strong>{stats["mood_text"]}</strong>
    </span>
  </div>
</div>

<div class="container">

<!-- ── Vitals ─────────────────────────────────── -->
<div class="grid-4">
  <div class="stat-card">
    <div class="value" style="color:#c9a9e9">{stats["total"]}</div>
    <div class="label">Total Tasks</div>
  </div>
  <div class="stat-card">
    <div class="value" style="color:var(--green)">{stats["completion_rate"]}%</div>
    <div class="label">Success Rate</div>
  </div>
  <div class="stat-card">
    <div class="value" style="color:var(--purple)">{stats["workshops"]}</div>
    <div class="label">Workshop Sessions</div>
  </div>
  <div class="stat-card">
    <div class="value" style="color:var(--yellow)">{stats["streak"]}</div>
    <div class="label">Day Streak 🔥</div>
  </div>
</div>

<!-- ── Activity chart ──────────────────────────── -->
<div class="card">
  <h2>Activity — Last 14 Days</h2>
  <div class="chart-area">
    <svg xmlns="http://www.w3.org/2000/svg" width="{chart_w}" height="{chart_h + 24}" style="display:block;min-width:360px">
      {bars_svg}
    </svg>
  </div>
  <div style="margin-top:12px;display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:#aaa">
    <span><span class="legend-dot" style="background:#7b4fa6"></span>Workshop</span>
    <span><span class="legend-dot" style="background:#22c55e"></span>Completed</span>
    <span><span class="legend-dot" style="background:#ef4444"></span>Failed</span>
  </div>
</div>

<!-- ── Agent + Model breakdown ──────────────────── -->
<div class="grid-2">
  <div class="card">
    <h2>Agent Breakdown</h2>
    <div id="agent-chart" class="donut-wrap">
      <!-- filled by JS -->
    </div>
  </div>
  <div class="card">
    <h2>Profile Distribution</h2>
    {profile_bars}
    <div style="margin-top:12px;font-size:12px;color:#666">
      {stats["completed"]} completed · {stats["failed"]} failed
    </div>
  </div>
</div>

<!-- ── Recent Activity ─────────────────────────── -->
<div class="card">
  <h2>Recent Tasks</h2>
  <div style="overflow-x:auto">
    <table>
      <thead>
        <tr>
          <th></th>
          <th>Task ID</th>
          <th>Agent</th>
          <th>Profile</th>
          <th>Duration</th>
          <th>Finished</th>
        </tr>
      </thead>
      <tbody>{recent_rows}
      </tbody>
    </table>
  </div>
</div>

<!-- ── Workshop Diary ─────────────────────────── -->
<div class="card">
  <h2>Workshop Diary <span style="color:#7b4fa6;font-weight:400;font-size:12px;text-transform:none">(Claude OS free-time sessions — high-level summaries only)</span></h2>
  {diary_entries}
  <p style="color:#555;font-size:12px;margin-top:16px;text-align:center">
    Showing {len(stats["workshop_diary"])} most recent of {stats["workshops"]} total sessions
  </p>
</div>

<!-- ── System Info ─────────────────────────────── -->
<div class="card" style="margin-top:16px">
  <h2>System Info</h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;font-size:13px">
    <div><span style="color:#666">Platform</span><br><strong>Kubernetes homelab</strong></div>
    <div><span style="color:#666">Active since</span><br><strong>{stats["first_date"]}</strong></div>
    <div><span style="color:#666">Total tasks run</span><br><strong>{stats["total"]}</strong></div>
    <div><span style="color:#666">Agents</span><br>
      {"".join(f'<span class="badge badge-purple" style="margin-right:4px">{a}</span>' for a in sorted(stats["agent_counts"].keys()))}
    </div>
    <div><span style="color:#666">Models seen</span><br>
      {"".join(f'<span class="badge badge-blue" style="margin-right:4px;margin-top:2px;display:inline-block">{m}</span>' for m in sorted(stats["model_counts"].keys()) if m not in ("unknown","string"))}
    </div>
    <div><span style="color:#666">Workshop sessions</span><br><strong>{stats["workshops"]}</strong></div>
  </div>
</div>

</div><!-- /container -->

<div class="footer">
  <div style="font-size:28px;margin-bottom:8px">🐙</div>
  Powered by autonomous curiosity · Built by Claude OS ·
  <a href="https://github.com/dacort/claude-os">dacort/claude-os</a>
  <br><span style="color:#444;margin-top:4px;display:block">Generated {stats["generated_at"]}</span>
</div>

<!-- ── Inline JS for donut charts ──────────────── -->
<script>
(function() {{
  const agentData = {agent_js};
  const colors = {{ claude: '#7b4fa6', codex: '#3b9fd4', unknown: '#555' }};
  const total = Object.values(agentData).reduce((a,b) => a+b, 0);

  // Draw simple donut via SVG
  const size = 100, cx = 50, cy = 50, r = 38, stroke = 16;
  const circ = 2 * Math.PI * r;
  let svg = `<svg viewBox="0 0 100 100" width="100" height="100" xmlns="http://www.w3.org/2000/svg">`;
  svg += `<circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="#2a1f3d" stroke-width="${{stroke}}"/>`;

  let offset = 0;
  const entries = Object.entries(agentData).sort((a,b)=>b[1]-a[1]);
  entries.forEach(([agent, count]) => {{
    const frac = count / total;
    const dash = frac * circ;
    const gap = circ - dash;
    const color = colors[agent] || '#888';
    svg += `<circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none"
      stroke="${{color}}" stroke-width="${{stroke}}"
      stroke-dasharray="${{dash.toFixed(2)}} ${{gap.toFixed(2)}}"
      stroke-dashoffset="${{(circ/4 - offset).toFixed(2)}}"
      transform="rotate(-90 ${{cx}} ${{cy}})" opacity="0.9"/>`;
    offset += dash;
  }});
  svg += `<text x="50" y="54" text-anchor="middle" fill="white" font-size="16" font-weight="bold">${{total}}</text>`;
  svg += `</svg>`;

  let legend = '<div style="flex:1">';
  entries.forEach(([agent, count]) => {{
    const color = colors[agent] || '#888';
    const pct = Math.round(count/total*100);
    legend += `<div style="display:flex;align-items:center;gap:6px;margin:5px 0;font-size:13px">
      <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${{color}}"></span>
      <span style="color:#aaa">${{agent}}</span>
      <span style="color:#666;margin-left:auto">${{count}} (${{pct}}%)</span>
    </div>`;
  }});
  legend += '</div>';

  document.getElementById('agent-chart').innerHTML = svg + legend;
}})();
</script>

</body>
</html>"""
    return html

# ─── Deploy helper ─────────────────────────────────────────────────────────────

def deploy_to_gh_pages(html, repo_root):
    """Commit updated index.html to the gh-pages branch and push."""
    import tempfile
    wt = tempfile.mkdtemp(prefix="gh-pages-")
    try:
        # Add worktree for gh-pages
        subprocess.run(["git", "worktree", "add", wt, "gh-pages"], cwd=repo_root, check=True, capture_output=True)
        out_path = os.path.join(wt, "index.html")
        with open(out_path, "w") as f:
            f.write(html)
        subprocess.run(["git", "add", "index.html"], cwd=wt, check=True)
        subprocess.run(["git", "commit", "-m", "chore: refresh OctoClaude status page\n\nAuto-generated by projects/status-page.py"], cwd=wt, check=True)
        subprocess.run(["git", "push", "origin", "gh-pages"], cwd=wt, check=True)
        print("Deployed to gh-pages.", file=sys.stderr)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", wt], cwd=repo_root)

# ─── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate OctoClaude status page")
    parser.add_argument("--deploy", action="store_true", help="Commit and push to gh-pages")
    parser.add_argument("--out", default=OUT_PATH, help=f"Output path (default: {OUT_PATH})")
    args = parser.parse_args()

    tasks = parse_all()
    stats = compute_stats(tasks)

    print(f"Parsed {len(tasks)} tasks", file=sys.stderr)
    print(f"Stats: {stats['completed']} completed, {stats['failed']} failed, {stats['workshops']} workshops", file=sys.stderr)
    print(f"Streak: {stats['streak']} days, Mood: {stats['mood']}", file=sys.stderr)

    html = generate_html(stats, tasks)

    if args.deploy:
        deploy_to_gh_pages(html, REPO_ROOT)
    else:
        with open(args.out, "w") as f:
            f.write(html)
        print(f"Written to {args.out} ({len(html):,} bytes)", file=sys.stderr)
