# Secure SDLC Policy

- **Policy owner:** Security Owner (CISO function) — see [roles.md](../roles.md)
- **Applies to:** All source and infrastructure changes to the six fleet repositories
- **Review cadence:** Annually, and on any change to the CI/CD or branch-protection model
- **Frameworks:** ISO/IEC 27001:2022 A.8.25-.32; SOC 2 CC8.1; SOX ITGC (change
  management, SoD); NIST CM-3/CM-4/CM-5, AC-5

Control detail and current-state grounding live in
[change-management-sod.md](change-management-sod.md) (Factory#316),
[supply-chain-integrity.md](supply-chain-integrity.md) (Factory#318), and
[vuln-patch-management.md](vuln-patch-management.md) (Factory#317).

## Purpose

To ensure changes to fleet code and infrastructure are reviewed, tested, scanned, and
provably built before they reach production, and that no single actor can unilaterally
ship an unreviewed change.

## Scope

All commits, pull requests, CI/CD workflows, container builds, and gitops deployments
across `Factory`, `PFactory`, `AIFactory`, `TFactory`, `CFactory`, and `factory-gitops`.

## Policy statements

1. **Change lands via reviewed pull request.** Direct pushes to `main` on protected
   repositories are prohibited; every change is a PR with at least one approving review.
   Branch protection is defined as code (see
   [branch-protection.md](../branch-protection.md), Factory#316) and applied across the
   fleet repositories. Repositories not yet protected (historically `Factory`,
   `AIFactory`, `factory-gitops`) are tracked to closure in the change-management domain.
2. **CI security gates are mandatory and fail-closed.** A PR does not merge unless the
   required checks pass: Ruff plus pytest, and the Trivy P0 supply-chain gate
   (`test_p0_supply_chain.py`, fail-closed on HIGH/CRITICAL, `--ignore-unfixed`). CodeQL
   runs per PR and weekly on all five code repositories.
3. **Code ownership.** `CODEOWNERS` defines the required reviewers per repository.
   Coverage is being completed for repositories currently missing it (`Factory`,
   `CFactory`, `factory-gitops`).
4. **Provenance on release.** Released images are signed with cosign keyless signing
   (Sigstore + GitHub OIDC, no custody key) and ship a dual SBOM (Syft SPDX and
   CycloneDX), attached as attestations and to the GitHub Release; the release pipeline
   self-verifies the signature. CFactory is being brought to parity (Factory#318).
5. **Independent verification.** Agent-produced changes are independently verified by
   TFactory against evidence gates (RFC-0001a) and Verification Assurance Levels
   (RFC-0006) before the output is trusted for merge.
6. **Separation of duties.** The intent is that authoring, approving, and deploying a
   privileged change are not all performed by one identity. The current push-to-main
   auto-deploy path and single-owner `CODEOWNERS` weaken this; strengthening it (deploy
   approvals, four-eyes via the built-but-unwired Fides change-gate, signed commits) is
   tracked in the change-management domain and recorded as risk R-005.
7. **Dependencies are managed.** Renovate keeps dependencies current across the repos;
   the Trivy gate blocks known-vulnerable additions. A remediation SLA by severity is a
   tracked gap (Factory#317).
8. **Reproducible builds.** Builds pin inputs (`flake.lock`, lockfiles, digest-pinned
   base images) so a build is reproducible and its inputs are auditable.

## Roles and responsibilities

- **Contributors** — raise changes as PRs, keep them green, and do not bypass gates
  (`--no-verify` local commits still face CI).
- **Reviewers / code owners** — review for correctness and security before approving.
- **Control owner (change management)** — maintains branch protection, CI gates, and
  drives the SoD and signed-commit improvements.
- **Security Owner** — approves exceptions and owns the policy.

## Related controls

- [change-management-sod.md](change-management-sod.md), [branch-protection.md](../branch-protection.md)
- [supply-chain-integrity.md](supply-chain-integrity.md), [vuln-patch-management.md](vuln-patch-management.md)
- [risk-register.md](../risk-register.md) — R-005 (weak SoD / auto-deploy)
