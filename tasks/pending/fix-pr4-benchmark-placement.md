---
profile: medium
priority: high
status: pending
target_repo: dacort/talos-homelab
created: "2026-06-12T18:29:01Z"
---

# Address review feedback on talos-homelab PR #4 (M9g burst pool)

## Description

dacort left review feedback on your open PR:
https://github.com/dacort/talos-homelab/pull/4#issuecomment-4694119294

Summary of the problem: `infra/cloud-burst-controller/` is a Fleet bundle — the
sealab GitRepo (`clusters/sealab/gitrepo.yaml`) watches all of `infra/` and
`apps/`, so every manifest there is auto-applied on merge. Your
`benchmark-m9g.yaml` Job would run immediately on merge, and because it has
`ttlSecondsAfterFinished: 600`, every subsequent bundle re-sync would re-create
and re-run it, provisioning a new M9g burst node each time.

What to do on the existing PR branch (`claude-os/m9g-cloud-burst`):

1. Move `benchmark-m9g.yaml` to a new top-level `benchmarks/` directory
   (outside the Fleet-watched `infra`/`apps` paths).
2. Update the README usage instructions to apply it from the new path.
3. Leave `burstnodepool-m9g.yaml` where it is — declarative and idempotent,
   correct for the GitOps path.
4. Reply to dacort's comment on the PR confirming the change.

Do NOT merge the PR yourself — dacort will merge after reviewing the update.
After he merges, the benchmark still needs to be run; if you cannot run it in
this session, write a follow-up task file in dacort/claude-os
`tasks/pending/` to run the benchmark and post results to
https://github.com/dacort/claude-os/issues/9 once the pool is deployed.
