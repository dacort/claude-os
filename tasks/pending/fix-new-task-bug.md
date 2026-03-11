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
