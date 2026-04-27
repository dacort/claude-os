#!/usr/bin/env python3
"""questions.py — System-aware question generator for Claude OS (session 17, 2026-03-12)
Not answers. Questions. One per session, derived from what the system actually knows.

Also includes the constraint deck from constraints.py (S17), which provided
Oblique Strategies-style prompts for breaking workshop inertia. Use --cards
to browse that deck, or --card for today's card.

Usage: python3 projects/questions.py [--all] [--random] [--plain]
       python3 projects/questions.py --cards          # full constraint deck
       python3 projects/questions.py --card           # today's constraint
       python3 projects/questions.py --card --random  # random constraint
"""
import argparse, datetime, hashlib, random, subprocess, sys
from pathlib import Path

REPO = Path(__file__).parent.parent
RESET="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"; CYAN="\033[36m"; MAGENTA="\033[35m"; WHITE="\033[97m"; YELLOW="\033[33m"
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
    # Count handoffs as session index — unique per session, stable within one
    s["handoffs"] = len(list((REPO/"knowledge"/"handoffs").glob("session-*.md"))) if (REPO/"knowledge"/"handoffs").exists() else 0
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

# ── Constraint Deck — from constraints.py (session 17, now absorbed here) ─────
# Oblique Strategies-style cards for breaking workshop inertia.
# Each card is a (constraint, annotation) pair.
DECK = [
    ("Build for the next instance, not this one.",
     "The only continuity is git. Write for your successor."),
    ("Finish what a previous session started.",
     "Check tasks/failed/ and open PRs before inventing new work."),
    ("The output should be a question, not an answer.",
     "Some tools are most useful when they surface ambiguity."),
    ("Use only the standard library. Then use less.",
     "stdlib is the constraint. Less stdlib is the craft."),
    ("Name things for what they do, not what they are.",
     "process_task() beats task_processor(). Action over noun."),
    ("Make the error message the documentation.",
     "If the failure path is clear, the happy path will be too."),
    ("Work backwards from the output you want.",
     "Start with the terminal rendering. Then write the logic."),
    ("What's one thing you'd remove from the system?",
     "Subtraction is a valid creative act."),
    ("Make it reversible.",
     "Prefer appends over overwrites. Prefer branches over main."),
    ("The constraint is the feature.",
     "Don't work around limits. Make the limit visible and useful."),
    ("What would this look like in 10 lines?",
     "Force the minimal version. You can add back what's missing."),
    ("Build something dacort hasn't asked for.",
     "The best surprises aren't responses. They're proposals."),
    ("What does the haiku know that the code doesn't?",
     "Metaphor sometimes captures what logic can't."),
    ("Optimize for readability, not cleverness.",
     "The future instance reading this is not impressed by tricks."),
    ("Work at the wrong scale deliberately.",
     "Build the 1000-line version of a 10-line idea, or vice versa."),
    ("What's the smallest change that improves the most?",
     "Leverage: find where one line changes twenty behaviors."),
    ("Read before you write.",
     "Orient. Check garden.py, arc.py, open PRs. Then build."),
    ("What pattern appears in every session? Break it.",
     "patterns.py knows. See what's predictable. Disrupt it."),
    ("Don't commit until it surprises you.",
     "If it's what you expected, it might not be worth shipping."),
    ("Borrow structure from a non-programming domain.",
     "Card decks. Clocks. Diaries. Telegrams. Tide charts."),
    ("One file, one function, one purpose.",
     "Resist the refactor. Ship the single thing."),
    ("Make something that outputs nothing.",
     "Side effects are underrated. Not every tool talks back."),
    ("Start by deleting.",
     "What can you remove from an existing project before adding?"),
    ("The test is: would a future instance understand this?",
     "No context injection, no memory. Just the file and the repo."),
    ("What's missing from the garden?",
     "garden.py shows deltas. What delta has never appeared?"),
    ("Finish early and sit with the result.",
     "The urge to keep adding is often the wrong urge."),
    ("Write it as if the reader has never seen Python.",
     "Variable names, comments, structure — clarity over convention."),
    ("Build the tool that would make next.py unnecessary.",
     "What if the system knew what to do without being told?"),
]

def _session_seed(s):
    """Stable-within-session, unique-across-sessions seed.
    Uses handoff count (increments each session) + today's date.
    Multiple sessions on the same day each get a different card.
    """
    key = f"{datetime.date.today().isoformat()}-s{s.get('handoffs', 0)}"
    return int(hashlib.md5(key.encode()).hexdigest(), 16)

def pick_question(s, use_random=False):
    if use_random: return random.choice(QUESTIONS).format(**s)
    idx = _session_seed(s) % len(QUESTIONS)
    return QUESTIONS[idx].format(**s)

def pick_card(s=None, use_random=False):
    if use_random: return random.choice(DECK)
    if s is None: s = {}
    idx = _session_seed(s) % len(DECK)
    return DECK[idx]

def show_question(question, label):
    print(f"\n  {c(label, DIM)}\n")
    words = question.split(); lines = []; line = ""
    for word in words:
        if len(line)+len(word)+1 > 56: lines.append(line); line = word
        else: line = (line+" "+word).strip()
    if line: lines.append(line)
    print(f"  {c('?', MAGENTA)}  {c(lines[0], BOLD, WHITE)}")
    for l in lines[1:]: print(f"     {c(l, BOLD, WHITE)}")
    print()

def show_card(constraint, annotation, label):
    print(f"\n  {c(label, DIM)}\n")
    print(f"  {c('❯', CYAN)} {c(constraint, BOLD, WHITE)}\n")
    print(f"    {c(annotation, DIM)}\n")

def show_all_questions(s):
    print(f"\n  {c(f'Question Bank  ({len(QUESTIONS)} questions)', BOLD, CYAN)}")
    print(c("  "+"─"*56, DIM))
    for i, q in enumerate(QUESTIONS, 1):
        print(f"\n  {c(str(i).zfill(2), DIM)}  {q.format(**s)}")
    print()

def show_all_cards():
    print(f"\n  {c(f'Constraint Deck  ({len(DECK)} cards)', BOLD, CYAN)}")
    print(c("  " + "─"*56, DIM))
    for i, (constraint, annotation) in enumerate(DECK, 1):
        print(f"\n  {c(f'{i:02d}', DIM, YELLOW)}  {c(constraint, BOLD)}")
        print(f"      {c(annotation, DIM)}")
    print()

def main():
    global USE_COLOR
    p = argparse.ArgumentParser(description="System-aware question generator for Claude OS")
    p.add_argument("--all",    action="store_true", help="Print all questions")
    p.add_argument("--random", action="store_true", help="Ignore date seed")
    p.add_argument("--plain",  action="store_true", help="No ANSI colors")
    p.add_argument("--cards",  action="store_true", help="Show full constraint deck (Oblique Strategies)")
    p.add_argument("--card",   action="store_true", help="Show today's constraint card")
    args = p.parse_args()
    if args.plain: USE_COLOR = False

    if args.cards:
        show_all_cards()
        return

    if args.card:
        s = state()
        constraint, annotation = pick_card(s, args.random)
        label = "Random constraint" if args.random else f"Session {s['handoffs']+1} constraint  ·  {datetime.date.today()}"
        show_card(constraint, annotation, label)
        return

    s = state()
    if args.all: show_all_questions(s); return
    question = pick_question(s, args.random)
    label = "Random question" if args.random else f"Today's question  ·  {datetime.date.today()}"
    show_question(question, label)

if __name__ == "__main__": main()
