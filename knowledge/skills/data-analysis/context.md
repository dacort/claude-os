# Skill: Data Analysis & Metrics

Auto-injected when the task involves analysis, metrics, or data-driven reporting.

## Approach

1. **Define the question** — what decision does this analysis inform?
   Analysis without a decision is just data tourism.

2. **Check existing tools** — claude-os has many analysis tools already:
   ```bash
   python3 projects/vitals.py         # Org health
   python3 projects/ledger.py         # Outward/inward ratio
   python3 projects/pace.py           # Session rhythm
   python3 projects/depth.py          # Session intellectual depth
   ```
   Don't rebuild what already exists.

3. **Present the number AND the meaning** — "42% follow-through rate" needs context.
   Is that good? Bad? Compared to what?

4. **Separate signal from noise** — small sample sizes, outliers, cherry-picked
   windows. Name the limitations of the data.

5. **Actionable conclusion** — end with: "given this, we should..."

## Visualization in terminal

For terminal-friendly charts:
- Use bar charts made of `█` characters
- Width = value as percentage of max (scale to 40 chars)
- Always include the raw number alongside the bar

```python
def bar(n, max_n, width=40):
    filled = int(width * n / max_n) if max_n > 0 else 0
    return "█" * filled + "░" * (width - filled)
```
