---
profile: small
priority: low
status: pending
created: "2026-03-11T05:04:45Z"
---

# Fix new task bug

## Description
There's a bug in the interactive mode of the new_task script. 
projects/new-task.py", line 115, in <genexpr>
    c(f"[{c}]", BOLD) if c == default else f"[{c}]"
    ~^^^^^^^^^^^^^^^^
TypeError: 'str' object is not callable

## Results

=== Claude OS Worker ===
Task ID: fix-new-task-bug
Profile: small
Started: 2026-03-11T05:05:11Z
Auth: OAuth token (subscription)
Cloning claude-os repo for workspace access
Running task via Claude Code...
---
Fixed. Here's a summary of what was done:

---

## Bug Fix: `new-task.py` interactive mode — `TypeError: 'str' object is not callable`

**Root cause:** In `prompt_choice()` (line 114–117), the generator expression used `c` as the loop variable:

```python
# BEFORE (broken)
for c in choices
```

This **shadowed the module-level `c()` color-formatting function**, so when the code tried to call `c(f"[{c}]", BOLD)` to highlight the default option, `c` was already rebound to the current string from `choices` — hence the `TypeError: 'str' object is not callable`.

**Fix:** Renamed the loop variable from `c` to `choice` to avoid the collision:

```python
# AFTER (fixed)
options = "  ".join(
    c(f"[{choice}]", BOLD) if choice == default else f"[{choice}]"
    for choice in choices
)
```

Now `c()` (the ANSI helper) and `choice` (the loop variable) are distinct, and the interactive profile/priority selection works correctly.
---
=== Worker Complete ===
Exit code: 0
Finished: 2026-03-11T05:05:37Z

