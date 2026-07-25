# Governance and ISMS

- **Domain:** Governance & ISMS (Factory#311)
- **Parent epic:** Factory#310
- **Frameworks addressed:**
  - ISO/IEC 27001:2022 — Clauses 4-10 (context, leadership, planning, support, operation, performance evaluation, improvement) and Annex A control A.5 (organizational controls, incl. A.5.1 policies, A.5.2 roles/responsibilities, A.5.31 legal/regulatory, A.5.35 independent review)
  - SOC 2 — CC1 (control environment), CC2 (communication), CC3 (risk assessment), CC4 (monitoring), CC5 (control activities)
  - NYDFS 23 NYCRR 500 — 500.3 (cybersecurity policy), 500.4 (CISO / governance and board reporting)
  - SEC cyber rules — Reg S-K Item 106 (risk management, strategy, and governance disclosure)
  - FFIEC — management booklet (governance, board/management oversight, risk management program)

## Purpose

This document establishes the Information Security Management System (ISMS) for the
Factory fleet — the management framework that sits above the individual technical
control domains (Factory#312 onward). It defines the policy set, the risk-assessment
methodology and register, the Statement of Applicability (SoA), the security roles, and
the management-review and continuous-monitoring cadence.

The intent is an assessor-facing artifact: a single folder
(`Factory/docs/compliance/`) an assessor can open to find the policy set, risk register,
SoA, and roles, each traceable to a framework clause. It does not restate the technical
controls themselves — those live in their own domain documents — but it is the umbrella
that references them and holds the fleet accountable for maintaining them.

## Current state (grounded)

The fleet's engineering governance is mature; its *ISMS* documentation is essentially
greenfield. Concretely, as of 2026-07-24:

What exists (real files):

- **RFC process** — 20 accepted RFCs under `Factory/docs/rfc/0001-*.md` through
  `0019-*.md` govern architecture and change intent (task contracts, evidence gates,
  verification assurance levels, access/credential provisioning, CI-gated auto-merge).
  This is a genuine, followed decision-record process, but it is engineering-scoped, not
  an information-security policy set.
- **Threat models** — `Factory/docs/security/untrusted-content-threat-model.md` and
  `Factory/docs/security/sandbox-runtime-class.md` document specific threats
  (prompt-injection, untrusted-code isolation) with fail-closed design. These are strong
  but narrow; there is no fleet-wide risk assessment.
- **Vulnerability reporting** — `SECURITY.md` exists in `AIFactory/`, `PFactory/`, and
  `TFactory/` with private-advisory reporting, response-time targets, and scope. It is
  **missing** in `Factory/` (the hub) and `CFactory/`, and there is no single fleet-level
  policy.
- **Code ownership** — `CODEOWNERS` exists in `AIFactory/`, `PFactory/`, and `TFactory/`
  (all owned by `@dataseeek`). It is **missing** in `Factory/`, `CFactory/`, and
  `factory-gitops/`.
- **Compliance folder** — `Factory/docs/compliance/policies/` exists but is empty
  (this document is its first occupant).

What is missing (the ISMS itself):

- No information-security policy set (no InfoSec, Access Control, Acceptable Use, SDLC,
  Incident, Data, BC/DR, or Vendor policy).
- No risk assessment or risk register, and no documented risk methodology.
- No Statement of Applicability mapping ISO 27001:2022 Annex A (93 controls) to
  implemented / planned / not-applicable.
- No defined security roles: no named security owner / CISO, no control-owner assignments.
  `CODEOWNERS @dataseeek` implies ownership but is not a governance role definition.
- No management-review cadence and no continuous-monitoring plan; no evidence of periodic
  independent review (ISO A.5.35).
- **Branch protection is not enforced on `main`** for the audited repos: the GitHub
  branch-protection API returns `404 Branch not protected` and `rulesets` is empty for
  both `Factory` and `AIFactory`. This is primarily a change-management concern
  (Factory#317) but is noted here because it undercuts the enforceability of any SDLC
  policy this ISMS references.

Net: engineering is ahead of documentation. The controls an assessor rewards (tamper-
evident audit chain, cosign+SBOM, signed contracts, evidence gates, sandboxing) exist in
code but are not wrapped in a management system that assigns ownership, assesses risk, or
demonstrates oversight.

## Gaps

| # | Gap | Framework requirement not met |
|---|-----|-------------------------------|
| G1 | No information-security policy, approved and communicated | ISO 27001 A.5.1, Clause 5.2; SOC 2 CC5.3; NYDFS 500.3 |
| G2 | No defined security roles / CISO / control owners | ISO 27001 Clause 5.3, A.5.2; SOC 2 CC1.3; NYDFS 500.4; SEC Item 106(c) |
| G3 | No risk-assessment methodology or risk register | ISO 27001 Clause 6.1.2, 8.2; SOC 2 CC3.1-CC3.4; SEC Item 106(b); FFIEC mgmt |
| G4 | No Statement of Applicability | ISO 27001 Clause 6.1.3(d) — mandatory document |
| G5 | No management review / oversight cadence | ISO 27001 Clause 9.3; SOC 2 CC1.2, CC4.1; NYDFS 500.4(b) board reporting |
| G6 | No continuous-monitoring plan | ISO 27001 Clause 9.1; SOC 2 CC4.1-CC4.2; FFIEC |
| G7 | No independent review of information security | ISO 27001 A.5.35; SOC 2 CC4.1 |
| G8 | Missing SECURITY.md / CODEOWNERS in `Factory` and `CFactory` (governance coverage uneven) | ISO 27001 A.5.2; SOC 2 CC2.2 |
| G9 | No scope / SoA boundary statement (what is in the ISMS) | ISO 27001 Clause 4.3 |

## Remediation plan

Phased. Each item is tagged **[docs]** (authoring, this domain) or **[eng]**
(engineering change owned elsewhere but referenced here).

### Phase 1 — Establish the ISMS skeleton (this domain, docs)

1. **[docs] Author the core policy set** under `Factory/docs/compliance/policies/`.
   Each is a short, enforceable policy that references the technical domain doc for
   specifics. Files to create:
   - `information-security-policy.md` — top-level policy, scope, objectives, management
     commitment (ISO Clause 5.2 / A.5.1; NYDFS 500.3). Parent of all others.
   - `access-control-policy.md` — least privilege, MFA, access reviews, joiner/mover/leaver
     (references IAM domain Factory#312).
   - `acceptable-use-policy.md` — use of fleet systems, credentials, and AI agents.
   - `secure-sdlc-policy.md` — branch protection, code review via CODEOWNERS, signed
     commits, CI gates, evidence gates (references change-mgmt Factory#317, RFC-0001a/0009).
   - `incident-response-policy.md` — pointer to the IR runbook and SEC 4-business-day /
     NYDFS 72-hour notification timelines (references IR domain).
   - `data-management-policy.md` — classification, retention, PII/LLM-egress handling
     (references data-governance domain).
   - `business-continuity-dr-policy.md` — backup, RTO/RPO, tested restore (references
     BC/DR domain; note the epic flags no backups today).
   - `vendor-management-policy.md` — third-party/LLM-provider risk (Anthropic, OpenAI,
     GitHub, cloud), review before onboarding.
   This document defines the structure; the other Factory#310 domain docs supply each
   policy's control detail so policies stay thin and non-duplicative.

2. **[docs] Define roles** in `Factory/docs/compliance/roles.md`:
   - Security Owner / CISO (named individual) — accountable for the ISMS, reports to
     leadership quarterly (NYDFS 500.4).
   - Control owners — one named owner per Factory#310 domain (IAM, encryption, IR, etc.).
   - RACI for policy approval, risk acceptance, and exception handling.

3. **[docs] Risk register + methodology** in `Factory/docs/compliance/risk-register.md`
   (see methodology below). Seed it from the epic's eight top gaps as the initial entries.

4. **[docs] Statement of Applicability** in `Factory/docs/compliance/soa.md` covering all
   93 ISO 27001:2022 Annex A controls (see SoA approach below).

5. **[docs] Scope statement** (ISO Clause 4.3) at the top of the InfoSec policy: the ISMS
   covers the six fleet repos (Factory, PFactory, AIFactory, TFactory, CFactory,
   factory-gitops), their CI/CD, the k3d cluster, MinIO evidence store, and Postgres
   job-state store.

### Phase 2 — Close governance-coverage gaps (mixed)

6. **[docs+eng] Add `SECURITY.md` and `CODEOWNERS` to `Factory` and `CFactory`** so all
   repos have consistent reporting and ownership (G8).
7. **[docs] Management-review procedure** in `Factory/docs/compliance/management-review.md`:
   quarterly agenda (risk-register review, incident review, control-effectiveness, audit
   findings, policy exceptions), attendees, and record-keeping (ISO Clause 9.3).
8. **[docs] Continuous-monitoring plan** in `Factory/docs/compliance/continuous-monitoring.md`:
   which signals are watched (CI gate pass rate, Trivy/CodeQL findings, cosign/SBOM
   coverage, audit-chain daily-anchor verification, access reviews) and at what cadence.
   Wherever a signal is already emitted by the fleet, cite it rather than inventing a new
   one.

### Phase 3 — Operationalize (ongoing)

9. **[eng] Enforce branch protection / rulesets on `main`** across the fleet (owned by
   change-mgmt Factory#317; tracked here as a dependency for the SDLC policy to be real).
10. **[docs] First management review** held and minuted; risk register re-scored;
    SoA reviewed. Sets the recurring quarterly cadence.
11. **[docs] Schedule the annual independent review** (ISO A.5.35).

### Risk-register methodology

Living document, reviewed quarterly and on material change. Each risk row:

- **ID** — R-NNN.
- **Asset** — what is at risk (e.g. Postgres job-state, MinIO evidence store, shared
  `API_TOKEN`, LLM-provider data flow, per-task untrusted-code Jobs).
- **Threat / vulnerability** — the credible adverse event.
- **Likelihood** — 1 (rare) to 5 (almost certain).
- **Impact** — 1 (negligible) to 5 (severe).
- **Inherent risk** — likelihood x impact (1-25); band Low 1-6 / Medium 8-12 / High 15-25.
- **Existing controls** — cite the real control (e.g. cosign signing, evidence gates,
  bwrap sandbox) or "none".
- **Treatment** — mitigate / accept / transfer / avoid, with owner and target date.
- **Residual risk** — re-scored after treatment.
- **Risk owner** — named.

Seed entries map directly to the epic's top gaps (no backups/DR, shared wildcard token,
no at-rest encryption, no Job NetworkPolicy, MFA not enforced, no compliance artifacts,
PII to LLM by default, uneven supply-chain coverage). Risk acceptance above the Medium
band requires Security Owner sign-off recorded in the register.

### Statement of Applicability approach

`soa.md` enumerates all **93 ISO/IEC 27001:2022 Annex A controls** across the four themes
(A.5 Organizational 37, A.6 People 8, A.7 Physical 14, A.8 Technological 34). Each row:

- Control ID and title.
- **Status** — Implemented / Planned / Not Applicable.
- **Justification** — for Implemented, cite the evidence (real file, RFC, or CI job);
  for Planned, cite the Factory#310 child issue and target phase; for N-A, state why
  (e.g. A.7 physical-media controls are largely N-A for a cloud-only fleet — justified,
  not silently dropped).
- **Owner** — the control owner from `roles.md`.

The SoA is the join table between this ISMS and the technical domain docs: it is how an
assessor confirms every Annex A control is consciously addressed.

## Acceptance criteria

An assessor can open `Factory/docs/compliance/` and find a complete, coherent ISMS:

- [ ] Information-security policy exists, is dated, states scope (ISO 4.3), and names the
      approving authority.
- [ ] The full policy set exists under `policies/`: InfoSec, Access Control, Acceptable
      Use, SDLC, Incident, Data, BC/DR, Vendor.
- [ ] `roles.md` names a Security Owner / CISO and a control owner per Factory#310 domain,
      with a RACI.
- [ ] `risk-register.md` exists, follows the documented methodology, and is seeded with at
      least the epic's eight top-gap risks, each scored and assigned an owner.
- [ ] `soa.md` covers all 93 Annex A controls with status + justification + owner; no
      control is blank.
- [ ] `management-review.md` defines a quarterly cadence and record-keeping; at least the
      first review is minuted.
- [ ] `continuous-monitoring.md` lists monitored signals and cadence, citing existing
      fleet telemetry where it exists.
- [ ] Every policy references its technical domain doc (no orphaned or duplicated control
      detail).
- [ ] `SECURITY.md` and `CODEOWNERS` present in all six fleet repos.

## Evidence artifacts

Collect and store the following to prove this control to an auditor (store alongside the
docs and in the MinIO evidence bucket where automated):

- The approved, version-controlled policy set (git history shows approval date and
  approver; PR reviews serve as the approval record).
- `risk-register.md` with revision history showing periodic re-scoring.
- `soa.md` with revision history.
- Minutes of each quarterly management review (`management-review/YYYY-QN.md`),
  including risk decisions and exceptions granted.
- Continuous-monitoring output samples: CI gate reports, Trivy/CodeQL scan results,
  cosign/SBOM coverage, and the audit-chain daily-anchor verification logs (already
  produced by the fleet).
- Access-review records (produced by the IAM domain) referenced by the review minutes.
- The independent-review report (ISO A.5.35), once performed.
- `roles.md` plus the `CODEOWNERS` files as evidence of assigned responsibility.
- Git log / PR history as tamper-evident proof of when each artifact was created and
  changed.
