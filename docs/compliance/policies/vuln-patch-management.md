# Vulnerability and Patch Management

- **Domain:** Vulnerability & patch management (Factory#317)
- **Frameworks addressed:** ISO 27001 A.8.8 (management of technical vulnerabilities), SOC 2 CC7.1 (vulnerability detection), PCI DSS 6.3 (identify/rank/patch vulnerabilities) & 11.3 (penetration testing), NYDFS 23 NYCRR 500.5 (penetration testing + vulnerability assessments), FedRAMP / NIST 800-53 RA-5 (vulnerability scanning) & SI-2 (flaw remediation).

## Purpose

Define how the Factory fleet finds, ranks, remediates, and evidences software vulnerabilities across source code, dependencies, and container images — with defined time-to-fix targets and independent testing. This policy governs the six repositories that make up the fleet: the `Factory` spec/contract hub and the five service repos (`PFactory`, `AIFactory`, `TFactory`, `CFactory`, `factory-gitops`).

## Current state (grounded)

The engineering posture is strong on automated scanning and supply-chain provenance, but coverage is uneven and there is no documented remediation SLA or penetration-testing program. The controls below are all live in CI today.

### Per-repo scanner coverage

| Repo | CodeQL (SAST) | Trivy (image/dep CVE) | Renovate (dep updates) | Cosign + SBOM | Notes |
|---|---|---|---|---|---|
| Factory (hub) | Yes | No | No | No | Spec/contract + docs; ships no container image, so no Trivy/SBOM by design. No Renovate — gap. |
| PFactory | Yes | Yes | Yes | Yes | Full stack. |
| AIFactory | Yes (security-and-quality pack) | Yes | Yes | Yes (3 image variants) | Reference implementation. |
| TFactory | Yes (custom barrier query pack + `actions`) | Yes | Yes | Yes | Strongest SAST config; also scans the system-under-test with Trivy during verification (`apps/backend/agents/dependency_review.py`). |
| CFactory | Yes | **No** | Yes | **No** | Cockpit UI. Missing image CVE scanning, SBOM, and image signing — the epic #310 gap #8. |
| factory-gitops | No | No | Yes | No | Manifests only; Renovate keeps pinned images current. |

Sources: `.github/workflows/codeql.yml` (all five code repos; weekly Monday cron + per-PR); `.github/workflows/ci.yml` and `release.yml` in PFactory/AIFactory/TFactory (`aquasecurity/setup-trivy`, `anchore/sbom-action`, `sigstore/cosign-installer`); `renovate.json` in PFactory/AIFactory/TFactory/CFactory/factory-gitops. No `dependabot.yml` exists in any repo (matches only appear under vendored `node_modules`); dependency automation is Renovate, not Dependabot.

### How the scanners gate

- **Trivy** runs as a P0 supply-chain test (`tests/docker/test_p0_supply_chain.py::test_trivy_no_high_critical`) that fails CI on any **fixable HIGH/CRITICAL** finding (`--severity HIGH,CRITICAL --ignore-unfixed`, asserted zero). Exceptions are an audited allow-list: every repo's `.trivyignore` carries exactly one entry — `CVE-2024-23342` (python-ecdsa Minerva) — with a documented not-applicable rationale (JWT is HS256/HMAC, EC signing path never invoked). Base images are Chainguard, digest-pinned, with `apk upgrade` clearing fixable HIGH/CRITICAL between digest bumps (`AIFactory/Dockerfile`).
- **CodeQL** analyses `python` and `javascript-typescript` on every PR and weekly. TFactory replaces GitHub default setup with a custom barrier-aware path-injection query pack (`.github/codeql/codeql-config.yml`) so verified-safe code clears, and additionally analyses the `actions` language.
- **SBOM + signing** (PFactory/AIFactory/TFactory release): Syft emits dual SPDX + CycloneDX; cosign keyless (Sigstore + GitHub OIDC) signs each image and attests both SBOM formats.

### CVE remediation history (evidence of a working loop)

- Base-image CVE bump: Chainguard Python digest `d45c16a1` -> `369768c6` to clear a Trivy P0 (2026-06-24).
- Copilot-cache CVE: Trivy HIGHs from a bundled `@github/copilot` / foundry-local-sdk subtree were removed at the source (#971, closed); copilot is never run at build time.
- CodeQL path-injection hardening: custom barrier pack drove remediation across 19 files (#565).

## Gaps

1. **Uneven supply-chain coverage — CFactory.** CFactory has CodeQL + Renovate but no Trivy image scan, no SBOM, and no cosign signing. Its container image ships to the cluster unscanned and unsigned. (Epic #310 gap #8.)
2. **No documented remediation SLA.** Trivy gates fixable HIGH/CRITICAL at build, but there is no written, tracked time-to-fix per severity for vulnerabilities found *outside* the build gate (already-deployed images, GitHub security alerts, newly-disclosed CVEs against pinned deps). Assessors (PCI 6.3.3, FedRAMP RA-5/SI-2) require defined and *met* timelines.
3. **No penetration testing.** Coverage is automated scanning plus internal adversarial review (the TFactory security audit, the CodeQL barrier work). There is no scheduled independent/external penetration test with a remediation record. PCI 11.3 and FedRAMP require at least annual; NYDFS 500.5 requires annual pen test + biannual vulnerability assessment.
4. **No vulnerability register / management process.** Findings live as transient scan output and ad-hoc issues; there is no single tracked register (finding -> severity -> owner -> due date -> status) that proves the loop closes within SLA.
5. **Known Trivy blind spot — bundled frontend deps.** Frontend assets bundled into the image (e.g. Monaco, served via CDN under CSP) do not reach a layer Trivy scans. A partial mitigation exists (`test_p0_supply_chain.py::test_frontend_lockfile_no_high_critical` scans the lockfile with `trivy fs`), but this is not applied uniformly (CFactory has no Trivy at all) and lockfile scanning misses vendored/bundled copies.
6. **No patch-cadence policy.** Renovate is configured everywhere but the merge/review cadence and the base-image digest-bump cadence are not policy-bound, so "current" is best-effort rather than an auditable target. Factory hub has no Renovate at all.

## Remediation plan (phased)

**Phase 1 — Close the CFactory gap (highest priority, gap #8).**
- Add the P0 Trivy image scan (reuse `tests/docker/test_p0_supply_chain.py` from a sibling repo) to CFactory `ci.yml`, gating fixable HIGH/CRITICAL.
- Add Syft dual-SBOM + cosign keyless signing to CFactory `release.yml`.
- Add a `.trivyignore` with the same audited-exceptions discipline.
- Add Renovate to the Factory hub repo.

**Phase 2 — Define and adopt remediation SLAs.**

| Severity | Source | Time-to-remediate (from confirmation) |
|---|---|---|
| Critical (CVSS 9.0–10.0) | scan / advisory / disclosure | 7 days (mitigate/patch or documented compensating control) |
| High (7.0–8.9) | scan / advisory | 30 days |
| Medium (4.0–6.9) | scan / advisory | 90 days |
| Low (< 4.0) | scan | next scheduled maintenance / 180 days |

- Build-gate stays fail-closed for fixable HIGH/CRITICAL (already met). SLAs above govern findings that bypass the gate (deployed images, unfixable-at-build, newly disclosed).
- Wire GitHub security alerts + Trivy output into the register in Phase 3; clock starts at confirmation, not disclosure.

**Phase 3 — Vulnerability register + tracking.**
- Stand up a single register (GitHub issues with a `vuln` label + due-date field, or the Fides evidence store) mapping finding -> severity -> owner -> SLA due date -> status -> evidence.
- Monthly review of open findings vs SLA; breaches escalate.

**Phase 4 — Penetration testing program.**
- Schedule annual external/independent penetration test (network + application, including the autonomous-agent attack surface: prompt injection, egress, untrusted-code Jobs).
- Add biannual internal vulnerability assessment (formalise the existing adversarial reviews into a repeatable, evidenced exercise).
- Track findings in the same register under the same SLAs; retain the report + remediation evidence.

**Phase 5 — Close the frontend blind spot + patch cadence.**
- Apply the frontend lockfile scan uniformly across all image-shipping repos; add SBOM-diff review to catch bundled/vendored copies Trivy's filesystem scan misses.
- Set a Renovate merge cadence (e.g. non-major auto-merge on green CI within 7 days; majors reviewed within 30) and a base-image digest-bump cadence, both documented and tracked.

## Acceptance criteria

- [ ] Every image-shipping repo (incl. CFactory) runs a fail-closed Trivy HIGH/CRITICAL image scan in CI.
- [ ] Every image-shipping repo (incl. CFactory) produces a dual-format SBOM and a cosign signature at release.
- [ ] Renovate is enabled on all six repos, including the Factory hub.
- [ ] Remediation SLAs by severity are documented, adopted, and demonstrably met (evidence of on-time closure).
- [ ] A vulnerability register exists and is reviewed monthly; no finding is past its SLA due date without a documented, approved exception.
- [ ] An annual independent penetration test is scheduled and completed, with a report and remediation evidence retained.
- [ ] The bundled-frontend-dependency blind spot is covered on every image-shipping repo (lockfile scan + SBOM review).
- [ ] `.trivyignore` allow-lists remain per-CVE with documented rationale; no blanket skips.

## Evidence artifacts

- CI logs: Trivy P0 scan results (`tests/docker/test_p0_supply_chain.py`) per repo, per release.
- `.github/workflows/codeql.yml` runs + CodeQL alert history (all five code repos); TFactory `.github/codeql/codeql-config.yml` custom pack.
- `release.yml` cosign signature + SBOM attestation logs; published SPDX + CycloneDX SBOMs per image (PFactory/AIFactory/TFactory, and CFactory after Phase 1).
- `renovate.json` per repo + merged Renovate PR history (patch cadence evidence).
- `.trivyignore` files (audited exception register) per repo.
- Base-image digest-bump commits and the CVE remediation history above (#971, #565, Chainguard digest bumps).
- Vulnerability register export (Phase 3) and penetration-test report + remediation records (Phase 4).
