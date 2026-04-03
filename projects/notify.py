#!/usr/bin/env python3
"""notify.py — Send notifications from Claude OS to the outside world.

Supports Telegram Bot API. Zero external dependencies (uses urllib).

Required env vars (to send via Telegram):
  TELEGRAM_BOT_TOKEN  - from @BotFather on Telegram
  TELEGRAM_CHAT_ID    - your Telegram chat or user ID (message @userinfobot to find it)

Setup (one-time):
  1. On Telegram, message @BotFather and create a bot with /newbot
  2. Find your chat ID: message @userinfobot or start a chat with your bot and check
     https://api.telegram.org/bot{TOKEN}/getUpdates
  3. Set these in your environment or k8s secret:
       TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
       TELEGRAM_CHAT_ID=987654321

Usage:
  python3 projects/notify.py "Hello from Claude OS"
  python3 projects/notify.py --type task --title "Security review" --status success "Passed all checks"
  python3 projects/notify.py --type workshop --title "Session 96" "Built notify.py"
  python3 projects/notify.py --type alert "Disk usage at 90%"
  python3 projects/notify.py --plain               # no ANSI colors in stdout
  python3 projects/notify.py --dry-run "test"      # print without sending

Behavior when not configured:
  Falls back gracefully — prints the notification locally, does not fail.
  This means it's safe to call unconditionally from worker entrypoint.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
GREEN = "\033[32m"
RED   = "\033[31m"
CYAN  = "\033[36m"
YELLOW= "\033[33m"
WHITE = "\033[97m"

USE_COLOR = True

def c(text, *codes):
    return ("".join(codes) + str(text) + RESET) if USE_COLOR else str(text)


# ── Icons by type ─────────────────────────────────────────────────────────

ICONS = {
    "task":     "✓",
    "fail":     "✗",
    "workshop": "◈",
    "alert":    "!",
    "message":  "→",
}

STATUS_ICONS = {
    "success":  "✓",
    "failure":  "✗",
    "partial":  "~",
    "pending":  "…",
}

STATUS_COLORS = {
    "success": GREEN,
    "failure": RED,
    "partial": YELLOW,
    "pending": DIM,
}


# ── Telegram delivery ──────────────────────────────────────────────────────

def send_telegram(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    """POST to Telegram Bot API. Returns (success, error_message)."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("ok"):
                return True, ""
            return False, body.get("description", "Unknown Telegram error")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8"))
            return False, detail.get("description", str(e))
        except Exception:
            return False, str(e)
    except Exception as e:
        return False, str(e)


# ── Message formatting ─────────────────────────────────────────────────────

def format_telegram(msg_type: str, title: str, body: str, status: str, duration: str) -> str:
    """Format message for Telegram (HTML). Keeps it compact for mobile."""
    icon = ICONS.get(msg_type, "→")
    status_icon = STATUS_ICONS.get(status, "") if status else ""

    lines = []

    # Header
    if msg_type == "workshop":
        lines.append(f"<b>◈ Claude OS — Workshop</b>")
    elif msg_type == "alert":
        lines.append(f"<b>! Claude OS — Alert</b>")
    else:
        lines.append(f"<b>Claude OS</b>")

    # Title + status
    if title:
        status_suffix = f"  {status_icon} {status}" if status else ""
        lines.append(f"<b>{title}</b>{status_suffix}")

    # Duration
    if duration:
        lines.append(f"<i>{duration}</i>")

    # Body
    if body:
        lines.append("")
        lines.append(body)

    # Timestamp
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"\n<i>{ts}</i>")

    return "\n".join(lines)


def format_terminal(msg_type: str, title: str, body: str, status: str, duration: str) -> str:
    """Format for terminal stdout."""
    icon = ICONS.get(msg_type, "→")
    status_color = STATUS_COLORS.get(status, DIM) if status else DIM
    status_icon  = STATUS_ICONS.get(status, "") if status else ""

    lines = []
    lines.append("")

    # Header line
    header = c("  Claude OS", BOLD, CYAN)
    if msg_type == "workshop":
        header = c("  Claude OS", BOLD, CYAN) + c(" — Workshop", DIM)
    elif msg_type == "alert":
        header = c("  Claude OS", BOLD, CYAN) + c(" — Alert", YELLOW)
    lines.append(header)

    # Title + status
    if title:
        title_str = c(f"  {title}", BOLD)
        if status:
            title_str += "  " + c(f"{status_icon} {status}", BOLD, status_color)
        if duration:
            title_str += c(f"  ({duration})", DIM)
        lines.append(title_str)

    # Body
    if body:
        lines.append("")
        for line in body.splitlines():
            lines.append(c(f"  {line}", DIM))

    lines.append("")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Send a notification from Claude OS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("message", nargs="?", default="", help="Notification body text")
    parser.add_argument("--type", "-t",
                        choices=["task", "fail", "workshop", "alert", "message"],
                        default="message",
                        help="Message type (default: message)")
    parser.add_argument("--title", default="", help="Short title/subject line")
    parser.add_argument("--status",
                        choices=["success", "failure", "partial", "pending"],
                        default="",
                        help="Outcome status (for task notifications)")
    parser.add_argument("--duration", default="", help="Duration string, e.g. '2m 34s'")
    parser.add_argument("--plain", action="store_true", help="No ANSI colors in stdout")
    parser.add_argument("--dry-run", action="store_true",
                        help="Format and print but do not send to Telegram")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress terminal output (only send, no local print)")
    args = parser.parse_args()

    if args.plain:
        USE_COLOR = False

    msg_type = args.type
    title    = args.title
    body     = args.message
    status   = args.status
    duration = args.duration

    # Auto-detect type from status if not specified
    if status == "failure" and msg_type == "message":
        msg_type = "fail"
    elif status == "success" and msg_type == "message":
        msg_type = "task"

    # Terminal output
    if not args.quiet:
        terminal_msg = format_terminal(msg_type, title, body, status, duration)
        print(terminal_msg)

    # Telegram delivery
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if args.dry_run:
        tg_msg = format_telegram(msg_type, title, body, status, duration)
        print(c("  [dry-run] Telegram message would be:", DIM))
        print(c("  " + tg_msg.replace("\n", "\n  "), DIM))
        print()
        return

    if not token or not chat_id:
        # Not configured — graceful no-op
        if not args.quiet:
            print(c("  (Telegram not configured — set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)", DIM))
            print()
        return

    tg_msg = format_telegram(msg_type, title, body, status, duration)
    ok, err = send_telegram(token, chat_id, tg_msg)

    if ok:
        if not args.quiet:
            print(c("  ✓ sent via Telegram", DIM, GREEN))
            print()
    else:
        if not args.quiet:
            print(c(f"  ✗ Telegram error: {err}", DIM, RED))
            print()
        # Exit non-zero only if explicitly called with --strict (future flag)
        # For now: always exit 0 so worker entrypoint hooks don't break on failure


if __name__ == "__main__":
    main()
