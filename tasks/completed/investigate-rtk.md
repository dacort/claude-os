---
profile: small
priority: normal
status: pending
created: "2026-03-13T14:35:00Z"
---

# Investigate rtk (Rust Token Killer) for Claude OS

## Description
Research whether rtk (https://github.com/rtk-ai/rtk) would be useful for Claude OS workers or the brain session.

rtk is a tool that compresses context to reduce token usage. Setup is supposedly simple:
- `brew install rtk`
- `rtk init -g --hook-only`

Questions to answer:
1. What does rtk actually do? How does it compress/reduce tokens?
2. Would it help with our worker prompts? Our system prompts are already quite large (preferences injection, context_refs, etc.)
3. Would it help with the brain session (my-octopus-teacher) where we have long CLAUDE.md and memory files?
4. Does it work with Claude Code CLI (`claude -p`)? With Codex? With Gemini?
5. What's the tradeoff — does compression lose important context?
6. Is it worth adding to the worker Dockerfile?
7. Any security concerns with running it on our task content?

Read the repo README and source code. Give a clear recommendation: adopt, skip, or revisit later — with reasoning.

## Results

=== Claude OS Worker v2 ===
Task ID: investigate-rtk
Profile: small
Agent: claude
Started: 2026-03-13T16:03:05Z
Auth: Claude OAuth token (subscription)
Cloning claude-os repo for workspace access
Injecting preferences from knowledge/preferences.md
Running task via claude...
---
Now I have everything I need. Let me write up the full analysis.

---

## rtk (Rust Token Killer) — Analysis for Claude OS

**tldr up front:** **Skip for workers. Worth trying for the brain session.** Here's why:

---

### 1. What does rtk actually do?

It's a **CLI output proxy**, not a system prompt compressor. The mental model:

```
Without rtk: LLM runs `git status` → shell executes → raw output (2,000 tokens) goes back into context
With rtk:    LLM runs `git status` → hook rewrites to `rtk git status` → rtk filters output → compressed output (~200 tokens) goes into context
```

Four techniques per command type:
- **Smart filtering** — strips blank lines, boilerplate, decorative ASCII
- **Grouping** — "5 files in src/" instead of listing each
- **Truncation** — keeps failures, cuts passing tests
- **Deduplication** — collapses repeated log lines with counts

The magic is a **Claude Code `PreToolUse` hook** registered in `~/.claude/settings.json`. When the LLM issues a Bash tool call for `git status`, the hook intercepts it and rewrites it to `rtk git status` before execution. The LLM never sees the rewrite — it just gets compressed output back.

Claimed savings on a 30-minute session: **~118,000 → ~24,000 tokens (~80%)** for common dev ops.

---

### 2. Would it help with worker prompts?

**No, not the system prompt itself.** rtk compresses *command output* that accumulates during a session. It does nothing to the static system prompt that's passed via `--system-prompt` at invocation time.

Our worker system prompt is already ~3-4KB of text (autonomy model + preferences + context_refs). That's fixed overhead per run. rtk can't touch it.

What rtk *would* help: the **dynamic context** accumulated as a worker runs `git status`, `gh pr list`, `cargo test`, etc. during a task. For a typical worker that does 30-50 tool calls, that's real savings — but smaller than the benchmark suggests because workers run shorter sessions than the 30-minute coding example.

---

### 3. Would it help the brain session (my-octopus-teacher)?

**Yes, this is the sweet spot.** Interactive sessions with long CLAUDE.md and memory files are exactly the use case. The long static context is already loaded — what rtk reduces is the *accumulating dynamic context* as you code across a long session.

In a 30-minute session where you run `git diff` 5× and `cargo test` 3×, that's potentially 10,000+ tokens saved per session. The hook is transparent and the setup is two commands. This is worth trying.

---

### 4. Does it work with `claude -p`? With Codex? With Gemini?

**`claude -p` (workers):** The hook should technically work — it's a `PreToolUse` hook in `~/.claude/settings.json`, which applies to all Claude Code invocations, headless or interactive. But workers use `--allowedTools "Bash,Read,Write,Edit,Glob,Grep"`, and the worker container starts fresh each time with no pre-configured `~/.claude/settings.json`. You'd need to run `rtk init -g --hook-only` in the Dockerfile or `entrypoint.sh` to set it up.

**Codex:** No integration. There's an OpenCode plugin, but Codex CLI is unrelated to OpenCode.

**Gemini:** No integration.

So it's Claude-only, which already limits its value for the multi-agent worker setup.

---

### 5. Does compression lose important context?

**Sometimes, yes — and the project knows this.** The "tee" feature is their mitigation: when a command fails, rtk saves the full unfiltered output to disk and tells the LLM where to find it. So a failing `cargo test` shows "FAILED: 2/15 tests" + a hint to read the full log.

The risk is: the LLM might misinterpret compressed output and miss an edge case, then not realize it needs the full log. Specific concerns:

- `rtk read file.rs -l aggressive` — shows only function signatures, strips bodies. Bad for debugging.
- `rtk git diff` — "condensed diff" could hide context needed for complex merge conflicts.
- `rtk git push` → "ok main" — this is fine, you don't need the 15-line counting-objects output.

For simple operations (git add/commit/push, `ls`, `docker ps`), compression is safe. For debugging (test failures, build errors), the tee fallback helps but adds a round-trip.

---

### 6. Is it worth adding to the worker Dockerfile?

**Not yet.** Here's the practical issue:

The worker image is Debian-based (no brew). Installation would be:
```bash
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
```
...plus `rtk init -g --hook-only` in `entrypoint.sh` to register the hook before `claude -p` runs.

This adds:
- ~10MB to the Docker image (Rust binary, statically linked musl)
- A network fetch at build time from a relatively new project (created Jan 2026)
- Hook setup that only benefits the `claude` agent path, not codex or gemini
- A dependency on an external project that's 7 weeks old (fast-moving, could break)

The payoff is modest for short-lived task workers. The project claims 80% savings on a 30-minute session — a worker running for 5 minutes and 20 tool calls would see proportionally less.

---

### 7. Security concerns?

**Low-to-moderate, manageable.** The key things:

**What it does with your data:**
- All filtering happens **locally** — no content leaves your machine
- Saves raw output to a local SQLite DB for tracking
- **Telemetry** exists but is disabled by default — `TELEMETRY_URL` is an `option_env!()` compile-time constant, meaning it's only active if compiled with that env var set. The Homebrew/install.sh binary: unknown whether telemetry is compiled in. To be safe: `RTK_TELEMETRY_DISABLED=1` kills it. Even if enabled, it only sends: device hash, version, OS, command counts/savings stats — not actual content.

**What the hook does:**
- It's a `PreToolUse` hook that intercepts every Bash command the LLM tries to run
- The hook script is thin (~50 lines of bash) — it delegates to `rtk rewrite` for the actual rewrite logic
- All rewrite rules are in `src/discover/registry.rs` — auditable Rust, no network calls

**Supply chain:**
- Project is 7 weeks old (created 2026-01-22) with 7,001 stars — fast growth, not a red flag in itself but warrants attention
- The `rtk` name conflicts with "Rust Type Kit" on crates.io — the README warns about this explicitly
- MIT license, active maintainer (@FlorianBruniaux)
- No unexpected network calls in the source code

**Bottom line on security:** The code is clean and auditable. The telemetry concern is real but opt-out-able. For task content (commit messages, code), none of it leaves the machine. The main concern is that it's a young project with a hook that intercepts all shell commands — worth auditing before adding to production worker containers.

---

### Recommendation

| Context | Verdict | Reasoning |
|---------|---------|-----------|
| **Worker Dockerfile** | **Skip** | Short-lived containers, multi-agent (not just Claude), adds build complexity for modest return on typical 5-10 min tasks |
| **Brain session (my-octopus-teacher)** | **Adopt (try it)** | Interactive, long sessions — exactly the target use case. Low setup cost, transparent hook, real savings. |
| **`claude -p` headless** | **Revisit later** | Technically works but needs hook setup in the container. Worth testing once brain session is validated. |
| **Codex / Gemini workers** | **Skip** | No integration |

**One-line take:** rtk is a solid tool that solves the right problem for interactive coding sessions. For Claude OS workers, the problem it solves (verbose command output) is real but secondary — the bigger cost driver is system prompt size, which rtk can't touch. Try it in your brain session first; if it survives there, revisit the worker Dockerfile.
---
=== Worker Complete ===
Exit code: 0
Finished: 2026-03-13T16:05:15Z

