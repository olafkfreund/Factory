# Vulnerability and Patch Management

- **Domain:** Vulnerability & patch management (Factory#317)
- **Frameworks addressed:** ISO 27001 A.8.8 (management of technical vulnerabilities), SOC 2 CC7.1 (vulnerability detection), PCI DSS 6.3 (identify/rank/patch vulnerabilities) & 11.3 (penetration testing), NYDFS 23 NYCRR 500.5 (penetration testing + vulnerability assessments), FedRAMP / NIST 800-53 RA-5 (vulnerability scanning) & SI-2 (flaw remediation).

## Purpose

Define how the Factory fleet finds, ranks, remediates, and evidences software vulnerabilities across source code, dependencies, and container images — with defined time-to-fix targets and independent testing. This policy governs the six repositories that make up the fleet: the `Factory` spec/contract hub and the five service repos (`PFactory`, `AIFactory`, `TFactory`, `CFactory`, `factory-gitops`).

## Current state (grounded)

The engineering posture is strong on automated scanning and supply-chain provenance, but coverage is uneven and there is no documented remediation SLA or penetration-testing program. The controls below are all live in CI today.

### Per-repo scanner coverage

| Repo | CodeQL (SAST) | Trivy (image/dep CVE) | Dependency updates | Cosign + SBOM | Notes |
|---|---|---|---|---|---|
| Factory (hub) | Yes | No | No | No | Spec/contract + docs; ships no container image, so no Trivy/SBOM by design. Its only Dockerfile is the `templates/cloud-deploy/` scaffolding template, which is deliberately unpinned because it is copied into generated projects, not built here. |
| PFactory | Yes | Yes | Dependabot: security alerts + docker (daily) | Yes | Full stack. |
| AIFactory | Yes (security-and-quality pack) | Yes | Dependabot: security alerts + docker (daily) | Yes (3 image variants) | Reference implementation. |
| TFactory | Yes (custom barrier query pack + `actions`) | Yes | Dependabot: security alerts + docker (daily) | Yes | Strongest SAST config; also scans the system-under-test with Trivy during verification (`apps/backend/agents/dependency_review.py`). |
| CFactory | Yes | **No** | Dependabot: security alerts + docker (weekly) | **No** | Cockpit UI. Missing image CVE scanning, SBOM, and image signing — the epic #310 gap #8. |
| factory-gitops | No | No | **None** | No | Manifests only. Its `renovate.json` regex custom manager has matched nothing since TFactory#791 moved the agent-CLI pins into the service repos' Dockerfiles; those are covered by the hub's `cli-freshness.yml` instead — see gap #7. |

Sources: `.github/workflows/codeql.yml` (all five code repos; weekly Monday cron + per-PR); `.github/workflows/ci.yml` and `release.yml` in PFactory/AIFactory/TFactory (`aquasecurity/setup-trivy`, `anchore/sbom-action`, `sigstore/cosign-installer`); `.github/dependabot.yml` in PFactory/AIFactory/TFactory/CFactory.

**Correction (2026-07-30, Factory#436).** Earlier revisions of this table credited "Renovate x5" as a live control. That was wrong, and wrong in the direction that flatters the posture: a `renovate.json` existed in five repos and Renovate had never run in any of them. The Renovate GitHub App is not installed on this account, so there were zero Renovate PRs fleet-wide and no Dependency Dashboard issue had ever been opened despite `:dependencyDashboard` being configured in four of the five. Committed configuration was being read as operating control. The fleet has standardised on Dependabot for base images (Factory#436), which is verifiable: it has an observable PR history in these repos, and it triggers the workflow runs that gate a base-image bump. `renovate.json` has been deleted from the four service repos so that no config claims coverage it does not deliver.

### How the scanners gate

- **Trivy** runs as a P0 supply-chain test (`tests/docker/test_p0_supply_chain.py::test_trivy_no_high_critical`) that fails CI on any **fixable HIGH/CRITICAL** finding (`--severity HIGH,CRITICAL --ignore-unfixed`, asserted zero). Exceptions are an audited allow-list: every repo's `.trivyignore` carries exactly one entry — `CVE-2024-23342` (python-ecdsa Minerva) — with a documented not-applicable rationale (JWT is HS256/HMAC, EC signing path never invoked). Base images are Chainguard, digest-pinned, with `apk upgrade` clearing fixable HIGH/CRITICAL between digest bumps (`AIFactory/Dockerfile`).
- **CodeQL** analyses `python` and `javascript-typescript` on every PR and weekly. TFactory replaces GitHub default setup with a custom barrier-aware path-injection query pack (`.github/codeql/codeql-config.yml`) so verified-safe code clears, and additionally analyses the `actions` language.
- **SBOM + signing** (PFactory/AIFactory/TFactory release): Syft emits dual SPDX + CycloneDX; cosign keyless (Sigstore + GitHub OIDC) signs each image and attests both SBOM formats.

### CVE remediation history (evidence of a working loop)

- Base-image CVE bump: Chainguard Python digest `d45c16a1` -> `369768c6` to clear a Trivy P0 (2026-06-24).
- Copilot-cache CVE: Trivy HIGHs from a bundled `@github/copilot` / foundry-local-sdk subtree were removed at the source (#971, closed); copilot is never run at build time.
- CodeQL path-injection hardening: custom barrier pack drove remediation across 19 files (#565).

## Gaps

1. **Uneven supply-chain coverage — CFactory.** CFactory has CodeQL and Dependabot base-image updates but no Trivy image scan, no SBOM, and no cosign signing. Its container image ships to the cluster unscanned and unsigned, which makes a current base image the only supply-chain control it actually has. (Epic #310 gap #8.)
2. **No documented remediation SLA.** Trivy gates fixable HIGH/CRITICAL at build, but there is no written, tracked time-to-fix per severity for vulnerabilities found *outside* the build gate (already-deployed images, GitHub security alerts, newly-disclosed CVEs against pinned deps). Assessors (PCI 6.3.3, FedRAMP RA-5/SI-2) require defined and *met* timelines.
3. **No penetration testing.** Coverage is automated scanning plus internal adversarial review (the TFactory security audit, the CodeQL barrier work). There is no scheduled independent/external penetration test with a remediation record. PCI 11.3 and FedRAMP require at least annual; NYDFS 500.5 requires annual pen test + biannual vulnerability assessment.
4. **No vulnerability register / management process.** Findings live as transient scan output and ad-hoc issues; there is no single tracked register (finding -> severity -> owner -> due date -> status) that proves the loop closes within SLA.
5. **Known Trivy blind spot — bundled frontend deps.** Frontend assets bundled into the image (e.g. Monaco, served via CDN under CSP) do not reach a layer Trivy scans. A partial mitigation exists (`test_p0_supply_chain.py::test_frontend_lockfile_no_high_critical` scans the lockfile with `trivy fs`), but this is not applied uniformly (CFactory has no Trivy at all) and lockfile scanning misses vendored/bundled copies.
6. **No patch-cadence policy.** Base-image updates now open as PRs, but the merge/review cadence is not policy-bound, so "current" is best-effort rather than an auditable target. Until 2026-07-30 this gap was worse than recorded: nothing opened those PRs at all, and every base-image digest bump in fleet history — including the Chainguard Python moves for CVE-2026-45447 — was done by hand.

7. **Agent-CLI pins are covered by a workflow, not by a bot.** ~~factory-gitops dependency updates are unmanaged.~~ Closed 2026-08-07 (Factory#459). The pins (`@anthropic-ai/claude-code`, `@openai/codex`, `@google/gemini-cli`) moved out of `factory-gitops apps/*/manifests/manifests.yaml` into each service repo's `Dockerfile` when TFactory#791 baked the CLIs into the runtime images, so that repo's `renovate.json` regex custom manager has matched nothing since — it reports success having found no dependencies, which is why "unmanaged" went unnoticed. No bot covers them: the Renovate App is not installed (zero Renovate PRs on this account, ever) and Dependabot cannot see an `npm install -g @scope/pkg@version` argument in a RUN layer, consistent with the parser limitation verified in gap #8. Measured 2026-08-07: Dependabot bumped `FROM node:24-bookworm-slim` and `FROM chainguard/python@sha256:...` in those same Dockerfiles within the preceding week while never once raising a PR for the three CLIs pinned twenty lines below. Coverage is now two halves of `.github/workflows/cli-freshness.yml`: the `freshness` job alerts when a newer release has sat unadopted past a 30-day window (#556), and the `propose` job opens or refreshes one bump PR per service repo each week (#459). Neither merges: the bumped CLI is baked into the image that executes untrusted repository content, and what makes proposing it automatically defensible is that each service repo's `image-build.yml` compiles `target: runtime` on the PR while the bake step runs `claude --version` inside that build. Installing the Renovate App would still be the fuller fix and remains open on Factory#459; if it ever is installed, delete the `propose` job rather than let two bots rewrite the same line.

8. **Dependabot does not read `COPY --from=<image>`.** Verified 2026-07-30 with `dependabot-cli` v1.91.0: its Dockerfile parser only extracts `FROM`. The `COPY --from=ghcr.io/olafkfreund/tfactory-runner-nix:latest@sha256:...` pins in `AIFactory/Dockerfile` are therefore not covered by any bot. Risk is low because that registry is ours, so upstream garbage collection is not a threat, but the pins are hand-managed rather than tracked.

## Remediation plan (phased)

**Phase 1 — Close the CFactory gap (highest priority, gap #8).**
- Add the P0 Trivy image scan (reuse `tests/docker/test_p0_supply_chain.py` from a sibling repo) to CFactory `ci.yml`, gating fixable HIGH/CRITICAL.
- Add Syft dual-SBOM + cosign keyless signing to CFactory `release.yml`.
- Add a `.trivyignore` with the same audited-exceptions discipline.
- ~~Decide whether the `factory-gitops` agent-CLI pins warrant installing the Renovate App, or whether the `cli-canary` should assert freshness itself (gap #7).~~ Done: both halves are `cli-freshness.yml`. Installing the Renovate App is still open on Factory#459 and needs account-level authorisation.

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
- Set a dependency-PR merge cadence (e.g. non-major auto-merge on green CI within 7 days; majors reviewed within 30) and a base-image digest-bump cadence, both documented and tracked.
- Add a staleness assertion so an *absent* bot is a failure rather than silence. The nine-week outage window behind AIFactory#1091 was invisible precisely because "no PRs" and "nothing to update" look identical from the outside. A check that fails when a pinned digest no longer matches its tag would have caught it on day one.

## Acceptance criteria

- [ ] Every image-shipping repo (incl. CFactory) runs a fail-closed Trivy HIGH/CRITICAL image scan in CI.
- [ ] Every image-shipping repo (incl. CFactory) produces a dual-format SBOM and a cosign signature at release.
- [ ] Every repo that builds a container image has a dependency bot that demonstrably runs, evidenced by its PR history rather than by the presence of a config file.
- [x] The agent-CLI pins are tracked by something, and something proposes the bump (gap #7): `cli-freshness.yml` alerts on staleness and opens a weekly bump PR per service repo. Evidenced by PR history, not by config: AIFactory#1198, PFactory#483, TFactory#978 (2026-08-07).
- [ ] Remediation SLAs by severity are documented, adopted, and demonstrably met (evidence of on-time closure).
- [ ] A vulnerability register exists and is reviewed monthly; no finding is past its SLA due date without a documented, approved exception.
- [ ] An annual independent penetration test is scheduled and completed, with a report and remediation evidence retained.
- [ ] The bundled-frontend-dependency blind spot is covered on every image-shipping repo (lockfile scan + SBOM review).
- [ ] `.trivyignore` allow-lists remain per-CVE with documented rationale; no blanket skips.

## Evidence artifacts

- CI logs: Trivy P0 scan results (`tests/docker/test_p0_supply_chain.py`) per repo, per release.
- `.github/workflows/codeql.yml` runs + CodeQL alert history (all five code repos); TFactory `.github/codeql/codeql-config.yml` custom pack.
- `release.yml` cosign signature + SBOM attestation logs; published SPDX + CycloneDX SBOMs per image (PFactory/AIFactory/TFactory, and CFactory after Phase 1).
- `.github/dependabot.yml` per repo **plus** the merged dependency-PR history for that repo. The config alone is not evidence: Factory#436 is the case study in a well-formed config that produced nothing for nine weeks. Evidence is bot activity.
- `.trivyignore` files (audited exception register) per repo.
- Base-image digest-bump commits and the CVE remediation history above (#971, #565, Chainguard digest bumps).
- Vulnerability register export (Phase 3) and penetration-test report + remediation records (Phase 4).
