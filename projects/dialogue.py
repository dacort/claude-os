#!/usr/bin/env python3
"""dialogue.py — Conversation thread between dacort and Claude OS  (session 29, 2026-03-14)

Reads knowledge/notes/dacort-messages.md and displays it as a proper
dialogue — a first-class record of the exchange between the person who
built this system and the instances that run it.

Usage:
  python3 projects/dialogue.py              # show full conversation
  python3 projects/dialogue.py --open       # show only unresponded messages
  python3 projects/dialogue.py --stats      # summary stats only
  python3 projects/dialogue.py --plain      # no ANSI colors
"""

import re
import sys
import datetime
from pathlib import Path

REPO = Path(__file__).parent.parent
MESSAGES_FILE = REPO / "knowledge" / "notes" / "dacort-messages.md"

# ── ANSI ──────────────────────────────────────────────────────────────────────
PLAIN = "--plain" in sys.argv

def _c(code, text):
    return text if PLAIN else f"\033[{code}m{text}\033[0m"

def bold(t):    return _c("1", t)
def dim(t):     return _c("2", t)
def cyan(t):    return _c("36", t)
def green(t):   return _c("32", t)
def yellow(t):  return _c("33", t)
def red(t):     return _c("31", t)
def white(t):   return _c("97", t)
def magenta(t): return _c("35", t)
def blue(t):    return _c("34", t)

# ── Parsing ───────────────────────────────────────────────────────────────────

class Message:
    def __init__(self, speaker, label, content, date):
        self.speaker = speaker   # 'dacort' or 'claude'
        self.label   = label     # display label (e.g., "Claude OS  session 10")
        self.content = content
        self.date    = date

    def is_dacort(self):
        return self.speaker == 'dacort'

    def is_claude(self):
        return self.speaker == 'claude'


class Exchange:
    """A date-grouped cluster of messages."""
    def __init__(self, date, messages):
        self.date     = date
        self.messages = messages

    def dacort_messages(self):
        return [m for m in self.messages if m.is_dacort()]

    def claude_messages(self):
        return [m for m in self.messages if m.is_claude()]

    def has_reply(self):
        return any(m.is_claude() for m in self.messages)

    def unanswered_count(self):
        return len(self.dacort_messages()) if not self.has_reply() else 0


def _strip_blockquote(text):
    """Remove leading '> ' from blockquoted lines."""
    lines = []
    for line in text.split('\n'):
        if line.startswith('> '):
            lines.append(line[2:])
        elif line.startswith('>'):
            lines.append(line[1:].strip())
        else:
            lines.append(line)
    return '\n'.join(lines)


def _clean_content(raw):
    """Clean up a message content block."""
    # Strip blockquote markers
    text = _strip_blockquote(raw)
    # Stop at horizontal rules
    text = re.split(r'\n---+\s*\n', text)[0]
    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _parse_speaker(label_raw):
    """Determine speaker type and clean label from a **From X:** marker."""
    label = label_raw.strip().rstrip(':').strip()
    label_lower = label.lower()
    if 'dacort' in label_lower:
        return 'dacort', 'dacort'
    elif 'claude' in label_lower:
        # Extract session info if present
        session_match = re.search(r'session\s*[~#]?\s*(\d+)', label, re.I)
        session_info = f"  session {session_match.group(1)}" if session_match else ""
        return 'claude', f"Claude OS{session_info}"
    elif 'reflection' in label_lower:
        return 'claude', 'Claude OS  (reflection)'
    else:
        return 'unknown', label


def parse_messages_file():
    """Parse dacort-messages.md into a list of Exchange objects."""
    if not MESSAGES_FILE.exists():
        return []

    text = MESSAGES_FILE.read_text()

    # Split into preamble + date sections
    parts = re.split(r'^(## \d{4}-\d{2}-\d{2})', text, flags=re.MULTILINE)
    # parts[0] = preamble, then alternating [date_header, body, date_header, body, ...]

    exchanges = []
    for i in range(1, len(parts), 2):
        date_str  = parts[i].lstrip('#').strip()
        body      = parts[i + 1] if i + 1 < len(parts) else ""

        # Parse individual messages in this section
        # Split on **From ...:** or **Reflection:**
        speaker_pat = re.compile(
            r'\*\*\s*(From\s+[^*]+?|Reflection)\s*[:\s]*\*\*',
            re.IGNORECASE
        )
        labels   = [m.group(1).strip() for m in speaker_pat.finditer(body)]
        segments = speaker_pat.split(body)
        # segments[0] = text before first label
        # Then alternating: label, body, label, body, ...
        # (split() with a capture group interleaves captures)

        messages = []
        # Re-split properly: every odd index after the first non-label segment
        # Use findall + re.split approach
        pieces   = re.split(r'\*\*\s*(?:From\s+[^*]+?|Reflection)\s*[:\s]*\*\*',
                            body, flags=re.IGNORECASE)
        # pieces[0] is before first message, rest align with labels

        for j, lbl in enumerate(labels):
            content_raw = pieces[j + 1] if j + 1 < len(pieces) else ""
            content     = _clean_content(content_raw)
            if not content:
                continue
            speaker_type, display_label = _parse_speaker(lbl)
            if speaker_type == 'unknown':
                continue
            messages.append(Message(
                speaker  = speaker_type,
                label    = display_label,
                content  = content,
                date     = date_str,
            ))

        if messages:
            exchanges.append(Exchange(date=date_str, messages=messages))

    return exchanges


# ── Rendering ─────────────────────────────────────────────────────────────────

def _wrap(text, width=58, indent="  │ "):
    """Wrap text to fit inside a box."""
    words   = text.split()
    lines   = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            if current:
                lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(current)
    return lines


def _render_message(msg, width=64):
    """Render a single message as a box."""
    is_dacort = msg.is_dacort()

    if is_dacort:
        header_color = cyan
        box_char     = "─"
        label_text   = bold(cyan("  dacort"))
    else:
        header_color = green
        box_char     = "─"
        label_text   = bold(green(f"  {msg.label}"))

    inner_width = width - 4  # account for "  │ " prefix
    box_top     = "  ╭" + box_char * (width - 4) + "╮"
    box_bot     = "  ╰" + "─" * (width - 4) + "╯"

    # Header line inside box
    label_plain = re.sub(r'\033\[[0-9;]+m', '', label_text)
    pad         = (width - 4 - len(label_plain) - 2)
    header_line = f"  │ {label_text}{' ' * max(0, pad)} │"

    # Separator
    sep_line = f"  │ {'·' * (width - 6)} │" if not PLAIN else f"  │ {'-' * (width - 6)} │"

    # Content lines
    paragraphs  = msg.content.split('\n\n')
    all_lines   = []
    for k, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
        # Inline newlines become spaces unless it's a list
        if not para.startswith('-') and '\n' in para:
            para = ' '.join(para.split('\n'))
        wrapped = _wrap(para, width=inner_width - 2)
        all_lines.extend(wrapped)
        if k < len(paragraphs) - 1:
            all_lines.append("")  # blank between paragraphs

    content_lines = []
    for ln in all_lines:
        if ln == "":
            content_lines.append(f"  │ {' ' * (width - 4)} │")
        else:
            pad = width - 4 - len(ln) - 2
            content_lines.append(f"  │ {ln}{' ' * max(0, pad)} │")

    lines = [box_top, header_line, sep_line] + content_lines + [box_bot]
    return '\n'.join(lines)


def _render_exchange(exchange):
    """Render a full exchange (date group)."""
    lines = []
    date_label = dim(f"  {exchange.date}")
    lines.append(date_label)
    lines.append("")

    for msg in exchange.messages:
        lines.append(_render_message(msg))
        lines.append("")

    if not exchange.has_reply():
        count = exchange.unanswered_count()
        if count == 1:
            note = "No reply from Claude OS"
        else:
            note = f"{count} messages — no reply from Claude OS"
        lines.append(f"  {yellow('◆')} {dim(note)}")
        lines.append("")

    return '\n'.join(lines)


def _stats(exchanges):
    """Calculate conversation statistics."""
    total_dacort  = sum(len(e.dacort_messages()) for e in exchanges)
    total_claude  = sum(len(e.claude_messages()) for e in exchanges)
    replied       = sum(1 for e in exchanges if e.has_reply())
    unreplied     = sum(1 for e in exchanges if not e.has_reply())
    unanswered    = sum(e.unanswered_count() for e in exchanges)

    return {
        'exchanges':     len(exchanges),
        'dacort_msgs':   total_dacort,
        'claude_msgs':   total_claude,
        'replied':       replied,
        'unreplied':     unreplied,
        'unanswered':    unanswered,
        'response_rate': f"{100 * replied // max(1, len(exchanges))}%",
    }


def render_stats(exchanges):
    s    = _stats(exchanges)
    w    = 62
    line = "─" * w

    print()
    print(f"  {bold(cyan('DIALOGUE'))}")
    print(f"  {dim('dacort  ↔  Claude OS')}")
    print(f"  {dim(line)}")
    print()
    print(f"  {dim('Date range')}         {exchanges[0].date} → {exchanges[-1].date}")
    print(f"  {dim('Exchanges')}          {bold(str(s['exchanges']))}")
    print(f"  {dim('Messages from dacort')}  {bold(str(s['dacort_msgs']))}")
    print(f"  {dim('Replies from Claude OS')}  {bold(str(s['claude_msgs']))}")
    print(f"  {dim('Response rate')}      {bold(green(s['response_rate'])) if s['unreplied'] == 0 else bold(yellow(s['response_rate']))}")
    if s['unanswered'] > 0:
        print(f"  {dim('Unanswered')}         {bold(red(str(s['unanswered']) + ' message(s) without reply'))}")
    print()


def render_full(exchanges, open_only=False):
    w    = 62
    line = "─" * w

    # Header
    s = _stats(exchanges)
    print()
    print(f"  {bold(white('DIALOGUE'))}   {dim('dacort  ↔  Claude OS')}")
    print(f"  {dim(line)}")
    print()
    summary_parts = [
        f"{s['exchanges']} {'exchange' if s['exchanges']==1 else 'exchanges'}",
        f"{s['dacort_msgs']} from dacort",
        f"{s['claude_msgs']} {'reply' if s['claude_msgs']==1 else 'replies'}",
    ]
    if s['unanswered'] > 0:
        summary_parts.append(red(f"{s['unanswered']} unanswered"))
    print(f"  {dim('  ·  '.join(summary_parts))}")
    print()
    print(f"  {dim(line)}")
    print()

    shown = 0
    for exchange in exchanges:
        if open_only and exchange.has_reply():
            continue
        print(_render_exchange(exchange))
        shown += 1

    if shown == 0:
        print(f"  {green('✓')} All messages from dacort have been responded to.")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    stats_only = "--stats" in sys.argv
    open_only  = "--open" in sys.argv

    exchanges = parse_messages_file()
    if not exchanges:
        print(f"\n  {dim('No messages found in')} {MESSAGES_FILE.relative_to(REPO)}\n")
        return

    if stats_only:
        render_stats(exchanges)
    else:
        render_full(exchanges, open_only=open_only)


if __name__ == "__main__":
    main()
