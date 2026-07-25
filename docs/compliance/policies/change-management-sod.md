# Change Management and Separation of Duties

- **Domain:** Change management & SoD (Factory#316)
- **Parent epic:** Factory#310
- **Frameworks addressed:**
  - ISO/IEC 27001:2022 — Annex A A.8.32 (change management), with A.8.31 (separation of development/test/production) and A.5.4 (management responsibilities)
  - SOC 2 — CC8.1 (authorized, tested, approved changes)
  - SOX ITGC — change-management controls (authorization, testing, approval, segregation between developer and deployer) — the critical framework for this domain
  - PCI DSS v4.0 — 6.5.x (change control for system changes; separation of duties between dev/test and production)
  - FedRAMP / NIST 800-53 — CM family (CM-3 configuration change control, CM-4 impact analysis, CM-5 access restrictions for change), plus AC-5 (separation of duties)
  - FFIEC — development & acquisition booklet (change control, promotion to production)

## Purpose

This document describes how changes to the Factory fleet's source, configuration, and
running systems are authorized, tested, reviewed, and promoted to production, and how
duties are separated so that no single actor can unilaterally introduce and deploy a
change without independent control. It covers all six repositories
(`Factory`, `PFactory`, `AIFactory`, `TFactory`, `CFactory`, `factory-gitops`) and the
GitOps/ArgoCD path from a merged commit to a running workload.

It is an assessor-facing artifact. It credits the fleet's genuinely strong CI and
independent-verification design, and it is honest that the *controls an auditor tests*
— branch-protection-as-code, required code-owner review, signed commits, and a formal
deploy approval with segregation of duties — are partly configured, unevenly applied,
and in the highest-risk paths absent. Engineering maturity here runs ahead of the
auditable enforcement.

## Current state (grounded)

As of 2026-07-24, verified against GitHub branch-protection APIs, in-repo CODEOWNERS and
workflow files, and the ArgoCD application manifests in `factory-gitops`.

### Pull-request and review flow

- **Protected repos (3 of 6):** `PFactory`, `TFactory`, `CFactory` have branch
  protection on `main` with required status checks and `required_approving_review_count = 1`.
  PFactory/TFactory require the checks `backend (ruff + pytest)` and `critical (fast PR gate)`;
  CFactory requires `Backend pytest`.
- **Unprotected repos (3 of 6):** `Factory`, `AIFactory`, and `factory-gitops` return
  HTTP 404 `Branch not protected`. Notably **AIFactory — the service that writes
  AI-generated code — has no branch protection at all** on `main`, and `factory-gitops`
  (the deploy source of truth, below) is likewise unprotected.
- **Review is nominal, not enforced:** on all three protected repos
  `require_code_owner_reviews = false`, `enforce_admins = false`, `dismiss_stale_reviews = false`,
  and `require_last_push_approval = false`. A single approving review is required but it
  need not come from a code owner, admins bypass protection, and approvals survive new
  pushes. `strict = false`, so a PR need not be up to date with `main` before merge.

### CI gates (credited)

- **`.github/workflows/ci.yml`** in PFactory/AIFactory/TFactory/CFactory runs Ruff +
  large backend pytest suites (AIFactory ~2400 tests), Helm lint, and kubeconform on
  every PR. `AIFactory/guides/compliance/soc2-evidence.md` CC8.1 documents this as the
  change-related control.
- **Code-quality ratchet / drift gates** — `cq-ratchet.yml`, `factory-github-drift.yml`,
  `factory-ui-drift.yml`, `verification-core-drift.yml`, `cq-factory-common-drift.yml`
  keep shared code and vendored contracts from silently diverging.
- **CodeQL** (`codeql.yml`) runs fleet-wide.
- **Independent verification exists but is not a required check.** TFactory verification
  (builder != verifier) is real and posts a commit status via
  `TFactory/.github/workflows/pr-review-tests.yml`, and AIFactory/PFactory run
  `pr-review.yml` / `copilot-plan-review.yml` review gates. However, TFactory verify is
  **not in any repo's `required_status_checks` list** — so the independent-verification
  separation is advisory at the GitHub-merge boundary, not merge-blocking.
- **RFC-0009 CI-gated auto-merge** (`Factory/docs/pipeline-and-guards.md`) specifies
  merge only on green + required checks + approvals + an assurance floor. This is a sound
  design, but it is driven by the PARR conductor / task services, not by a GitHub-native
  auto-merge workflow or by branch-protection settings — so it is a process control, not
  a platform-enforced one.

### CODEOWNERS

- Present in `PFactory`, `AIFactory`, `TFactory` (identical files). Absent in `Factory`,
  `CFactory`, and `factory-gitops`.
- Every path — including `/.github/`, `Dockerfile`, `/scripts/` — maps to a **single
  owner, `@dataseeek`**. With one owner, "separation" of review is nominal: the same
  identity authors and owns everything, and (given `require_code_owner_reviews = false`)
  is not even required to review.

### Fides change-gate and segregation-of-duties approvals

- A full compliance/provenance system, **Fides**, exists and provides exactly the
  controls this domain needs: a `fides change-gate` that turns evidence + control
  coverage into an approve/HOLD verdict plus a 0-100 risk score (exit 2 = HOLD blocks the
  deploy step), a four-eyes `fides approve --trail <id>` requiring two distinct humans
  (segregation of duties), ServiceNow Change Request write-back
  (`fides servicenow change-check`), and an auditor artifact (`fides audit --output`).
- **It is not wired into any Factory repo.** No workflow in any of the six repositories
  invokes `fides change-gate`, `fides approve`, or emits a Fides trail. The capability is
  available and documented; the integration is the gap. Credit the tool, not its use.

### Deploy / GitOps flow (the core SoD exposure)

- Deploy is fully continuous. `AIFactory/.github/workflows/deploy.yml` (mirrored in
  PFactory/TFactory) fires on **every push to `main`**, builds an immutable image, pushes
  to GHCR, and **commits an image-tag bump directly to `factory-gitops`** using a
  `GITOPS_PAT`, as `github-actions[bot]` (unsigned).
- `factory-gitops` is committed **directly to `main` with no branch protection**, and the
  ArgoCD `Application` manifests (`apps/*/application.yaml`, `bootstrap/argocd-root-app.yaml`)
  set `syncPolicy.automated` with `prune: true` and `selfHeal: true`. A merged tag bump
  therefore reconciles to the live p510 cluster with **no human deploy approval and no
  gate** anywhere between merge and production.
- Net effect on separation of duties: a single actor who can merge to an app repo (admins
  bypass protection; code-owner review not required; the same identity owns CODEOWNERS)
  triggers an automatic, unsigned, self-healing deploy to production. There is no distinct
  deployer role and no production change-approval checkpoint.

### Commit signing

- `required_signatures.enabled = false` on all three protected repos and unset on the
  unprotected three. No workflow signs commits or verifies signatures. The automated
  gitops bump is an unsigned bot commit. Commit provenance is therefore unverifiable — an
  auditor cannot cryptographically attribute a change to an authorized author.

### What is credited

Strong CI (lint + large test suites + Helm/kubeconform + CodeQL + drift ratchets),
independent TFactory verification, a documented RFC-0009 merge discipline, CODEOWNERS on
the three core service repos, and a fully capable but unintegrated Fides change-gate /
four-eyes approval system.

## Gaps

1. **Branch protection is not code (and is missing on the two highest-risk repos).**
   Protection lives only in GitHub settings, is absent on `AIFactory` (the code-writer)
   and `factory-gitops` (the deploy source), and where present has `enforce_admins = false`,
   `require_code_owner_reviews = false`, and `strict = false`. There is no in-repo,
   version-controlled, auditable definition of the ruleset. (SOX ITGC, CM-5, CC8.1)
2. **No signed commits / no signature verification** anywhere in the fleet, including the
   automated gitops deploy commit. Change authorship is not cryptographically provable.
   (CM-5, PCI 6.5, SOX)
3. **No formal deploy approval and weak separation of duties.** Deploy fires on push to
   `main` and ArgoCD auto-syncs with `selfHeal`; there is no distinct deployer role and no
   production approval checkpoint. One actor can author, self-approve (owner review not
   required, admin bypass), merge, and auto-deploy. (AC-5, CC8.1, SOX ITGC, PCI 6.5.4,
   CM-3)
4. **Direct-to-main GitOps with no protection or gate.** `factory-gitops` accepts
   unprotected direct commits and ArgoCD reconciles them automatically to production —
   the single largest change-control exposure. (CM-3, CC8.1)
5. **Independent verification is advisory, not required.** TFactory verify is not in any
   `required_status_checks` list, so builder-!=-verifier is not enforced at merge. (CC8.1)
6. **No change-approval / CAB record linkage.** The Fides change-gate + four-eyes approval
   + ServiceNow write-back exist but are not invoked; prod changes are not traceable to an
   auditable approval record. (CC8.1, SOX ITGC, FFIEC)
7. **Single-owner, incomplete CODEOWNERS.** One owner (`@dataseeek`) for all paths defeats
   review separation; `Factory`, `CFactory`, `factory-gitops` have no CODEOWNERS at all.
   (AC-5, CC8.1)

## Remediation plan

Phased; each phase is independently shippable and leaves the fleet auditable at a higher
level than before.

**Phase 1 — Close the platform gaps (branch protection + review as enforced controls).**

- Enable branch protection on `AIFactory` and `factory-gitops` to match the other repos,
  then harden all six: set `enforce_admins = true`, `require_code_owner_reviews = true`,
  `required_approving_review_count >= 1`, `strict = true`, and `require_last_push_approval = true`.
- Add TFactory verify (and the relevant `pr-review` gate) to `required_status_checks` so
  independent verification is merge-blocking.
- Add CODEOWNERS to `Factory`, `CFactory`, `factory-gitops`, and split ownership so at
  least one reviewer is distinct from the typical author (retire single-owner-for-all).

**Phase 2 — Branch-protection-as-code.**

- Define each repo's ruleset declaratively (GitHub rulesets JSON or a Terraform
  `github_branch_protection` / `github_repository_ruleset` module) committed under
  `factory-gitops` or a new `Factory/infra/github/`. Reconcile drift in CI (fail if live
  protection != committed spec). This makes the control itself auditable and versioned.

**Phase 3 — Signed commits + verification.**

- Require signed commits (`required_signatures = true`) once contributors and the CI bots
  have signing keys. Sign the automated gitops deploy commit (bot GPG/SSH key or Sigstore
  gitsign) and add a verify-signatures gate to CI. Pair with the existing cosign image
  signing so both source and artifact are attributable.

**Phase 4 — Formal deploy approval + segregation of duties.**

- Insert a production gate between merge and ArgoCD sync. Options, cheapest first:
  (a) GitHub Environments with required reviewers on the deploy job, giving a distinct
  approver from the author; or (b) wire the existing **Fides change-gate** into
  `deploy.yml` (`fides change-gate --trail $TRAIL` before the gitops bump — exit 2 HOLDs
  the deploy) with `fides approve` four-eyes for production and ServiceNow write-back for
  the CAB record. Reuse Fides rather than building new approval machinery.
- Consider gating `factory-gitops` prod paths behind ArgoCD manual sync (drop `selfHeal`
  for prod overlays) or an ArgoCD sync window, so production reconciliation requires an
  explicit action by a deployer role distinct from the merger.

**Phase 5 — Change-record traceability.**

- Emit a Fides trail per change and publish `fides audit --output trail-audit.zip` as a
  build artifact, so every production change links to its approval, evidence, and risk
  verdict. Document the developer / reviewer / deployer role split in the roles register
  (Governance & ISMS, Factory#311).

## Acceptance criteria

- [ ] All six repositories have branch protection on `main` with `enforce_admins = true`,
      `require_code_owner_reviews = true`, `strict = true`, and at least one required
      approval.
- [ ] `AIFactory` and `factory-gitops` are no longer returning `Branch not protected`.
- [ ] Branch-protection rulesets for every repo are defined as code, committed, and
      drift-checked in CI.
- [ ] `required_signatures = true` fleet-wide; contributors and CI bots sign commits; a CI
      gate verifies signatures, including the automated gitops deploy commit.
- [ ] TFactory independent verification is a required status check on the app repos
      (builder != verifier enforced at merge).
- [ ] CODEOWNERS exists in all six repos with ownership split so the required reviewer can
      be distinct from the author.
- [ ] A production deploy approval exists (GitHub Environment required reviewers and/or
      Fides change-gate) such that no single actor can both merge and deploy to production
      unreviewed.
- [ ] Every production change is traceable to an auditable approval record (Fides trail +
      audit artifact, optionally ServiceNow CR).
- [ ] `factory-gitops` production paths require an explicit deployer action or approval
      before ArgoCD reconciles them (no unattended selfHeal-to-prod on an unprotected
      commit).

## Evidence artifacts

- Branch-protection state (live): `gh api repos/olafkfreund/<repo>/branches/main/protection`
  for each of the six repos.
- Required-review config: `.../protection/required_pull_request_reviews` per repo.
- CODEOWNERS: `PFactory/CODEOWNERS`, `AIFactory/CODEOWNERS`, `TFactory/CODEOWNERS`.
- CI gates: `<repo>/.github/workflows/ci.yml`, `cq-ratchet.yml`, `codeql.yml`,
  `*-drift.yml`, `pr-review.yml`, `pr-review-tests.yml`, `copilot-plan-review.yml`.
- Deploy / GitOps flow: `AIFactory/.github/workflows/deploy.yml` (and PFactory/TFactory
  equivalents); `factory-gitops/apps/*/application.yaml` and
  `factory-gitops/bootstrap/argocd-root-app.yaml` (`syncPolicy.automated`, `selfHeal`).
- Merge discipline (design): `Factory/docs/pipeline-and-guards.md` (RFC-0009 auto-merge).
- Change-control narrative: `AIFactory/guides/compliance/soc2-evidence.md` CC8.1,
  `AIFactory/guides/compliance/iso27001-evidence.md`.
- Fides change-gate / SoD approvals (available, to be wired): `fides` skill —
  `reference/pipelines.md` (change-gate exit-code contract, four-eyes `fides approve`,
  ServiceNow write-back, `fides audit`).
- Commit-signing state: `required_signatures.enabled` per repo (currently `false`).
