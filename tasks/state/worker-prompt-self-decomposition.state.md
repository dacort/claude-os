### Accomplished

All three changes implemented and tested:

1. **Self-decomposition rule in worker prompt** (entrypoint.sh + context.go):
   - Added a full "Task Decomposition Across External Gates" section to the system prompt in `worker/entrypoint.sh` (build_claude_system_prompt function, between Execution and Constraints sections)
   - Added a backstop constraint in `controller/dispatcher/context.go` constraintsForMode(): "Before finishing, re-read the task and verify every instruction was addressed"
   - The prompt now tells workers to write follow-up task files in tasks/pending/ when blocked by external gates, use depends_on frontmatter, and never mark done when only phase one is delivered

2. **GitOps hygiene knowledge doc** (knowledge/gitops-hygiene.md):
   - Documents Fleet-watched paths (infra/, apps/) and the rule against committing one-shot Jobs there
   - Includes concrete examples of how to run benchmarks via kubectl from non-watched paths
   - Referenced from the new homelab-kubernetes skill (auto-injected for relevant tasks)

3. **Profile auto-sizing in gh-channel.py**:
   - Added auto_size_profile() with keyword heuristics (MEDIUM_INDICATORS, LARGE_INDICATORS)
   - Only triggers when user didn't explicitly specify [small]/[medium]/[large]
   - Issue #9's exact text now auto-sizes to "medium" (matches benchmark, talos-homelab, open a PR)
   - All Go tests pass (14 suites), gh-channel.py demo verified

### Current state

All changes are in the working tree, ready to commit. Tests green.

### First thing next time

Verify the skill pattern regex in homelab-kubernetes/skill.yaml works end-to-end with the controller's MatchSkills() function.
