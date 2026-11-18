---
status: draft
issue: 1958
intent: intent/2026-11-18-1958-runbook-skills.md
---

# Spec: runbook skills for TFactory and CFactory

## Design

One thin skill per repo, like the two references: frontmatter (`name`, `description`,
`when_to_use`), then a short ordered procedure that points at the repo's own source of
truth and states the verification and rollback. Sources:

- TFactory: `.github/workflows/release.yml` (tag, GitHub release, images, cosign, SBOM
  when `package.json` version changes on `main`), `.github/workflows/deploy.yml` (sha
  image, cosign sign and verify, `assert-signature-location.sh`, gitops bump of
  `apps/tfactory/manifests` incl. `TFACTORY_IMAGE`, seam-check),
  `.github/workflows/deploy-drift.yml`, `scripts/bump-version.js`, CONTRIBUTING.md
  branching (`dev` to `main` promotion), chart probe `/api/health`. The skill states
  that `release.yml` and `deploy.yml` are the truth where RELEASE.md differs, and the
  stale RELEASE.md text is corrected in the same PR.
- CFactory: RELEASE.md (already a faithful description of `deploy.yml`) and
  `deploy.yml`, `deploy-drift.yml`, `guides/deployment.md`, chart probe `/health`.
  CFactory has no versions, tags or releases; the skill says so.
- Rollback for both: revert or re-pin the image SHA in `factory-gitops`
  (`apps/<svc>/manifests`) and let Argo CD reconcile; this is the operator's action.
- Verification: `gh run` for the deploy and seam-check, `cosign verify` with the
  workflow's identity regexp and issuer, `git grep` of the pinned SHA in
  factory-gitops, read-only `kubectl -n factory get deploy` and `/api/health` or
  `/health`.
- CFactory AGENTS.md is read against RELEASE.md and fixed only if they disagree.
- No lint exists for `.claude/skills` content, so verification is a frontmatter and
  link check script run by hand plus the existing TFactory skills tests.

## Alternatives rejected

- Copy the workflows into the skill: duplicates and drifts. Point at the files.
- Do Q3 in this round: it touches the hub, four services and a CI gate; filed as a
  child issue with design (report-only first; flip to enforcing after two clean weeks
  of drift runs on `main` in all four repos).
- Add a new skill lint: not asked; the reference skills have none.

## Risks

A skill that restates a workflow can go stale. Mitigated by pointing at file paths,
not copying logic, and by keeping command lines to ones taken from the workflows.

## Verification

Each cited path and command exists (grep check), frontmatter parses, existing tests
(`tests/test_skills*.py` in TFactory, CFactory `just test`) still pass, CI green.
