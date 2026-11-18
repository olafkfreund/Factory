---
status: draft
issue: 1958
spec: spec/2026-11-18-1958-runbook-skills.md
coders:
  1: lead (contained doc edit, needs the facts read from the workflows)
  2: lead
  3: lead
  4: lead
  5: lead
reviewers:
  - codex   # read-only review of each draft and of the final diff; agy is off by owner decision
---

# Plan: runbook skills for TFactory and CFactory

Decisions carried from the spec: one thin skill per repo (frontmatter plus ordered
procedure that points at workflow and doc paths, no copied logic); TFactory follows
`release.yml` and `deploy.yml` where RELEASE.md differs, and RELEASE.md is corrected;
CFactory follows RELEASE.md and `deploy.yml`; rollback is a `factory-gitops` image
re-pin by the operator; verification commands are read-only; Q3 is deferred to a child
issue with the design. Repos: TFactory and CFactory on `dev`, artifacts in Factory
`main`.

## Steps

1. `TFactory/.claude/skills/tfactory-deploy-runbook/SKILL.md` (new): sections
   release (bump-version.js, CHANGELOG `## <version>` gate, PR to `dev`, promotion to
   `main`, auto tag and GitHub release, signed images and SBOM), deploy (push to
   `main`, `sha-<short>` image, cosign, gitops bump incl. `TFACTORY_IMAGE`,
   seam-check, `FACTORY_TOKEN`, `GITOPS_PAT` and `GHCR_PAT` (or package write for `GITHUB_TOKEN`) are
   operator secrets), the release gates (CHANGELOG `## <version>` entry, unused tag,
   non-empty release notes), the 30-minute deploy-drift watchdog (hub workflow), verification
   (incl. reading the seam-check step result, since it is `continue-on-error`) and rollback
   (re-pin the deployment image AND `TFACTORY_IMAGE`). Check: every cited path exists (grep script), frontmatter parses,
   `pytest tests/test_skills.py tests/test_skills_routes.py tests/test_tfactory_routes_skills.py tests/test_well_known_agent_skills.py`.
   Traps: do not claim a manual tag step; never print secrets.
2. `TFactory/RELEASE.md`: replace the manual tag and `gh release create` steps and the
   `develop` branch wording with what `release.yml` does and the `dev` to `main` flow;
   link the skill. Check: `git diff` read against `release.yml`.
   Traps: keep the file otherwise intact; root `*.md` is in deploy `paths-ignore`.
3. `CFactory/.claude/skills/cfactory-deploy-runbook/SKILL.md` (new): promotion PR
   dev to main, what `deploy.yml` does (test gate, two images, Trivy, cosign, SBOM,
   gitops bump, seam-check), the `GHCR_PAT`/`GITOPS_PAT`/`FACTORY_TOKEN` prerequisites,
   deploy-drift, rollback of BOTH images (backend and frontend), no versions or tags, verification, copilot `cred-sync`
   post-deploy check, rollback per RELEASE.md. Check: path grep script, frontmatter.
   Traps: CFactory has no `.claude/` dir; `.gitignore` must not ignore it.
4. `CFactory/AGENTS.md`: read against RELEASE.md and `deploy.yml`; edit only if
   inconsistent; known candidate: line 48 implies every push to `main` deploys, but
   `docs/**` and root `*.md` are `paths-ignore`d. Check: diff or "consistent" note in the PR.
5. Create the Q3 child issue in Factory with the design (hub `shared/mcp-allowlist.json`,
   per-agent-type `allowed_tools`, drift script, CI step, report-only start, flip after
   two clean weeks on `main` across four repos); comment on #1958 with the decision.
   Check: issue URL.

## Tests

- TFactory: the four skills tests above, expect pass.
- CFactory: `cd` repo, `just test` is unaffected by a markdown add; run
  `PYTHONPATH=apps/backend pytest -q tests/test_deploy_trigger_covers_baked_files.py`.
- Path-and-command check script over both skills, expect no missing path.
- CI checks green on each PR head.

## Rollback

Revert the PRs. No runtime, chart or workflow change, so nothing else to undo.
