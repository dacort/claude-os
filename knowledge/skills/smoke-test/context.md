# Skill: Smoke Test & Validation

Auto-injected when the task is to validate, confirm, or smoke-test a component.

## What a smoke test is

A smoke test verifies that the basic paths work — it's not exhaustive. The goal
is: "does this thing function at all?" not "is every edge case handled?"

## Checklist

1. **Define success criteria first** — write down what "passing" looks like before
   you start. A test without a clear pass condition is just exploration.

2. **Test the happy path** — verify the normal, expected usage works end to end.

3. **Test obvious failure modes** — empty input, invalid config, missing auth.

4. **Check logs/output** — even if no error is thrown, check that the output is
   what you expect, not just "no crash."

5. **Document what you tested** — in the task output, list each thing tested and
   the observed result.

## For context contracts (claude-os specific)

When validating a context contract:
```bash
cat /workspace/task-context.json | jq .         # Inspect the full envelope
jq -r '.task.title' /workspace/task-context.json  # Specific field
```

Check: task_id present, profile matches, context_refs resolve, constraints non-empty if expected.

## Output format

```markdown
## Smoke Test Results

| Test case       | Expected       | Observed  | Status |
|-----------------|----------------|-----------|--------|
| Happy path      | X              | X         | PASS   |
| Missing auth    | Error 401      | Error 401 | PASS   |
```
