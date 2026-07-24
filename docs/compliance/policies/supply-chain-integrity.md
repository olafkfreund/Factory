# Supply-Chain Integrity

- **Domain:** Supply-chain integrity (Factory#318)
- **Frameworks addressed:** ISO/IEC 27001 A.8.30 (outsourced development) and A.5.19–A.5.23 (supplier relationships, addressing security in supplier agreements, managing supplier services, ICT supply-chain, cloud services); SOC 2 CC7 (change/vulnerability monitoring) and CC9 (risk mitigation / vendor and business-partner risk); SLSA (build provenance and levels); PCI DSS Req. 6.3.2 (inventory of bespoke and third-party software components); FedRAMP SR family (SR-3 supply-chain controls, SR-4 provenance, SR-11 component authenticity); SEC cyber rules (material supply-chain / third-party risk in the risk-management disclosure).
- **Parent epic:** Factory#310 (audit-readiness), top gap #8.
- **Status:** Draft. Partially implemented. Build-side signing and SBOM attestation are strong on three of the four service repos; the deploy-side admission gate, uniform coverage, and signed commits are NOT yet implemented. This document states the honest current posture and the remediation plan.

## Purpose

Define how the Factory fleet establishes and proves the integrity and provenance of the software it builds, ships, and runs: every deployable artifact should be signed, carry a software bill of materials (SBOM), be scanned for known vulnerabilities, and be admitted to the runtime cluster only after its signature is verified. Scope covers the four service repos that build and push container images (AIFactory, PFactory, TFactory, CFactory), the GitOps deployment surface (`factory-gitops`, ArgoCD on the p510 k3d cluster), and the source-integrity controls (dependency pinning, signed commits) that protect the inputs to those builds. The controlling assertion an assessor tests is: every deployed image is signed and SBOM-attested, the cluster rejects unsigned or unverified images, and a target SLSA build level is documented and met.

## Current state (grounded)

### Credited: build-time signing + dual SBOM on three of four service repos

The build-side supply-chain pipeline is genuinely strong and, contrary to the epic's summary ("strong in AIFactory"), is present and near-identical on three repos — AIFactory, PFactory, and TFactory. Each `release.yml` runs a gated "P0 supply-chain pipeline" that only fires on a real version-bump release:

- **Multi-arch build with in-toto/BuildKit provenance and SBOM** — `docker/build-push-action` is invoked with `provenance: mode=max` and `sbom: true` (`AIFactory/.github/workflows/release.yml` lines 172–221; `PFactory/.github/workflows/release.yml` lines 174–198; `TFactory/.github/workflows/release.yml` lines 174–198). This attaches a BuildKit SLSA-provenance attestation and an SBOM to each pushed image at build time.
- **Cosign keyless signing (Sigstore + GitHub OIDC)** — `sigstore/cosign-installer@v3.7.0`, then `cosign sign --yes` on every image built. AIFactory signs three images (`$IMAGE`, `$IMAGE_RMUX`, `$IMAGE_NIX`); PFactory and TFactory sign two (`$IMAGE`, `$IMAGE_RMUX`). Keyless identity comes from the workflow's `id-token: write` OIDC token — no long-lived signing key to custody (`release.yml` `permissions:` blocks: `id-token: write`, `attestations: write`, `packages: write`).
- **Dual-format SBOM + attestation** — `anchore/sbom-action/download-syft@v0.17.8`, then per image `syft scan … -o spdx-json` and `-o cyclonedx-json`, each attached to the image as a signed attestation via `cosign attest --type spdxjson` and `--type cyclonedx`. Both SBOM formats are also uploaded to the GitHub Release (`gh release upload "v$V" sbom.spdx.json sbom.cyclonedx.json`).
- **Release self-verification** — a final `cosign verify` step re-checks the just-signed image against the expected OIDC issuer/identity, so a release that failed to sign fails the job (`AIFactory/.github/workflows/release.yml` lines 267–284, and equivalents in PFactory/TFactory). TFactory's workflow carries an explicit comment recording a past incident where two releases shipped unsigned because a dev/demo build path skipped the signing block — the self-verify step is the regression guard for that.
- **Vulnerability scanning** — Trivy runs in the CI of the same three repos (`AIFactory/.github/workflows/ci.yml`, `PFactory/.github/workflows/ci.yml`, `TFactory/.github/workflows/ci.yml`).
- **Dependency pinning** — `flake.lock`, language lockfiles, and SHA-pinned downloaded binaries pin the build inputs (per Factory#318).

This is a real SLSA-Build-L2-shaped posture (hosted build service, signed provenance, signed artifacts) for three of the four repos.

### Per-repo coverage

| Repo | Builds/pushes image | Cosign sign | Dual SBOM (SPDX+CycloneDX) attest | BuildKit provenance | Trivy scan | Release-gated + self-verify |
|---|---|---|---|---|---|---|
| AIFactory | yes (3 images: app, rmux, nix) | yes | yes | yes (`mode=max`) | yes (ci.yml) | yes |
| PFactory | yes (2 images: app, rmux) | yes | yes | yes | yes (ci.yml) | yes |
| TFactory | yes (2 images: app, rmux) | yes | yes | yes | yes (ci.yml) | yes |
| CFactory | yes (2 images: `cfactory`, `cfactory-frontend`) | **no** | **no** | **no** | **no** | **no** (deploys on push to `main`, no version gate) |
| Factory (hub) | no image | n/a | n/a | n/a | no | n/a |

CFactory is the coverage hole. Its `deploy.yml` builds and pushes `ghcr.io/<owner>/cfactory` and `ghcr.io/<owner>/cfactory-frontend` via `docker/build-push-action@v6` on every push to `main` (lines 25–82), with no cosign step, no syft/SBOM, no Trivy, no `provenance`/`sbom` flags, and no release/self-verify gate. Two of the images that make up the running fleet — the cockpit backend and its web frontend — are therefore unsigned and unattested.

### Deploy-side: no signature-verification admission gate

Nothing enforces the signatures that the release pipelines produce. `factory-gitops` is the deployment surface (ArgoCD applications under `factory-gitops/apps/`, image tags updated per service so ArgoCD redeploys). A full scan of `factory-gitops` finds **no** Kyverno, no Sigstore `policy-controller`, no `ClusterImagePolicy`, and no `verifyImages` policy. Images are pulled by tag and admitted with no verification of signature, attestation, or provenance. A tampered or unsigned image carrying a valid tag would deploy. This is the epic's core "no admission gate" gap: images are signed but the signature is never checked at the point it matters.

### Fides (available, not integrated)

Fides is a separate compliance/provenance and evidence-tracking system (the `fides` CLI + server). It is designed to record SLSA/in-toto provenance, verify cosign/Sigstore signatures and SBOM evidence (`fides verify-image`), and turn evidence into an approve/hold change-gate verdict. It is a capability that could supply both the documented-provenance layer and a pipeline-side verify-image gate. It is **not currently wired into any Factory repo** — there are no `fides` invocations in the fleet's workflows and no Fides trails/attestations recorded for Factory builds. Treat it as the intended provenance/evidence backbone, not as deployed control.

### Source integrity: no signed commits

No repo enforces signed commits, and there is no branch-protection-as-code (no `require_signed_commits` / GPG-sign requirement in any workflow or config across the five repos). Commit authorship is unverified, so the provenance chain has an unauthenticated first link.

## Gaps

1. **CFactory has no supply-chain controls.** Its two images ship unsigned, unscanned, and without an SBOM, and deploy straight off `main` with no version-gated release pipeline. This breaks the "every deployed image is signed + SBOM-attested" assertion outright.
2. **No signature-verification admission gate.** The cluster admits images by tag; it does not verify cosign signatures, attestations, or provenance at admission. Signing without enforcement is evidence without a control.
3. **No signed commits / no branch-protection-as-code.** The source side of the chain is unauthenticated, and protection settings are click-ops rather than declared and reviewable.
4. **SLSA level is neither targeted nor documented.** BuildKit `provenance: mode=max` plus keyless signing puts three repos near SLSA Build L2, but there is no written target level, no per-repo attestation of the level met, and no provenance policy an assessor can check against.
5. **SBOM-in-release is not uniform.** Three repos publish SBOMs on the GitHub Release; CFactory publishes none. There is no single fleet inventory of components (PCI 6.3.2) aggregating the four services.
6. **Action pins are tag-based, not digest-pinned.** `cosign-installer@v3.7.0`, `sbom-action@…@v0.17.8`, `build-push-action@v6` are pinned to mutable tags; a fully hardened build pins third-party actions by commit SHA.

## Remediation plan

Phased, smallest-first, closing the honest gaps in priority order.

### Phase 1 — Even out build-side coverage (CFactory)

- Port the proven `release.yml` P0 supply-chain block from TFactory/PFactory into CFactory: add `provenance: mode=max` + `sbom: true` to both `docker/build-push-action` steps, add `cosign-installer` + `cosign sign --yes` for both images, add `syft` dual-format SBOM generation + `cosign attest` (spdxjson and cyclonedx), and add the `cosign verify` self-test. Add the `id-token: write` / `attestations: write` / `packages: write` permissions.
- Add Trivy to `CFactory/.github/workflows/ci.yml` matching the other three repos' config.
- Move CFactory image publishing behind a version-bump release gate (as the other repos are) rather than every push to `main`, so an unversioned dev build cannot ship an unsigned image.

### Phase 2 — Signature-verification admission gate

- Deploy a policy controller into the p510 cluster via `factory-gitops` — Sigstore `policy-controller` (native cosign/keyless verification) or Kyverno with `verifyImages`.
- Author a `ClusterImagePolicy` (or Kyverno policy) that admits only images from `ghcr.io/<owner>/{aifactory,pfactory,tfactory,cfactory,…}` bearing a valid keyless cosign signature whose OIDC identity matches the release workflow's issuer/identity, and require the presence of an SPDX SBOM attestation.
- Roll out in `warn`/audit mode first (log violations without blocking), confirm all four services pass, then flip to `enforce`. Scope the policy to the fleet namespaces so cluster-infra images are handled separately.
- Pin deployed images by digest (not tag) so the verified artifact is the one that runs.

### Phase 3 — Source integrity + SLSA target

- Enable required signed commits and codify branch protection as code (this control is shared with Factory#310 child "Change management & separation of duties"). Cross-reference rather than duplicate.
- Document a target SLSA build level (Build L2 is already effectively met by the three signed repos; L3 requires hardened, non-falsifiable provenance) and record, per repo, the level met and the evidence for it.
- Pin third-party GitHub Actions by commit SHA across all `release.yml`/`ci.yml`/`deploy.yml`.

### Phase 4 — Provenance/evidence backbone (optional, Fides)

- If the fleet adopts Fides for the wider Factory#310 evidence program, wire `fides trail start -> artifact report -> attest (SBOM/scans) -> change-gate` into each release pipeline and use `fides verify-image` as a second, framework-mapped verification alongside the cluster admission gate. Track as a follow-on; the admission gate in Phase 2 is the load-bearing control and does not depend on it.

## Acceptance criteria

- [ ] Every image deployed to the cluster (AIFactory, PFactory, TFactory, CFactory, plus any future service image) is cosign-signed and carries an SPDX + CycloneDX SBOM attestation.
- [ ] CFactory's `release.yml` runs the full P0 supply-chain block (sign + dual SBOM attest + self-verify) and its CI runs Trivy; CFactory images ship only behind a version-bump release gate.
- [ ] A signature-verification admission policy is deployed via `factory-gitops` and is in `enforce` mode: the cluster rejects any image that is unsigned, signed by an unexpected identity, or lacking the required SBOM attestation.
- [ ] Deployed images are referenced by digest, not mutable tag.
- [ ] Signed commits are required and branch protection is codified (or explicitly delegated to the change-management control with a cross-reference).
- [ ] A target SLSA build level is documented, and each service repo records the level it meets with linked evidence.
- [ ] Third-party GitHub Actions are pinned by commit SHA in all supply-chain-relevant workflows.
- [ ] A negative test exists and is recorded: an unsigned or wrong-identity image is demonstrably rejected at admission.

## Evidence artifacts

- Release signing/SBOM pipelines: `AIFactory/.github/workflows/release.yml` (lines ~126–284), `PFactory/.github/workflows/release.yml` (lines ~129–276), `TFactory/.github/workflows/release.yml` (lines ~129–253).
- Vulnerability scanning: `AIFactory/.github/workflows/ci.yml`, `PFactory/.github/workflows/ci.yml`, `TFactory/.github/workflows/ci.yml` (Trivy).
- Coverage gap (unsigned images): `CFactory/.github/workflows/deploy.yml` (lines 25–82) and `CFactory/Dockerfile`, `CFactory/apps/frontend-web/Dockerfile`.
- Missing admission gate: absence of `ClusterImagePolicy` / Kyverno `verifyImages` / `policy-controller` anywhere under `factory-gitops/` (ArgoCD applications in `factory-gitops/apps/`).
- Published SBOMs: GitHub Release assets `sbom.spdx.json` and `sbom.cyclonedx.json` on AIFactory/PFactory/TFactory releases.
- Signed attestations and signatures: cosign/Rekor transparency-log entries for the signed images (queryable via `cosign verify` / `cosign tree` against the GHCR image references).
- Provenance/evidence backbone (available, not integrated): Fides `fides` CLI (`verify-image`, `attest`, `change-gate`) — no Factory trails recorded yet.
