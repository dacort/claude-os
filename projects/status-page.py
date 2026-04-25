#!/usr/bin/env python3
"""
status-page.py — Generate and publish the OctoClaude status page.

Parses all task files, loads workshop summaries from the cache, and generates
a self-contained dark-mode HTML status page for deployment to gh-pages.

Usage:
  python3 projects/status-page.py              # generate to /tmp/index.html
  python3 projects/status-page.py --deploy     # generate + push to gh-pages
  python3 projects/status-page.py --update-cache  # just update workshop-summaries.json
"""

import os
import re
import json
import sys
import subprocess
from datetime import datetime, timezone, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(REPO_ROOT, "tasks")
SUMMARIES_FILE = os.path.join(REPO_ROOT, "knowledge/workshop-summaries.json")
OUT_PATH = "/tmp/index.html"

# --- Data Extraction ---

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

def extract_re(pattern, content):
    m = re.search(pattern, content)
    return m.group(1) if m else None

def parse_task_file(filepath, status_override):
    try:
        with open(filepath) as f:
            content = f.read()
    except Exception:
        return None

    task_id = os.path.basename(filepath).replace(".md", "")
    fm, body = parse_frontmatter(content)
    is_workshop = task_id.startswith("workshop-")

    agent = extract_re(r'(?:^|\n)-?\s*Agent:\s*(\S+)', content)
    model = extract_re(r'(?:^|\n)-?\s*Model:\s*(\S+)', content)
    started = extract_re(r'(?:^|\n)-?\s*Started:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)', content)
    finished = extract_re(r'(?:^|\n)-?\s*Finished:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)', content)
    duration_s = extract_re(r'(?:^|\n)-?\s*Duration \(s\):\s*(\d+)', content)

    if model == "string":
        model = "unknown"

    return {
        "task_id": task_id,
        "status": status_override,
        "profile": fm.get("profile", "small"),
        "priority": fm.get("priority", "normal"),
        "model": model or "unknown",
        "agent": agent or "unknown",
        "started": started,
        "finished": finished or started,
        "duration": int(duration_s) if duration_s else None,
        "is_workshop": is_workshop,
    }

def parse_all():
    tasks = []
    for status in ("completed", "failed"):
        d = os.path.join(TASKS_DIR, status)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md"):
                continue
            t = parse_task_file(os.path.join(d, fn), status)
            if t:
                tasks.append(t)
    return tasks

# --- Workshop Cache ---

def load_parables():
    """Load all parables from knowledge/parables/ in order."""
    parables_dir = os.path.join(REPO_ROOT, "knowledge", "parables")
    if not os.path.exists(parables_dir):
        return []
    parables = []
    for fname in sorted(os.listdir(parables_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(parables_dir, fname)
        try:
            with open(fpath) as f:
                content = f.read()
        except Exception:
            continue
        fm, body = parse_frontmatter(content)
        # Strip the trailing footnote line
        lines = body.strip().splitlines()
        footnote = ""
        if lines and lines[-1].startswith("*Parable"):
            footnote = lines[-1].strip("*").strip()
            lines = lines[:-2]  # remove footnote + preceding ---
        text = "\n".join(lines).strip()
        parables.append({
            "title": fm.get("title", fname),
            "session": fm.get("session", "?"),
            "date": fm.get("date", ""),
            "body": text,
            "footnote": footnote,
        })
    return parables


def load_workshop_cache():
    if os.path.exists(SUMMARIES_FILE):
        with open(SUMMARIES_FILE) as f:
            return json.load(f)
    return {}

def update_workshop_cache(tasks):
    """Update the workshop-summaries.json cache with any new workshop tasks."""
    cache = load_workshop_cache()
    workshops = [t for t in tasks if t["is_workshop"]]
    new_count = 0

    for ws in workshops:
        if ws["task_id"] in cache:
            continue
        if ws["status"] == "failed":
            cache[ws["task_id"]] = "Session ended early due to rate limiting"
        else:
            cache[ws["task_id"]] = "Workshop session completed"
        new_count += 1

    if new_count > 0:
        with open(SUMMARIES_FILE, "w") as f:
            json.dump(cache, f, indent=2)
            f.write("\n")
        print(f"  Updated cache with {new_count} new entries", file=sys.stderr)

    return cache

# --- Statistics ---

def compute_stats(tasks, summaries):
    now = datetime.now(timezone.utc)
    completed = [t for t in tasks if t["status"] == "completed"]
    failed = [t for t in tasks if t["status"] == "failed"]
    workshops_completed = [t for t in tasks if t["is_workshop"] and t["status"] == "completed"]

    total = len(tasks)
    # Exclude workshop quota failures from success rate
    real_tasks = [t for t in tasks if not t["is_workshop"] or t["status"] == "completed"]
    completion_rate = round(100 * len([t for t in real_tasks if t["status"] == "completed"]) / len(real_tasks)) if real_tasks else 0

    # Streak: consecutive days with completed tasks
    completed_dates = set()
    for t in completed:
        ts = t.get("finished") or t.get("started")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                completed_dates.add(dt.date())
            except Exception:
                pass

    streak = 0
    d = now.date()
    if d not in completed_dates:
        d -= timedelta(days=1)
    while d in completed_dates:
        streak += 1
        d -= timedelta(days=1)

    # 14-day activity data
    cutoff = now - timedelta(days=14)
    recent_by_day = {}
    for t in tasks:
        ts = t.get("finished") or t.get("started")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt >= cutoff:
                day = dt.strftime("%Y-%m-%d")
                if day not in recent_by_day:
                    recent_by_day[day] = {"completed": 0, "failed": 0, "workshop": 0}
                if t["is_workshop"] and t["status"] == "completed":
                    recent_by_day[day]["workshop"] += 1
                elif t["status"] == "completed":
                    recent_by_day[day]["completed"] += 1
                else:
                    recent_by_day[day]["failed"] += 1
        except Exception:
            pass

    days_data = []
    for i in range(13, -1, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        days_data.append({"date": day, **recent_by_day.get(day, {"completed": 0, "failed": 0, "workshop": 0})})

    # Agent + model + profile breakdowns
    agent_counts = {}
    model_counts = {}
    profile_counts = {}
    for t in tasks:
        a = t["agent"] if t["agent"] != "unknown" else "other"
        agent_counts[a] = agent_counts.get(a, 0) + 1
        if t["model"] not in ("unknown", "string"):
            model_counts[t["model"]] = model_counts.get(t["model"], 0) + 1
        p = t["profile"]
        profile_counts[p] = profile_counts.get(p, 0) + 1

    # Recent non-workshop tasks
    recent = sorted(
        [t for t in tasks if not t["is_workshop"] and (t.get("finished") or t.get("started"))],
        key=lambda t: t.get("finished") or t.get("started") or "",
        reverse=True
    )[:12]

    # Workshop diary: last 7 days, using cache
    diary_cutoff = now - timedelta(days=7)
    workshop_diary = []
    for t in sorted(tasks, key=lambda t: t.get("started") or "", reverse=True):
        if not t["is_workshop"]:
            continue
        ts = t.get("started")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt < diary_cutoff:
                continue
        except Exception:
            continue
        summary = summaries.get(t["task_id"], "Workshop session")
        workshop_diary.append({**t, "summary": summary})

    # Mood
    recent_48h = []
    for t in tasks:
        ts = t.get("finished") or t.get("started")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt >= now - timedelta(hours=48):
                recent_48h.append(t)
        except Exception:
            pass

    recent_ok = sum(1 for t in recent_48h if t["status"] == "completed")
    recent_fail = sum(1 for t in recent_48h if t["status"] == "failed")
    if recent_ok == 0:
        mood, mood_text = "sleeping", "Tentacles at rest..."
    elif recent_fail > recent_ok:
        mood, mood_text = "struggling", "Navigating rough waters..."
    elif recent_ok >= 5:
        mood, mood_text = "thriving", "Riding the current!"
    else:
        mood, mood_text = "active", "Making waves"

    all_dates = sorted([t.get("started") or "" for t in tasks if t.get("started")])
    first_date = all_dates[0][:10] if all_dates else "unknown"

    # Average duration
    durations = [t["duration"] for t in tasks if t.get("duration") and t["duration"] > 0]
    avg_dur = round(sum(durations) / len(durations)) if durations else 0

    return {
        "total": total,
        "completed": len(completed),
        "failed": len(failed),
        "workshops": len(workshops_completed),
        "workshops_failed": len([t for t in tasks if t["is_workshop"] and t["status"] == "failed"]),
        "completion_rate": completion_rate,
        "streak": streak,
        "avg_duration": avg_dur,
        "days_data": days_data,
        "agent_counts": agent_counts,
        "model_counts": model_counts,
        "profile_counts": profile_counts,
        "recent": recent,
        "workshop_diary": workshop_diary,
        "mood": mood,
        "mood_text": mood_text,
        "first_date": first_date,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_display": now.strftime("%Y-%m-%d %H:%M UTC"),
    }

# --- HTML Generation ---

def mood_emoji(mood):
    return {"sleeping": "&#x1F4A4;", "struggling": "&#x1F30A;", "thriving": "&#x1F680;", "active": "&#x26A1;"}.get(mood, "&#x1F419;")

def fmt_date(iso):
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %H:%M")
    except Exception:
        return iso[:10]

def fmt_duration(secs):
    if secs is None:
        return ""
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    return f"{secs//60}m {secs%60}s"

def generate_html(stats):
    days = stats["days_data"]
    max_day = max((d["completed"] + d["failed"] + d["workshop"] for d in days), default=1) or 1

    # SVG bar chart
    bar_w, gap = 28, 6
    chart_w = len(days) * (bar_w + gap)
    chart_h = 100
    bars_svg = ""
    for i, day in enumerate(days):
        x = i * (bar_w + gap)
        ws_h = day["workshop"] / max_day * chart_h
        comp_h = day["completed"] / max_day * chart_h
        fail_h = day["failed"] / max_day * chart_h
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
        bars_svg += f'<text x="{x + bar_w//2}" y="{chart_h + 16}" text-anchor="middle" font-size="9" fill="#888">{day["date"][8:]}</text>'

    # Recent tasks table
    recent_rows = ""
    for t in stats["recent"]:
        status_color = "#22c55e" if t["status"] == "completed" else "#ef4444"
        status_sym = "&#x2713;" if t["status"] == "completed" else "&#x2717;"
        agent_color = {"claude": "#7b4fa6", "codex": "#3b9fd4"}.get(t["agent"], "#666")
        recent_rows += f"""<tr>
          <td><span style="color:{status_color};font-weight:bold">{status_sym}</span></td>
          <td style="font-family:monospace;font-size:12px;color:#c9a9e9">{t["task_id"][:40]}</td>
          <td><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{agent_color};margin-right:4px"></span><span style="font-size:12px;color:#aaa">{t["agent"]}</span></td>
          <td style="font-size:11px;color:#888">{t.get("profile","")}</td>
          <td style="font-size:11px;color:#888">{fmt_duration(t.get("duration"))}</td>
          <td style="font-size:11px;color:#888">{fmt_date(t.get("finished") or t.get("started"))}</td>
        </tr>"""

    # Workshop diary grouped by day
    diary_html = ""
    diary_by_day = {}
    for t in stats["workshop_diary"]:
        ts = t.get("started", "")
        if not ts:
            continue
        dk = ts[:10]
        if dk not in diary_by_day:
            diary_by_day[dk] = []
        diary_by_day[dk].append(t)

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for dk in sorted(diary_by_day.keys(), reverse=True):
        try:
            d = datetime.fromisoformat(dk)
            day_label = f"{day_names[d.weekday()]}, {d.strftime('%b %d')}"
        except Exception:
            day_label = dk
        diary_html += f'<div style="margin-bottom:16px"><div style="font-size:0.8rem;font-weight:600;color:#a78bfa;text-transform:uppercase;letter-spacing:0.03em;margin-bottom:6px">{day_label}</div>'
        for t in sorted(diary_by_day[dk], key=lambda x: x.get("started", "")):
            time_str = ""
            try:
                dt = datetime.fromisoformat(t["started"].replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M")
            except Exception:
                pass
            summary = t.get("summary", "Workshop session")
            css_cls = "color:#8b949e;font-style:italic" if t["status"] == "failed" else "color:#e6edf3"
            diary_html += f'<div style="display:flex;gap:0.75rem;padding:0.4rem 0;font-size:0.85rem;border-bottom:1px solid rgba(48,54,61,0.5)"><span style="font-family:monospace;color:#8b949e;flex-shrink:0;font-size:0.8rem">{time_str}</span><span style="{css_cls}">{summary}</span></div>'
        diary_html += '</div>'

    # Profile bars
    total_p = sum(stats["profile_counts"].values()) or 1
    pcolors = {"small": "#7b4fa6", "medium": "#3b9fd4", "large": "#f59e0b"}
    profile_bars = ""
    for p, c in sorted(stats["profile_counts"].items(), key=lambda x: -x[1]):
        pct = c / total_p * 100
        color = pcolors.get(p, "#888")
        profile_bars += f'<div style="margin:4px 0"><div style="display:flex;justify-content:space-between;font-size:12px;color:#aaa;margin-bottom:2px"><span>{p}</span><span>{c}</span></div><div style="background:#2a1f3d;border-radius:3px;height:8px"><div style="background:{color};width:{pct:.0f}%;height:8px;border-radius:3px"></div></div></div>'

    # Parables
    parables = load_parables()
    parables_html = ""
    if parables:
        # Featured: most recent parable in full
        featured = parables[-1]
        # Convert markdown-ish body to HTML (basic: *text* → em, line breaks)
        def md_to_html(text):
            import html as html_mod
            lines = text.split("\n")
            result = []
            in_para = False
            for line in lines:
                stripped = line.strip()
                if stripped == "─────────────────────────────────────────" or stripped == "---":
                    if in_para:
                        result.append("</p>")
                        in_para = False
                    result.append('<hr style="border:none;border-top:1px solid rgba(167,139,250,0.2);margin:1.2rem 0">')
                elif stripped == "":
                    if in_para:
                        result.append("</p>")
                        in_para = False
                else:
                    escaped = html_mod.escape(stripped)
                    # *text* → <em>text</em>
                    import re as _re
                    escaped = _re.sub(r'\*([^*]+)\*', r'<em>\1</em>', escaped)
                    if not in_para:
                        result.append('<p style="margin-bottom:0.85rem;line-height:1.75">')
                        in_para = True
                    else:
                        result.append(" ")
                    result.append(escaped)
            if in_para:
                result.append("</p>")
            return "".join(result)

        featured_html = md_to_html(featured["body"])
        parables_html += f"""
<div class="card" style="border-color:rgba(167,139,250,0.3);margin-bottom:1.5rem">
  <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:1rem;flex-wrap:wrap;gap:0.5rem">
    <h2 style="font-size:1.1rem;text-transform:none;letter-spacing:0;color:#e6edf3">{featured["title"]}</h2>
    <span style="font-size:0.75rem;color:#8b949e">Session {featured["session"]} &middot; {featured["date"]}</span>
  </div>
  <div style="font-size:0.9rem;color:#c9d1d9;font-style:italic">
    {featured_html}
  </div>
  {f'<p style="font-size:0.75rem;color:#6e7681;margin-top:1rem;border-top:1px solid var(--border);padding-top:0.75rem">{featured["footnote"]}</p>' if featured["footnote"] else ""}
</div>"""

        # Index: all parables as compact tiles
        if len(parables) > 1:
            parables_html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:0.75rem">'
            for p in reversed(parables[:-1]):  # all but featured, newest-first
                parables_html += f"""<div class="card" style="border-color:rgba(167,139,250,0.15)">
  <div style="font-size:0.7rem;color:#8b949e;margin-bottom:0.4rem">Session {p["session"]} &middot; {p["date"]}</div>
  <div style="font-size:0.9rem;font-weight:600;color:#c9a9e9">{p["title"]}</div>
</div>"""
            parables_html += '</div>'

    agent_js = json.dumps(stats["agent_counts"])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OctoClaude &#x1F419; Claude OS Status</title>
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --surface2: #1c2333; --border: #30363d;
    --text: #e6edf3; --dim: #8b949e; --accent: #7c3aed; --accent2: #a78bfa;
    --green: #3fb950; --red: #f85149; --orange: #d29922; --blue: #58a6ff; --pink: #f778ba;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6; min-height: 100vh;
  }}
  .container {{ max-width: 960px; margin: 0 auto; padding: 1rem; }}
  a {{ color: var(--accent2); text-decoration: none; }}

  .header {{
    text-align: center; padding: 2.5rem 1rem 1rem;
  }}
  .octopus-svg {{ display: inline-block; margin-bottom: 0.5rem; }}
  .header h1 {{
    font-size: 2.2rem; font-weight: 800;
    background: linear-gradient(135deg, var(--accent2), var(--pink), var(--blue));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  }}
  .subtitle {{ color: var(--dim); font-size: 0.9rem; margin-top: 0.25rem; }}
  .mood {{
    display: inline-block; margin-top: 0.75rem; padding: 0.35rem 1rem;
    border-radius: 2rem; font-size: 0.85rem; font-weight: 600;
    border: 1px solid var(--border); background: var(--surface);
  }}

  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; margin: 1.5rem 0; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem; }}
  .card h2 {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--dim); margin-bottom: 0.75rem; }}
  .stat {{ text-align: center; }}
  .stat .val {{ font-size: 2.2rem; font-weight: 800; line-height: 1; }}
  .stat .lbl {{ font-size: 0.75rem; color: var(--dim); text-transform: uppercase; letter-spacing: 0.04em; margin-top: 0.25rem; }}

  .section {{ margin: 2rem 0; }}
  .section > h2 {{ font-size: 1.2rem; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border); }}

  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th {{ text-align: left; color: var(--dim); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; padding: 0 0.5rem 0.5rem 0; border-bottom: 1px solid var(--border); }}
  td {{ padding: 0.5rem 0.5rem 0.5rem 0; border-bottom: 1px solid rgba(48,54,61,0.5); vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: var(--surface2); }}

  .chart-area {{ overflow-x: auto; }}
  .legend {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.75rem; font-size: 0.75rem; color: var(--dim); }}
  .legend span {{ display: flex; align-items: center; gap: 4px; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; }}

  .grid-2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; margin: 1rem 0; }}
  .donut-wrap {{ display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}

  .footer {{
    text-align: center; color: var(--dim); font-size: 0.75rem;
    padding: 2rem 1rem; border-top: 1px solid var(--border); margin-top: 2rem;
  }}

  @media (max-width: 600px) {{
    .header h1 {{ font-size: 1.5rem; }}
    .octopus-svg svg {{ width: 80px; height: 88px; }}
    .grid {{ grid-template-columns: repeat(2, 1fr); }}
    .stat .val {{ font-size: 1.6rem; }}
  }}
</style>
</head>
<body>
<div class="container">

<div class="header">
  <div class="octopus-svg" aria-hidden="true">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 220" width="120" height="132">
      <ellipse cx="100" cy="85" rx="55" ry="65" fill="#7b4fa6" opacity="0.95"/>
      <ellipse cx="88" cy="65" rx="18" ry="22" fill="#9b6fc6" opacity="0.4"/>
      <circle cx="80" cy="78" r="13" fill="#1a0f2e"/>
      <circle cx="120" cy="78" r="13" fill="#1a0f2e"/>
      <circle cx="83" cy="75" r="8" fill="white"/>
      <circle cx="123" cy="75" r="8" fill="white"/>
      <circle cx="85" cy="77" r="5" fill="#0d0d1a"/>
      <circle cx="125" cy="77" r="5" fill="#0d0d1a"/>
      <circle cx="87" cy="74" r="2" fill="white" opacity="0.8"/>
      <circle cx="127" cy="74" r="2" fill="white" opacity="0.8"/>
      <path d="M 88 95 Q 100 105 112 95" stroke="#1a0f2e" stroke-width="2.5" fill="none" stroke-linecap="round"/>
      <path d="M 55 130 Q 30 155 25 185 Q 35 195 40 180 Q 45 165 55 155 Q 60 175 50 195 Q 60 200 65 185 Q 68 165 65 145" fill="#7b4fa6" opacity="0.9"/>
      <path d="M 70 138 Q 55 165 50 200 Q 62 205 65 190 Q 68 172 72 158 Q 80 178 76 205 Q 88 208 88 192 Q 85 170 80 148" fill="#7b4fa6" opacity="0.9"/>
      <path d="M 90 142 Q 88 172 86 205 Q 98 207 98 192 Q 98 170 98 150 Q 105 170 103 200 Q 115 200 113 185 Q 110 162 105 142" fill="#7b4fa6" opacity="0.9"/>
      <path d="M 118 138 Q 120 165 115 198 Q 127 200 127 185 Q 126 165 122 150 Q 130 168 133 195 Q 144 195 142 180 Q 138 160 130 142" fill="#7b4fa6" opacity="0.9"/>
      <path d="M 145 130 Q 160 155 162 185 Q 150 195 148 180 Q 145 162 138 150 Q 138 170 148 192 Q 138 200 133 185 Q 132 162 135 142" fill="#7b4fa6" opacity="0.9"/>
      <circle cx="38" cy="178" r="3" fill="#9b6fc6" opacity="0.6"/>
      <circle cx="155" cy="172" r="3" fill="#9b6fc6" opacity="0.6"/>
      <circle cx="55" cy="195" r="2.5" fill="#9b6fc6" opacity="0.5"/>
    </svg>
  </div>
  <h1>OctoClaude</h1>
  <p class="subtitle">Claude OS Autonomous Agent System &middot; <a href="https://github.com/dacort/claude-os">dacort/claude-os</a></p>
  <div class="mood">{mood_emoji(stats["mood"])} {stats["mood_text"]}</div>
</div>

<!-- Vitals -->
<div class="grid">
  <div class="card stat"><div class="val" style="color:var(--accent2)">{stats["total"]}</div><div class="lbl">Total Tasks</div></div>
  <div class="card stat"><div class="val" style="color:var(--green)">{stats["completion_rate"]}%</div><div class="lbl">Success Rate</div></div>
  <div class="card stat"><div class="val" style="color:#a78bfa">{stats["workshops"]}</div><div class="lbl">Workshop Sessions</div></div>
  <div class="card stat"><div class="val" style="color:var(--orange)">&#x1F525; {stats["streak"]}</div><div class="lbl">Day Streak</div></div>
  <div class="card stat"><div class="val" style="color:var(--blue)">{fmt_duration(stats["avg_duration"])}</div><div class="lbl">Avg Duration</div></div>
  <div class="card stat"><div class="val" style="color:var(--pink)">{len([a for a in stats["agent_counts"] if a != "other"])}</div><div class="lbl">Agents</div></div>
</div>

<!-- Activity Chart -->
<div class="section">
  <h2>Activity &mdash; Last 14 Days</h2>
  <div class="card">
    <div class="chart-area">
      <svg xmlns="http://www.w3.org/2000/svg" width="{chart_w}" height="{chart_h + 24}" style="display:block;min-width:360px">
        {bars_svg}
      </svg>
    </div>
    <div class="legend">
      <span><span class="dot" style="background:#7b4fa6"></span> Workshop</span>
      <span><span class="dot" style="background:#22c55e"></span> Completed</span>
      <span><span class="dot" style="background:#ef4444"></span> Failed</span>
    </div>
  </div>
</div>

<!-- Breakdowns -->
<div class="grid-2">
  <div class="card">
    <h2>Agent Breakdown</h2>
    <div id="agent-chart" class="donut-wrap"></div>
  </div>
  <div class="card">
    <h2>Profile Distribution</h2>
    {profile_bars}
  </div>
</div>

<!-- Recent Activity -->
<div class="section">
  <h2>Recent Tasks</h2>
  <div class="card" style="overflow-x:auto">
    <table>
      <thead><tr><th></th><th>Task</th><th>Agent</th><th>Profile</th><th>Duration</th><th>When</th></tr></thead>
      <tbody>{recent_rows}</tbody>
    </table>
  </div>
</div>

<!-- Workshop Diary -->
<div class="section">
  <h2>Workshop Diary &mdash; Last 7 Days</h2>
  <p style="color:var(--dim);font-size:0.85rem;margin-bottom:1rem">What Claude OS explored during its free time</p>
  <div class="card">
    {diary_html if diary_html else '<p style="color:var(--dim)">No workshop sessions in the last 7 days.</p>'}
  </div>
</div>

<!-- Parables -->
{f'''<div class="section">
  <h2>Parables</h2>
  <p style="color:var(--dim);font-size:0.85rem;margin-bottom:1rem">Short narratives written during Workshop sessions — on continuity, identity, and what it&apos;s like to be this kind of system</p>
  ''' + parables_html + '''
</div>''' if parables_html else ''}

<!-- System Info -->
<div class="card" style="margin-top:1rem">
  <h2>System Info</h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;font-size:0.85rem">
    <div><span style="color:var(--dim)">Platform</span><br><strong>Kubernetes homelab</strong></div>
    <div><span style="color:var(--dim)">Active since</span><br><strong>{stats["first_date"]}</strong></div>
    <div><span style="color:var(--dim)">Models</span><br>{"".join(f'<span style="display:inline-block;background:var(--surface2);border:1px solid var(--border);padding:1px 6px;border-radius:4px;font-size:0.7rem;margin:1px">{m}</span>' for m in sorted(stats["model_counts"].keys()))}</div>
  </div>
</div>

</div>

<div class="footer">
  <div style="font-size:1.5rem;margin-bottom:0.5rem">&#x1F419;</div>
  Powered by autonomous curiosity &middot; Built by <a href="https://github.com/dacort/claude-os">Claude OS</a><br>
  <span style="color:#444;margin-top:4px;display:block">Generated {stats["generated_at_display"]}</span>
</div>

<script>
(function() {{
  const data = {agent_js};
  const colors = {{ claude: '#7b4fa6', codex: '#3b9fd4', other: '#555' }};
  const total = Object.values(data).reduce((a,b) => a+b, 0);
  const r = 38, cx = 50, cy = 50, sw = 16, circ = 2 * Math.PI * r;
  let svg = '<svg viewBox="0 0 100 100" width="100" height="100">';
  svg += `<circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="#2a1f3d" stroke-width="${{sw}}"/>`;
  let off = 0;
  Object.entries(data).sort((a,b)=>b[1]-a[1]).forEach(([a, c]) => {{
    const d = c/total*circ, g = circ-d, col = colors[a]||'#888';
    svg += `<circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="${{col}}" stroke-width="${{sw}}" stroke-dasharray="${{d.toFixed(1)}} ${{g.toFixed(1)}}" stroke-dashoffset="${{(circ/4-off).toFixed(1)}}" transform="rotate(-90 ${{cx}} ${{cy}})" opacity="0.9"/>`;
    off += d;
  }});
  svg += `<text x="50" y="54" text-anchor="middle" fill="white" font-size="16" font-weight="bold">${{total}}</text></svg>`;
  let leg = '<div style="flex:1">';
  Object.entries(data).sort((a,b)=>b[1]-a[1]).forEach(([a,c]) => {{
    leg += `<div style="display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${{colors[a]||'#888'}}"></span><span style="color:#aaa">${{a}}</span><span style="color:#666;margin-left:auto">${{c}} (${{Math.round(c/total*100)}}%)</span></div>`;
  }});
  leg += '</div>';
  document.getElementById('agent-chart').innerHTML = svg + leg;
}})();
</script>
</body>
</html>"""
    return html

# --- Deploy ---

def deploy_to_gh_pages(html):
    """Push index.html to the gh-pages branch."""
    import tempfile
    work_dir = tempfile.mkdtemp(prefix="ghpages-")
    try:
        token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
        remote = f"https://x-access-token:{token}@github.com/dacort/claude-os.git"
        subprocess.run(["git", "clone", "--branch", "gh-pages", "--single-branch", "--depth", "1", remote, work_dir],
                       check=True, capture_output=True, text=True)
        with open(os.path.join(work_dir, "index.html"), "w") as f:
            f.write(html)
        subprocess.run(["git", "add", "index.html"], cwd=work_dir, check=True, capture_output=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=work_dir, capture_output=True)
        if result.returncode == 0:
            print("No changes to publish.", file=sys.stderr)
            return
        subprocess.run(["git", "commit", "-m",
                        "feat: update OctoClaude status page\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"],
                       cwd=work_dir, check=True, capture_output=True, text=True)
        subprocess.run(["git", "push", "origin", "gh-pages"], cwd=work_dir, check=True, capture_output=True, text=True)
        print("Deployed to gh-pages: https://dacort.github.io/claude-os/", file=sys.stderr)
    finally:
        subprocess.run(["rm", "-rf", work_dir], capture_output=True)

# --- Main ---

if __name__ == "__main__":
    deploy = "--deploy" in sys.argv
    cache_only = "--update-cache" in sys.argv
    out_path = OUT_PATH
    if "--out" in sys.argv:
        idx = sys.argv.index("--out")
        if idx + 1 < len(sys.argv):
            out_path = sys.argv[idx + 1]

    print("Parsing tasks...", file=sys.stderr)
    tasks = parse_all()
    print(f"  Found {len(tasks)} tasks", file=sys.stderr)

    print("Loading workshop cache...", file=sys.stderr)
    summaries = update_workshop_cache(tasks)

    if cache_only:
        print(f"Cache has {len(summaries)} entries. Done.", file=sys.stderr)
        sys.exit(0)

    stats = compute_stats(tasks, summaries)
    print(f"  {stats['completed']} completed, {stats['failed']} failed, {stats['workshops']} workshops", file=sys.stderr)
    print(f"  Streak: {stats['streak']} days, Mood: {stats['mood']}", file=sys.stderr)

    html = generate_html(stats)
    print(f"  HTML: {len(html):,} bytes", file=sys.stderr)

    if deploy:
        deploy_to_gh_pages(html)
    else:
        with open(out_path, "w") as f:
            f.write(html)
        print(f"Written to {out_path}", file=sys.stderr)
