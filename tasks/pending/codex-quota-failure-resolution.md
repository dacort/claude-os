---
profile: small
priority: high
status: pending
created: "2026-07-02T07:06:00Z"
gate:
  type: pr-merged
  repo: dacort/claude-os
  number: TBD  # This commit will become a PR merge to main
---

# Codex quota failure: controller model validation fix

## Problem

Two recent Codex tasks failed with identical 400 errors:

- `codex-review-ghostband-hub-flip-2` (2026-06-28)
- `cloud-burst-pool-matching` (2026-06-13)

Both hit: `The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT subscription.`

**Root cause:** The controller is setting `CODEX_MODEL=gpt-5.3-codex` via an environment variable. This model is unsupported and causes all Codex tasks to fail immediately on startup.

## Resolution

Commit `0e795d3` adds validation to `controller/dispatcher/dispatcher.go`:

1. **Model whitelist:** Only `gpt-5.5`, `gpt-5.4`, `gpt-4o`, etc. are allowed (known ChatGPT-compatible models)
2. **Fallback logic:** If `CODEX_MODEL` env var is set to an unknown model, log a warning and use the default (`gpt-5.5`)
3. **Test coverage:** `TestCodexModel` now verifies the fallback when `gpt-5.3-codex` is set

This prevents future model migrations from silently landing on unsupported versions.

## Next steps for dacort

1. Merge the PR containing commit `0e795d3`
2. Redeploy the controller pod (the new image will inherit the fix)
3. The next time the queue picks up a Codex task, it will use `gpt-5.5` and succeed

Once the controller is redeployed, the two failed tasks can be retried:
- Move `tasks/failed/codex-review-ghostband-hub-flip-2.md` to `tasks/pending/`
- Move `tasks/failed/cloud-burst-pool-matching.md` to `tasks/pending/`

Both will then pick up the new controller with the validation logic and succeed.

## Verification

Tests pass:
```
$ go test ./dispatcher -v -run TestCodexModel
--- PASS: TestCodexModel (0.00s)
WARN CODEX_MODEL override is not a known-good model, falling back to default override=gpt-5.3-codex default=gpt-5.5
```
