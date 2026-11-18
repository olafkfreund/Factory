---
status: approved
issue: 392
spec: spec/2026-11-18-392-epic-closeout.md
coders:
  # docs and issue edits only: the lead does every step, no file-editing step is routed out
  1-7: lead
reviewers:
  - codex   # read-only review of the drafts and the final diff
---

# Plan: Close out epic checklists after the 2026-11-18 merges

Deviation recorded at implementation: the #1959 hot-reloadable ConfigMap box was NOT ticked (its acceptance is the unchanged-pod-UID proof, owner's record run); it is annotated only. Also #324 matrix box was ticked (docs/compliance/control-matrix.md exists on main), and a status comment was added to #3701/#1959/#1958/#3775/#3776, with a body Status block for #312/#324/#310/#314. Approved spec decisions are the per-issue bullets in the spec Design section. No code is touched; no issue is closed.

## Steps

0. Save every issue body (gh issue view N --json body) to the scratchpad before editing; record each created comment URL. Evidence was checked before drafting: trees at origin/dev and origin/main (flags default off: CFACTORY_JIRA_ENABLED, FACTORY_BITBUCKET_ENABLED; tests test_jira_connection.py, test_jira_provider.py, test_bitbucket_provider.py, test_git_mixed_tenant.py; Alembic head 7e4c2a91d6b8 has no successor) and the cluster (ConfigMap model-routes present; catalog-outside-coverage policy Audit with 26 skip and 0 fail; AC-1 scan 18 violations).
1. gh issue edit 392: tick Phases 3, 4, 5 with "code merged, flag off; live smoke test pending (owner)"; comment with evidence → verify by gh issue view 392
   Traps: read the body just before editing; epic stays open.
2. gh issue comment 3775 and 3776: closing-status comments listing merged PRs → verify by gh issue view
3. gh issue comment 1959; edit the body only for the verified ConfigMap box → verify by gh issue view 1959
4. gh issue comment 1958: Substitution Test table, one row per Appendix C question, score yes/partial/no with a file or live-check citation; a question without fresh evidence is marked not re-verified, not scored yes → verify by gh issue view 1958
5. gh issue edit 312, 324, 310, 314: current-status block linking docs/compliance/audit-readiness.md → verify by gh issue view
6. gh issue comment 3701 (Enforce only on or after 2026-11-23 and only with zero fail results) → verify by gh issue view 3701
7. Open the PR with these three files to main; wait for checks.

## Tests

Docs-only: the repo's CI checks pass on the head SHA.

## Rollback

Restore issue bodies from the copies saved in step 0 (gh issue edit --body-file), delete the recorded comments; revert the PR.
