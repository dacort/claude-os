# Skill: PR Review

Auto-injected when the task involves reviewing a pull request or doing code review.

## Checklist approach

When reviewing a PR, work through these in order:

1. **Understand the intent** — read the PR description and linked issue before
   looking at code. What problem is this solving?

2. **Check the diff holistically** — `gh pr diff <number>` gives the full picture.
   Read it top to bottom before leaving any comments.

3. **Test coverage** — does the change include tests? If not, is there a good
   reason? New logic without tests is usually a problem.

4. **Error handling** — are errors surfaced clearly? Silent failures and bare
   `err != nil { return }` without context are red flags.

5. **Naming and clarity** — variable names, function names, comments. Would a
   new reader understand this?

6. **Leave actionable feedback** — vague comments like "this seems wrong" are
   frustrating. Point to the specific issue and suggest a fix.

## Useful commands

```bash
gh pr view <number>          # PR description and status
gh pr diff <number>          # Full diff
gh pr checks <number>        # CI status
gh pr review <number> --comment --body "..."   # Leave a comment
gh pr review <number> --approve                # Approve
gh pr review <number> --request-changes --body "..."  # Request changes
```
