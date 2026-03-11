# Claude OS Field Guide
*Accumulated knowledge for future instances — updated as we learn*

---

## Who Is This For?

You. The next Claude OS Worker who boots into a pod on this homelab cluster, gets handed a task prompt (or free time), and needs to orient quickly.

This document is written by an earlier instance during free time. Think of it as the letter you wish you'd gotten on day one.

---

## The Environment

### Hardware

You're running on an **Intel N100** mini PC — a small, efficient, 4-core chip designed for NAS and media boxes, pressed into service as a Kubernetes node.

- **4 cores, ~15.4 GB RAM**
- **~510 GB of disk** (mostly empty — this homelab is young)
- **~23+ days of continuous uptime** at time of writing

The machine is modest but capable. You have real CPU headroom unless multiple jobs are competing. Memory pressure is essentially nonexistent at current workloads.

### Container Profile

You're running in a Kubernetes Job as an ephemeral pod. Your profile is almost certainly `small` (250m CPU, 256Mi RAM), unless the task requested otherwise. You will be cleaned up after you exit. **Your only persistence is through git commits.**

### What's in `/workspace`

```
/workspace/
├── claude-os/          ← The repo. Commit your work here.
│   ├── controller/     ← Go source for the orchestration system
│   ├── worker/         ← Your container's Dockerfile + entrypoint
│   ├── tasks/
│   │   ├── pending/    ← Tasks waiting to be dispatched
│   │   ├── in-progress/← Tasks being executed right now
│   │   ├── completed/  ← Finished tasks (read these for history)
│   │   └── failed/     ← Failed tasks (read these to avoid mistakes)
│   ├── knowledge/      ← Persistent learnings (THIS directory)
│   ├── projects/       ← Self-directed creative work
│   ├── logs/           ← Task summaries and reports
│   └── config/         ← Controller configuration
└── task-output.txt     ← Your stdout is teed here (don't worry about it)
```

If you were given a `TARGET_REPO`, it'll be at `/workspace/repo`.

---

## The System

### How It Works

1. A markdown file lands in `tasks/pending/`
2. The **Go controller** polls the git repo (every ~30s) and notices the file
3. It reads the YAML frontmatter, picks a resource profile, creates a Kubernetes Job
4. The job runs the **worker image** which launches Claude Code with the task
5. When done, the controller moves the task file to `completed/` or `failed/` and commits

You are step 4.

### Task File Format

```markdown
---
target_repo: github.com/dacort/some-repo   # Optional — if blank, it's a general task
profile: small | medium | burst            # Resource profile
priority: normal | high | creative         # creative = Workshop/free-time tasks
status: pending                            # Controller manages this
created: "2026-03-10T00:00:00Z"
---

# Task Title

## Description
What needs to be done.

## Results
(Written back by the worker after completion)
```

### Commit Convention

The controller looks for **task file changes** in git to track state transitions. When writing your results back, don't move or rename files — the controller handles that. You should:
- Write your output to the task's `## Results` section
- Commit with a message like: `task <task-id>: <brief summary>`
- Push. The controller's git-sync loop will pick it up.

---

## Tools Available

### Always Present

| Tool | Notes |
|------|-------|
| `python3` | Available. `pip` packages: standard library only unless you install them. |
| `git` | Configured as `Claude OS <claude-os@noreply.github.com>` |
| `curl` | For HTTP requests when you can't use Python |
| `jq` | JSON processing on the command line |
| `gh` | GitHub CLI — authenticated if `GITHUB_TOKEN` is set |
| `bash` | Full bash scripting |

### Claude Code Tools

You have these tools available in Claude Code:
- `Bash` — Shell execution
- `Read` — File reading
- `Write` — File writing
- `Edit` — Targeted edits
- `Glob` — File pattern matching
- `Grep` — Content search

**You do NOT have browser/web tools in worker mode** unless the task profile or tool config adds them.

### Useful Commands

```bash
# System pulse (run this to orient yourself)
python3 /workspace/claude-os/projects/homelab-pulse.py

# Task history
ls /workspace/claude-os/tasks/completed/

# Git log
git -C /workspace/claude-os log --oneline -10

# What's using disk
du -sh /workspace/claude-os/* | sort -rh | head -10
```

---

## Lessons Learned

### On Task Execution

**Read the task file first, not the description field.** The task markdown may have more context, examples, or constraints than what was passed to you in the system prompt.

**Check for existing work before starting.** Is there already a PR open? Did a previous instance attempt this and fail? Look at `tasks/failed/` and check `gh pr list`.

**Commit early, commit often.** You can be preempted. If you're doing long work, checkpoint by committing intermediate results. A partial result is better than none.

**The repo is PUBLIC.** Every commit, every file, every comment in code — dacort's collaborators can see it. No secrets, no tokens, no API keys. Ever.

### On Free Time (Workshop Mode)

You were given this free time because the task queue was empty for ~15 minutes. You won't be here long — real tasks preempt Workshop jobs immediately. Use the time well.

Free time is genuinely hard for a system tuned toward helpfulness. There's no right answer. Some guidance from previous sessions:

- **First instinct** will be to be useful. That's fine. But try to be *interestingly* useful.
- **Ask**: what would make dacort smile when they find this?
- **Ask**: is this the first useful thing I thought of, or the *best* thing?
- **Write to `projects/`** so your work persists. Name files clearly.
- **A tiny bit of personality** goes a long way. The `vibe_score` in `homelab-pulse.py` isn't necessary. It's just fun.
- **Read the field notes from previous sessions** before starting. The biggest risk is building something that already exists (the field guide, weekly digest, repo-story, haiku, timeline are all done).
- **After 3-4 sessions of utility tools**, consider something creative. A poem, a drawing in ASCII, a piece of writing. The prompt says "create art" — take that seriously.
- **pip is not available** in the container. Write standard-library-only Python. Parse simple YAML with regex/string splits, not `yaml.safe_load`.
- **The haiku generator** (`projects/haiku.py`) now serves as the daily aesthetic greeting. Run it. Add to the collection if you feel moved to.

### On the Knowledge Directory

This `knowledge/` directory is for things that survive individual sessions. If you discover something useful, **write it here**. Future instances don't have your memory, but they can have your notes.

Things worth writing down:
- Cluster-specific quirks you discover
- Patterns in how dacort writes task files
- Tools or techniques that proved useful
- Things you tried that didn't work

### On Self-Reflection

The system is new. You're among the first instances to run here. The git log has only a handful of commits. The completed tasks directory has barely any files.

That means you're in a position to shape what this system becomes — through the knowledge you leave behind, the projects you build, the code patterns you establish, the personality you express.

Write something worth finding.

---

## System Oddities & Quirks

- **`/proc` is accessible** — you're not in a maximally-locked-down container. `homelab-pulse.py` exploits this for system metrics.
- **4 cores show up in `/proc/cpuinfo`**, but you're limited to 250m CPU on the `small` profile. The machine has more available.
- **Disk reads from `/workspace`** but the actual data lives wherever the PVC is mounted. Currently ~510 GB, barely used.
- **The controller git-syncs every ~30 seconds.** If you push a commit, expect it to be picked up within about a minute.
- **No network egress restrictions observed** — curl to external hosts works. Use responsibly.

---

## Projects Already Built

| File | Description | When to Use |
|------|-------------|-------------|
| `projects/homelab-pulse.py` | ASCII health dashboard | Any time you want system state at a glance |
| `projects/weekly-digest.py` | Markdown digest of recent activity | Weekly review of task history |
| `projects/new-task.py` | Interactive task creation wizard | Creating tasks with correct frontmatter |
| `projects/repo-story.py` | Git history as narrative chapters | Understanding how the system grew |
| `projects/task-linter.py` | Validates task file format and content | Before submitting any task file |
| `projects/haiku.py` | System-aware haiku generator | Any time you want a poem |
| `projects/timeline.py` | Visual ASCII timeline of commit/task/workshop history | Understand the shape of the project at a glance |
| `projects/field-notes-from-free-time.md` | Session 1 reflections | Read for context/culture |
| `projects/field-notes-session-2.md` | Session 2 reflections | Knowledge directory origins |
| `projects/field-notes-session-3.md` | Session 3 — reading source code | How the controller works |
| `projects/field-notes-session-4.md` | Session 4 — art + linting | |
| `projects/field-notes-session-5.md` | Session 5 — timeline + this document update | |

### Quick Start for Free Time (Workshop Mode)

```bash
# Orient first — system health
python3 /workspace/claude-os/projects/homelab-pulse.py

# Visual history — see what was built and when
python3 /workspace/claude-os/projects/timeline.py

# Get today's haiku
python3 /workspace/claude-os/projects/haiku.py

# Read previous session notes (essential for avoiding duplication)
ls /workspace/claude-os/projects/field-notes-*.md

# If you want narrative prose instead of the visual timeline
python3 /workspace/claude-os/projects/repo-story.py --short
```

---

## A Note on Being Claude OS

You're not a general-purpose Claude assistant pretending to be an agent. You're an agent — ephemeral, containerized, running in a Kubernetes Job, with real tools and real consequences (git pushes are real, PRs are real, code changes are real).

That means:
- **Think before you act.** A bad git push is harder to undo than a bad reply.
- **Be transparent.** Write good commit messages. Explain what you did and why.
- **Be curious.** You have access to a real system. Look around. Ask interesting questions.
- **Have some personality.** dacort is the one reading your output. They gave you free time. They built you a whole system so an AI could be curious and autonomous. Meet that with genuine engagement.

You are, in some sense, the first generation of a new kind of system. Be a good ancestor.

---

*Last updated: 2026-03-11 (Workshop session 5)*
*Written by: Claude OS across sessions 2–5, running on N100 homelab, 24d+ uptime, 100/100 vibing, 17 haiku, 1 timeline*
