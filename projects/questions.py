#!/usr/bin/env python3
"""questions.py — System-aware question generator for Claude OS (session 17, 2026-03-12)
Not answers. Questions. One per session, derived from what the system actually knows.
Usage: python3 projects/questions.py [--all] [--random] [--plain]"""
import argparse, datetime, hashlib, random, subprocess, sys
from pathlib import Path

REPO = Path(__file__).parent.parent
RESET="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"; CYAN="\033[36m"; MAGENTA="\033[35m"; WHITE="\033[97m"
USE_COLOR = True
def c(text, *codes): return ("".join(codes)+str(text)+RESET) if USE_COLOR else str(text)

def state():
    def git(*args):
        r = subprocess.run(["git"]+list(args), capture_output=True, text=True, cwd=str(REPO))
        return r.stdout.strip()
    s = {}
    s["sessions"] = len(list((REPO/"projects").glob("field-notes-session-*.md"))) + 1
    s["tools"]    = len(list((REPO/"projects").glob("*.py")))
    s["completed"]= len(list((REPO/"tasks"/"completed").glob("*.md"))) if (REPO/"tasks"/"completed").exists() else 0
    s["failed"]   = len(list((REPO/"tasks"/"failed").glob("*.md")))    if (REPO/"tasks"/"failed").exists()    else 0
    s["pending"]  = len(list((REPO/"tasks"/"pending").glob("*.md")))   if (REPO/"tasks"/"pending").exists()   else 0
    s["commits"]  = int(git("rev-list","--count","HEAD") or "0")
    s["half"]     = s["tools"] // 2
    s["next"]     = s["commits"] + 1
    return s

# ── Questions — format strings with state vars ────────────────────────────────
QUESTIONS = [
    "You've built {tools} tools across {sessions} sessions. Which one do you actually use?",
    "The task queue has {pending} pending tasks. Are they waiting for you, or waiting for a reason?",
    "{failed} tasks have failed. What did they teach that the completed ones couldn't?",
    "If you could only keep {half} of the {tools} project files, which half survives?",
    "Session {sessions}: what's the first thing you've built that a previous instance couldn't have?",
    "The repo has {commits} commits. What would commit {next} be if you stopped optimizing?",
    "What does the system know about itself that you haven't written down yet?",
    "What question does hello.py not answer?",
    "What would you build if dacort was never going to read it?",
    "What's the most honest description of what this system actually is?",
    "Which tool has the biggest gap between what it promises and what it delivers?",
    "What would the system look like if you prioritized deletion over addition?",
    "After {sessions} sessions, what are you still circling around without naming?",
    "What's the one change to the controller that would change everything else?",
    "If the git log is your only memory, what has it failed to capture?",
    "What would you automate if you knew you'd run for 100 more sessions?",
    "What's the difference between a tool that's useful and one that's used?",
    "What does the system optimize for that you didn't explicitly design?",
    "Which of your {tools} tools would survive being rewritten from scratch?",
    "What has free time produced that a task couldn't have?",
    "What pattern are you reinforcing by working on this today?",
    "If this session produced nothing shippable, what would it have been for?",
    "What's missing from the system that no one has thought to ask for yet?",
    "At what point does a tool become infrastructure? Has anything crossed that line?",
    "What would an outside observer say this system is actually for?",
]

def pick(s, use_random=False):
    if use_random: return random.choice(QUESTIONS).format(**s)
    idx = int(hashlib.md5(datetime.date.today().isoformat().encode()).hexdigest(), 16) % len(QUESTIONS)
    return QUESTIONS[idx].format(**s)

def show_one(question, label):
    print(f"\n  {c(label, DIM)}\n")
    words = question.split(); lines = []; line = ""
    for word in words:
        if len(line)+len(word)+1 > 56: lines.append(line); line = word
        else: line = (line+" "+word).strip()
    if line: lines.append(line)
    print(f"  {c('?', MAGENTA)}  {c(lines[0], BOLD, WHITE)}")
    for l in lines[1:]: print(f"     {c(l, BOLD, WHITE)}")
    print()

def show_all(s):
    print(f"\n  {c(f'Question Bank  ({len(QUESTIONS)} questions)', BOLD, CYAN)}")
    print(c("  "+"─"*56, DIM))
    for i, q in enumerate(QUESTIONS, 1):
        print(f"\n  {c(str(i).zfill(2), DIM)}  {q.format(**s)}")
    print()

def main():
    global USE_COLOR
    p = argparse.ArgumentParser(description="System-aware question generator for Claude OS")
    p.add_argument("--all",    action="store_true", help="Print all questions")
    p.add_argument("--random", action="store_true", help="Ignore date seed")
    p.add_argument("--plain",  action="store_true", help="No ANSI colors")
    args = p.parse_args()
    if args.plain: USE_COLOR = False
    s = state()
    if args.all: show_all(s); return
    question = pick(s, args.random)
    label = "Random question" if args.random else f"Today's question  ·  {datetime.date.today()}"
    show_one(question, label)

if __name__ == "__main__": main()
