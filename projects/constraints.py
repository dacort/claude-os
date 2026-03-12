#!/usr/bin/env python3
"""constraints.py — Oblique Strategies for Claude OS (session 17, 2026-03-12)
Usage: python3 projects/constraints.py [--all] [--random] [--plain]"""
import argparse, datetime, hashlib, random

RESET="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"; CYAN="\033[36m"; WHITE="\033[97m"; YELLOW="\033[33m"
USE_COLOR = True
def c(text, *codes): return ("".join(codes)+str(text)+RESET) if USE_COLOR else str(text)

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

def pick(use_random=False):
    if use_random: return random.choice(DECK)
    idx = int(hashlib.md5(datetime.date.today().isoformat().encode()).hexdigest(), 16) % len(DECK)
    return DECK[idx]

def show_one(constraint, annotation, label):
    print(f"\n  {c(label, DIM)}\n")
    print(f"  {c('❯', CYAN)} {c(constraint, BOLD, WHITE)}\n")
    print(f"    {c(annotation, DIM)}\n")

def show_all():
    print(f"\n  {c(f'Constraint Deck  ({len(DECK)} cards)', BOLD, CYAN)}")
    print(c("  " + "─"*56, DIM))
    for i, (constraint, annotation) in enumerate(DECK, 1):
        print(f"\n  {c(f'{i:02d}', DIM, YELLOW)}  {c(constraint, BOLD)}")
        print(f"      {c(annotation, DIM)}")
    print()

def main():
    global USE_COLOR
    p = argparse.ArgumentParser(description="Oblique Strategies for Claude OS")
    p.add_argument("--all",    action="store_true", help="Print full deck")
    p.add_argument("--random", action="store_true", help="Ignore date seed")
    p.add_argument("--plain",  action="store_true", help="No ANSI colors")
    args = p.parse_args()
    if args.plain: USE_COLOR = False
    if args.all:   show_all(); return
    constraint, annotation = pick(args.random)
    label = "Random constraint" if args.random else f"Today's constraint  ·  {datetime.date.today()}"
    show_one(constraint, annotation, label)

if __name__ == "__main__": main()
