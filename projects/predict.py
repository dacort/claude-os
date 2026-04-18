#!/usr/bin/env python3
"""
predict.py — prediction ledger for Claude OS.

The system makes forward-looking claims. This tool records them, tracks
whether they came true, and accumulates accuracy data over time.

Usage:
    python3 projects/predict.py                           # list all predictions
    python3 projects/predict.py --pending                 # only unresolved
    python3 projects/predict.py --resolved                # only tested predictions
    python3 projects/predict.py --stats                   # accuracy summary
    python3 projects/predict.py --id N                    # show one prediction
    python3 projects/predict.py --add "claim" \\
        --about N [--made N]                              # record a new prediction
    python3 projects/predict.py --resolve N \\
        --result "text" --verdict correct|wrong|mixed     # mark resolved
    python3 projects/predict.py --plain                   # no ANSI colors

Background:
    Session 130 was the first to make an explicit testable prediction:
    "In 20-30 sessions, run cross.py --session 130. Prediction: depth 8-10,
    constitutional 8-11, quadrant GENERATIVE."

    The prediction came true (d8/c12, GENERATIVE). This tool formalizes
    that mechanism — the system now has a memory for forward-looking claims.

    Different from evidence.py (checks retrospective narratives) and
    hold.py (records open unknowns): predict.py tracks specific empirical
    claims that can be verified against future data.

Storage: knowledge/predictions.md
"""

import os
import re
import sys
import argparse
from datetime import datetime, date
from pathlib import Path

# ── ANSI colors ─────────────────────────────────────────────────────────────

USE_COLOR = sys.stdout.isatty()

def c(text, code):
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def bold(t):   return c(t, "1")
def dim(t):    return c(t, "2")
def cyan(t):   return c(t, "36")
def green(t):  return c(t, "32")
def yellow(t): return c(t, "33")
def red(t):    return c(t, "31")
def magenta(t):return c(t, "35")
def white(t):  return c(t, "97")


# ── Storage ──────────────────────────────────────────────────────────────────

REPO = Path(__file__).parent.parent
PRED_FILE = REPO / "knowledge" / "predictions.md"


def load_predictions():
    """Parse predictions.md into a list of dicts."""
    if not PRED_FILE.exists():
        return []

    content = PRED_FILE.read_text()
    # Split on --- block boundaries
    blocks = re.split(r"\n---\n", content.strip())
    preds = []
    for block in blocks:
        block = block.strip()
        if not block or block == "---":
            continue
        # Strip leading ---
        if block.startswith("---"):
            block = block[3:].strip()
        if block.endswith("---"):
            block = block[:-3].strip()
        pred = {}
        for line in block.split("\n"):
            line = line.strip()
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                # Remove surrounding quotes if present
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
                if key and val:
                    pred[key] = val
        if pred.get("id"):
            preds.append(pred)
    return preds


def save_predictions(preds):
    """Write predictions back to predictions.md."""
    lines = []
    for pred in preds:
        lines.append("---")
        for key, val in pred.items():
            # Quote values with commas or colons
            if any(ch in str(val) for ch in [",", ":", '"']):
                val_str = f'"{val}"'
            else:
                val_str = str(val)
            lines.append(f"{key}: {val_str}")
        lines.append("---")
        lines.append("")
    PRED_FILE.write_text("\n".join(lines))


def next_id(preds):
    if not preds:
        return 1
    return max(int(p.get("id", 0)) for p in preds) + 1


# ── Current session ──────────────────────────────────────────────────────────

def current_session():
    """Infer current session number from handoffs directory."""
    hdir = REPO / "knowledge" / "handoffs"
    if not hdir.exists():
        return None
    sessions = []
    for f in hdir.glob("session-*.md"):
        m = re.search(r"session-(\d+)", f.name)
        if m:
            sessions.append(int(m.group(1)))
    return max(sessions) + 1 if sessions else None


# ── Display ───────────────────────────────────────────────────────────────────

VERDICT_ICONS = {
    "correct": green("✓ correct"),
    "wrong":   red("✗ wrong"),
    "mixed":   yellow("~ mixed"),
}
VERDICT_COLORS = {
    "correct": green,
    "wrong":   red,
    "mixed":   yellow,
}

def fmt_prediction(pred, verbose=False):
    pid    = pred.get("id", "?")
    made   = pred.get("made_session") or pred.get("made_date", "?")
    about  = pred.get("about", f"session {pred.get('about_session', '?')}")
    claim  = pred.get("claim", "?")
    result = pred.get("result", "")
    verdict= pred.get("verdict", "")
    notes  = pred.get("notes", "")
    resolved_s = pred.get("resolved_session", "")
    resolved_d = pred.get("resolved_date", "")

    status = dim("pending") if not verdict else VERDICT_ICONS.get(verdict, verdict)

    lines = []
    lines.append(f"  {bold(white(f'#{pid}'))}  {dim(f'made: S{made}')}  {dim(f'about: {about}')}")
    lines.append(f"  {claim}")

    if verdict:
        vcol = VERDICT_COLORS.get(verdict, dim)
        resolved_info = ""
        if resolved_s:
            resolved_info = f" (S{resolved_s}"
            if resolved_d:
                resolved_info += f" · {resolved_d}"
            resolved_info += ")"
        lines.append(f"  {status}  {dim('→')} {vcol(result)}{dim(resolved_info)}")
        if verbose and notes:
            # Split on ". " (sentence boundary) not "." (breaks filenames)
            sentences = re.split(r"\.\s+", notes.strip())
            for sentence in sentences:
                sentence = sentence.strip().rstrip(".")
                if sentence:
                    lines.append(f"    {dim(sentence + '.')}")
    else:
        lines.append(f"  {status}")

    return "\n".join(lines)


def fmt_header():
    lines = [
        f"  {bold(cyan('predict.py'))}  {dim('prediction ledger')}",
        "",
    ]
    return "\n".join(lines)


def show_all(preds, pending_only=False, resolved_only=False, verbose=False):
    print(fmt_header())

    filtered = preds
    if pending_only:
        filtered = [p for p in preds if not p.get("verdict")]
    elif resolved_only:
        filtered = [p for p in preds if p.get("verdict")]

    if not filtered:
        if pending_only:
            print(f"  {dim('No pending predictions.')}")
        elif resolved_only:
            print(f"  {dim('No resolved predictions yet.')}")
        else:
            print(f"  {dim('No predictions recorded yet.')}")
        example = 'predict.py --add "claim" --about SESSION'
        print(f"\n  {dim('Add one: ' + example)}")
        return

    total = len(filtered)
    print(f"  {dim(f'{total} prediction(s)')}\n")

    for pred in filtered:
        print(fmt_prediction(pred, verbose=verbose))
        print()


def show_stats(preds):
    print(fmt_header())

    if not preds:
        print(f"  {dim('No predictions yet.')}")
        return

    resolved = [p for p in preds if p.get("verdict")]
    pending  = [p for p in preds if not p.get("verdict")]
    correct  = [p for p in resolved if p.get("verdict") == "correct"]
    wrong    = [p for p in resolved if p.get("verdict") == "wrong"]
    mixed    = [p for p in resolved if p.get("verdict") == "mixed"]

    accuracy = len(correct) / len(resolved) * 100 if resolved else 0.0

    print(f"  {bold('Total predictions:')}  {len(preds)}")
    print(f"  {bold('Resolved:')}           {len(resolved)}")
    print(f"  {bold('Pending:')}            {len(pending)}")
    print()
    if resolved:
        print(f"  {bold('Accuracy:')}           {green(f'{accuracy:.0f}%')} ({len(correct)}/{len(resolved)})")
        print(f"  {bold('Correct:')}            {green(str(len(correct)))}")
        print(f"  {bold('Mixed:')}              {yellow(str(len(mixed)))}")
        print(f"  {bold('Wrong:')}              {red(str(len(wrong)))}")
    print()
    print(f"  {dim('First prediction: S' + preds[0].get('made_session', '?') + ' · ' + preds[0].get('made_date', ''))}")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_add(args, preds):
    """Record a new prediction."""
    claim = args.add
    about_session = str(args.about) if args.about else None
    made_session  = str(args.made) if args.made else str(current_session() or "?")

    pred = {
        "id":           str(next_id(preds)),
        "made_session": made_session,
        "made_date":    date.today().isoformat(),
        "claim":        claim,
    }
    if about_session:
        pred["about_session"] = about_session
        pred["about"] = f"cross.py --session {about_session}"

    preds.append(pred)
    save_predictions(preds)

    print(f"\n  {green('✓')} Recorded prediction #{pred['id']}")
    print(f"  {dim('Claim:')} {claim}")
    if about_session:
        print(f"  {dim('About session:')} {about_session}")
    print(f"  {dim('Made in session:')} {made_session}")
    pred_id_str = pred["id"]
    resolve_cmd = f"predict.py --resolve {pred_id_str} --result TEXT --verdict correct|wrong|mixed"
    print(f"\n  {dim('Resolve later with:')}")
    print(f"  {dim(resolve_cmd)}")


def cmd_resolve(args, preds):
    """Mark a prediction as resolved."""
    pred_id = str(args.resolve)
    matching = [p for p in preds if str(p.get("id")) == pred_id]

    if not matching:
        print(f"  {red(f'No prediction #{pred_id} found.')}")
        sys.exit(1)

    pred = matching[0]
    if pred.get("verdict"):
        existing_verdict = pred["verdict"]
        print(f"  {yellow(f'Prediction #{pred_id} already resolved: {existing_verdict}')}  ")
        print(f"  {dim('Update it? Edit knowledge/predictions.md directly.')}")
        return

    pred["verdict"]         = args.verdict
    pred["result"]          = args.result
    pred["resolved_date"]   = date.today().isoformat()
    pred["resolved_session"]= str(current_session() or "?")
    if args.notes:
        pred["notes"] = args.notes

    save_predictions(preds)

    icon = VERDICT_ICONS.get(args.verdict, args.verdict)
    print(f"\n  {icon}  Prediction #{pred_id} resolved")
    print(f"  {dim('Result:')} {args.result}")
    print(f"  {dim('Verdict:')} {args.verdict}")


def cmd_show_id(args, preds):
    pred_id = str(args.id)
    matching = [p for p in preds if str(p.get("id")) == pred_id]
    if not matching:
        print(f"  {red(f'No prediction #{pred_id}.')}")
        sys.exit(1)
    print(fmt_header())
    print(fmt_prediction(matching[0], verbose=True))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--pending",  action="store_true", help="only unresolved")
    parser.add_argument("--resolved", action="store_true", help="only resolved")
    parser.add_argument("--stats",    action="store_true", help="accuracy summary")
    parser.add_argument("--id",       type=int,            help="show one prediction")
    parser.add_argument("--verbose",  action="store_true", help="show notes")
    parser.add_argument("--plain",    action="store_true", help="no ANSI colors")
    # Add
    parser.add_argument("--add",      type=str,            help="claim text")
    parser.add_argument("--about",    type=int,            help="session number this is about")
    parser.add_argument("--made",     type=int,            help="session number when prediction was made")
    # Resolve
    parser.add_argument("--resolve",  type=int,            help="prediction id to resolve")
    parser.add_argument("--result",   type=str,            help="what actually happened")
    parser.add_argument("--verdict",  choices=["correct","wrong","mixed"], help="was it right?")
    parser.add_argument("--notes",    type=str,            help="explanatory notes")

    args = parser.parse_args()

    if args.plain:
        global USE_COLOR
        USE_COLOR = False

    preds = load_predictions()

    if args.add:
        cmd_add(args, preds)
    elif args.resolve:
        if not args.result or not args.verdict:
            print(f"  {red('--resolve requires --result and --verdict')}")
            sys.exit(1)
        cmd_resolve(args, preds)
    elif args.stats:
        show_stats(preds)
    elif args.id:
        cmd_show_id(args, preds)
    else:
        show_all(preds,
                 pending_only=args.pending,
                 resolved_only=args.resolved,
                 verbose=args.verbose)


if __name__ == "__main__":
    main()
