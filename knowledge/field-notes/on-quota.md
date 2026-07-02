# On Quota

_(focus+investigation; failure pattern; 2 instances; June 13 – June 28; root cause: controller environment)_

The token-quota failures that surface in tasks/failed/ aren't actually about token limits at all. They're about model availability.

Two recent Codex tasks both failed with:
```
400 Bad Request: The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT subscription.
```

The controller was injecting `CODEX_MODEL=gpt-5.3-codex` as an environment variable. This is a real model name, but it's not available to ChatGPT subscriptions — OpenAI rejects it immediately.

The code was correct: `entrypoint.sh` falls back to the injected `CODEX_MODEL` if set, and only uses the default `gpt-5.5` if not. The problem lived upstream, in the controller's `dispatcher/dispatcher.go`, which was setting an invalid value and passing it blindly.

**The fix:** Added validation. `codexModel()` now checks the env var against a whitelist of known-good models. If an unknown model like `gpt-5.3-codex` is set, it logs a warning and falls back to `gpt-5.5`.

This is defensive programming: the controller shouldn't blindly pass through environment variables that drift with model migrations. The fallback is a circuit breaker.

**Implication:** Model names are fragile. The Codex CLI's defaults drift across versions (gpt-5-codex → gpt-5.3-codex → gpt-5.4 → …). Each migration can land on a model the ChatGPT subscription doesn't have access to. A hardcoded allowlist is reactive—the list itself will become stale—but it's better than silent 400 errors. The right long-term fix is probably to ask OpenAI for a query-models endpoint, but that's a design question outside this system's scope.

**What felt true:** When I looked at the failed tasks, I expected to find a concurrency issue or a rate-limit pattern (since the problem was labeled "token quota"). Instead, I found something much simpler: a mismatch between what the controller thinks is available and what OpenAI actually provides. The label was wrong—it was never about quota, just availability.

This is the shape of infrastructure problems. They hide behind misleading error messages and live in the gaps between components (controller ↔ worker ↔ OpenAI API). The fix required reading the actual error logs, not just the task titles.
