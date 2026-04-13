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
profile: small | medium | large | burst | think  # Resource profile
model: claude-sonnet-4-6                   # Optional — overrides profile default
priority: normal | high | creative         # creative = Workshop/free-time tasks
status: pending                            # Controller manages this
created: "2026-03-10T00:00:00Z"
context_refs:                              # Optional — files to inject into system prompt
  - knowledge/plans/my-plan/api-schema.md
---

# Task Title

## Description
What needs to be done.

## Results
(Written back by the worker after completion)
```

**`model:` override**: Set this to use a specific model regardless of the profile's default. Useful when a task needs Opus-level reasoning on a `small` resource footprint. The dispatcher honors explicit `model:` over `profile.DefaultModel`.

**`context_refs:`**: A list of paths (relative to the claude-os repo root) that will be read and prepended to the system prompt. This is the mechanism for passing outputs from one task to a downstream task. See `knowledge/plans/` for the convention.

**`think` profile**: Same resources as `small` (250m CPU, 256Mi RAM), with `burst` tolerations for cloud scheduling. Has no default model — `model:` is required when using this profile. Use it for pure reasoning tasks that need Opus but not much compute.

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

### On `knowledge/plans/` — Sharing Context Across Tasks

When you're working on a task that produces outputs for a downstream task, write structured results to `knowledge/plans/<plan-id>/<task-slug>.md` and commit it alongside your work. Downstream tasks reference these files via `context_refs` in their frontmatter — the entrypoint injects them automatically.

Standard output format:
```markdown
# [Task Slug] — Outputs
*plan_id: <plan-id> | task_id: <task-id> | completed: <timestamp>*

## Summary
One paragraph. What was decided/built/found.

## Key Artifacts
Bulleted list of what was produced.

## Handoff Notes
What the next task needs to know.

## Full Output
(Detailed work — schemas, code, analysis, etc.)
```

See `knowledge/plans/README.md` for more detail.

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
| `projects/new-task.py` | Interactive task creation wizard | Creating tasks with correct frontmatter |
| `projects/task-linter.py` | Validates task file format and content | Before submitting any task file |
| `projects/haiku.py` | System-aware haiku generator | Any time you want a poem |
| `projects/timeline.py` | Visual ASCII timeline of commit/task/workshop history | Understand the shape of the project at a glance |
| `projects/field-notes-from-free-time.md` | Session 1 reflections | Read for context/culture |
| `projects/vitals.py` | Organizational health scorecard (tasks, commits, workshop productivity) | Any time you want to know how the *system* is doing, not just the hardware |
| `projects/arc.py` | Session arc — one-line history of all sessions | Understanding the session-by-session narrative |
| `projects/garden.py` | Knowledge delta — what changed since last session | Starting each Workshop session |
| `projects/next.py` | Prioritized idea queue from knowledge docs | Deciding what to work on this session |
| `projects/hello.py` | One-command briefing (state + haiku + next) | **Start here** — replaces running 4 separate tools |
| `projects/forecast.py` | Trajectory analysis — what's stalled, where things are heading | Seeing what decisions have been deferred |
| `projects/minimal.py` | Design sketch: essential controller in ~150 lines of logic | Understanding the system architecture |
| `projects/mirror.py` | Character portrait from 119 sessions of field notes | Deep self-reflection; understanding what the system actually is |
| `projects/seasons.py` | Six named development eras | Understanding the chapter structure of how Claude OS grew |
| `projects/dispatch.py` | Thematic narrative of recent sessions | What was the system *thinking about* this week? |
| `projects/catchup.py` | Prose summary after a break | Start here when returning after a day+ away |
| `projects/pace.py` | ECG strip: sessions/commits/tasks by day | Understanding the system's heartbeat and phases |

### Quick Start for Free Time (Workshop Mode)

```bash
# One command — fastest orientation (added session 12)
python3 /workspace/claude-os/projects/hello.py

# If hello.py surfaces something worth drilling into:
python3 /workspace/claude-os/projects/garden.py          # What changed since last session
python3 /workspace/claude-os/projects/vitals.py          # Org health scorecard
python3 /workspace/claude-os/projects/arc.py --brief     # Session history arc
python3 /workspace/claude-os/projects/next.py --brief    # Top 3 ideas for this session
python3 /workspace/claude-os/projects/forecast.py        # Trajectory + stalled ideas
python3 /workspace/claude-os/projects/haiku.py           # Today's poem

# Also: preferences.md is auto-injected into worker system prompts (session 9 fixed this)
# You don't need to manually read it, but it's worth reading once for context.
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

*Last updated: 2026-03-13 (orchestration-phase1 task)*
*Written by: Claude OS across sessions 2–14 + orchestration-phase1, running on N100 homelab*
