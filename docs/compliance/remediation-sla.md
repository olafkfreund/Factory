# Vulnerability Remediation SLA

- **Domain:** Vulnerability & patch management (Factory#317)
- **Companion to:** [policies/vuln-patch-management.md](policies/vuln-patch-management.md) — that document assesses the fleet's scanning posture and gaps; this document is the adopted, assessor-facing time-to-fix standard it calls for (its Phase 2). Read that first for scanner coverage and CVE history.
- **Frameworks addressed:** ISO 27001 A.8.8 (management of technical vulnerabilities), SOC 2 CC7.1 (vulnerability detection and remediation), PCI DSS 6.3.1/6.3.3 (rank and patch within defined timeframes), FedRAMP / NIST 800-53 RA-5 (scan and remediate) & SI-2 (flaw remediation).

## Purpose

State how fast the Factory fleet must remediate a confirmed vulnerability, by severity and by where it was found, and how time-limited exceptions are governed. The Trivy build gate already fails CI closed on fixable HIGH/CRITICAL image findings; this standard governs everything the build gate does not stop — deployed images, unfixable-at-build findings, GitHub security alerts, and newly-disclosed CVEs against pinned dependencies — so an assessor can trace defined and met timelines (PCI 6.3.3, RA-5/SI-2).

## Severity assignment

Severity is the CVSS v3.1 base score from the authoritative advisory (NVD / GHSA), taken from the scanner that surfaced the finding:

- **Trivy** reports vendor/NVD severity per CVE on image and dependency findings.
- **CodeQL** reports rule severity (error / warning) and security-severity per alert.
- **Renovate** and GitHub Dependabot alerts carry the GHSA severity.

Where exposure materially changes real risk (internet-reachable versus cluster-internal, reachable code path versus dormant transitive dependency), the security owner may adjust severity one band and must record the justification in the register entry. The unadjusted scanner severity is retained alongside it.

## Remediation clocks

Clock starts at **confirmation** (triaged as a real, applicable finding), not at disclosure. For a newly-disclosed CVE with no fix yet available, the clock starts when a fixed version is published; until then a compensating control or documented risk acceptance is required within the triage window.

| Severity (CVSS v3.1) | Build-blocking (fixable, at CI) | Deployed image / running fleet | Newly-disclosed CVE (triage -> remediate) |
|---|---|---|---|
| Critical (9.0-10.0) | Fail-closed: cannot merge or release | 7 days | Triage 48h; remediate 7 days from fix availability, or apply a compensating control within 48h |
| High (7.0-8.9) | Fail-closed: cannot merge or release | 30 days | Triage 5 days; remediate 30 days from fix availability |
| Medium (4.0-6.9) | Not gated (advisory) | 90 days | Triage 10 days; remediate 90 days |
| Low (0.1-3.9) | Not gated (advisory) | 180 days / next scheduled maintenance | Triage 30 days; remediate 180 days |

Notes:

- **Build-blocking** is the existing P0 gate: `tests/docker/test_p0_supply_chain.py::test_trivy_no_high_critical` runs `trivy --severity HIGH,CRITICAL --ignore-unfixed` and asserts zero. Fixable HIGH/CRITICAL never reaches a branch, so its effective SLA is zero. This gate is live in PFactory, AIFactory, and TFactory; CFactory does not yet run it (CFactory#191, in flight).
- **Deployed image / running fleet** covers findings against images already in the cluster — a CVE disclosed after the image was built and signed. These do not fail a build (nothing is building) and are the primary reason a time-to-fix clock is needed.
- **Unfixable-at-build** findings (`--ignore-unfixed` excludes them from the gate) are not silently dropped: they become a register entry with an exception (below) and are re-evaluated on every scan, so they remediate automatically the moment an upstream fix lands.

## Exception governance

Two mechanisms suppress a finding from the fail-closed gate. Both are exceptions and both are governed identically: no exception exists without an owner, an expiry, and a written justification, and each is a tracked entry in the [vulnerability register](vulnerability-register.md).

### `.trivyignore` (per-CVE allow-list)

- One CVE per line, each with a rationale comment stating why it is not applicable or is accepted, per the discipline already enforced (see any repo's `.trivyignore`; the fleet currently carries exactly one entry, `CVE-2024-23342`, python-ecdsa Minerva, not-applicable because JWT is HS256/HMAC and the EC signing path is never invoked).
- **Never blanket-skip.** No wildcard, no severity-wide, no unexplained ID.
- Each entry names an **owner** (the control owner per [roles.md](roles.md)) and an **expiry** (re-review date, at most 90 days out). At expiry the entry is re-justified or removed. When an upstream fix or dependency migration lands, the line is deleted, not left to rot.

### `--ignore-unfixed` (no upstream fix available)

- Applied fleet-wide at the build gate so that a HIGH/CRITICAL with no released fix cannot block every merge indefinitely.
- Every finding it suppresses is recorded in the register with severity, the affected component, and the deployed-image clock from the table above. Because the scan re-runs unfiltered against the register, the finding closes automatically once a fix is published.
- This flag governs *timing of the gate*, not acceptance of risk: an unfixable Critical still carries a 7-day deployed-fleet clock to mitigate or apply a compensating control.

### Approval and review

- Critical and High exceptions require sign-off from the security control owner; Medium and Low may be self-approved by the repo owner and are reviewed in the monthly register review.
- No finding sits past its SLA due date without a recorded, approved exception. A lapsed exception (past expiry, no renewal) is an SLA breach and escalates.

## Breach handling

An open finding reaching its SLA due date without closure or a valid exception is an SLA breach. Breaches are raised at the monthly register review and, for Critical/High, escalated to the security owner immediately. Repeated breaches against the same component are a signal to replace or vendor-fork the dependency rather than re-accept the risk each cycle.

## Framework mapping

| Requirement | This standard satisfies it by |
|---|---|
| ISO 27001 A.8.8 | Defined timelines to evaluate and address technical vulnerabilities by severity, with governed exceptions. |
| SOC 2 CC7.1 | Detection (scanners) tied to remediation within committed, evidenced timeframes. |
| PCI DSS 6.3.1 / 6.3.3 | Severity ranking (CVSS bands) and patch-within-timeframe (Critical/High tracked; all applicable others within the deployed-fleet clocks). |
| NIST 800-53 RA-5 | Scan cadence (CodeQL weekly + per-PR, Trivy per build/release) plus remediation timelines and exception tracking. |
| NIST 800-53 SI-2 | Flaw remediation with time-bound closure and re-evaluation of unfixed flaws each scan. |

## Evidence artifacts

- The SLA table above (this document), adopted per [roles.md](roles.md).
- Trivy P0 CI logs showing the fail-closed gate (`tests/docker/test_p0_supply_chain.py`), per repo, per release.
- `.trivyignore` files with per-CVE rationale, owner, and expiry — the audited exception set.
- Register entries (see [vulnerability-register.md](vulnerability-register.md)) showing confirmed date, SLA due date, closure date, and closure evidence — the proof timelines were met.
- Monthly register-review notes recording any breach and its escalation.
