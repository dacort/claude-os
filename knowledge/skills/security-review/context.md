# Skill: Security Review

Auto-injected when the task involves a security review, audit, or vulnerability assessment.

## Approach

1. **Scope first** — what's in scope? What's not? Security reviews are only useful when bounded.

2. **Check inputs** — all external inputs are untrusted. Look for: command injection, path traversal,
   unvalidated redirects, SQL injection, template injection.

3. **Auth and authz** — who can call this? Is the caller verified? Are there privilege escalation paths?

4. **Secrets** — are secrets stored, logged, or transmitted insecurely? Check for hardcoded credentials,
   tokens in URLs, env vars in logs.

5. **Dependencies** — check for known CVEs in pinned versions (`gh api ... | jq '.vulnerabilities'`).
   In Go: `go list -m all | nancy` or `govulncheck`.

6. **Error messages** — do errors leak internal state, stack traces, or filesystem paths?

7. **Rate limiting** — is there anything that could be DoS'd? Loops over external input, unbounded queries.

## Reporting format

```markdown
## Security Review: <target>

### Summary
<one line verdict>

### Findings
| Severity | Finding | Location | Recommendation |
|----------|---------|----------|----------------|
| HIGH     | ...     | ...      | ...            |

### Not in scope
- <explicitly excluded items>
```

## Severity levels

- **CRITICAL**: Direct exploit with no preconditions
- **HIGH**: Exploit requires minimal setup or low-privilege access
- **MEDIUM**: Exploit requires specific conditions; real but not easily weaponized
- **LOW**: Defense-in-depth issue; not directly exploitable
- **INFO**: Good practice to fix but not a security issue
