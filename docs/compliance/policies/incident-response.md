# Incident Response and Breach Notification

- **Domain:** Incident response & breach notification (Factory#319)
- **Frameworks addressed:** ISO/IEC 27001 A.5.24-A.5.28, SOC 2 CC7.3-CC7.5, PCI DSS 12.10, NYDFS 23 NYCRR 500.17 (72-hour notification), SEC Regulation S-K Item 1.05 (4-business-day material-incident disclosure), FFIEC (incident response guidance), FedRAMP IR family (NIST SP 800-53 IR-1 through IR-8)
- **Parent epic:** Factory#310 (fleet compliance program)
- **Status:** Draft policy + operational runbook. Alerting/paging and tabletop exercises are open remediation items (see Gaps).
- **Owner:** Security lead / on-call rotation (see Roles)
- **Review cadence:** At least annually and after every Sev-1/Sev-2 incident.

## Purpose

This document defines how the Factory fleet detects, triages, contains, eradicates, recovers
from, and reports security and availability incidents, and it fixes the regulatory
notification clocks that start when an incident is confirmed. It exists to satisfy the
control requirement for a documented, tested incident-response capability (ISO A.5.24-A.5.28,
SOC 2 CC7.3-CC7.5, PCI 12.10, FedRAMP IR-1/IR-4/IR-6) and to make the breach-notification
timelines (SEC 4 business days, NYDFS 72 hours, GDPR 72 hours) actionable rather than
aspirational.

Scope covers the five fleet repositories and their deployed services -- Factory (spec/contract
hub), PFactory (planning), AIFactory (build), TFactory (verification), CFactory (cockpit) --
plus the shared cluster and GitOps configuration in factory-gitops. It covers both security
incidents (compromise, data exposure, credential leak, malicious use of the autonomous agents)
and availability incidents (outage, data loss, corruption of durable job state or evidence).

## Current state (grounded)

What exists today:

- **Coordinated vulnerability disclosure.** `PFactory/SECURITY.md`, `AIFactory/SECURITY.md`,
  and `TFactory/SECURITY.md` each define a private reporting channel (GitHub Security
  Advisory) with response SLAs: acknowledgement within 3 business days, triage and severity
  within 7 business days, fix depending on severity, disclosure coordinated with the reporter.
  These are inbound-report SLAs for externally discovered vulnerabilities -- they are not an
  internal incident runbook and they carry no regulatory notification clock.
- **Heuristic anomaly detection (detective control, UI-surfacing only).**
  `CFactory/apps/backend/cfactory/copilot/anomalies.py` flags failures / gate rejections,
  test-to-code handback loops, and stuck/stale stages over the WorkItem store, surfaced in the
  CFactory cockpit copilot panel (`CFactory/apps/frontend-web/src/CopilotPanel.tsx`). It is a
  pipeline-health heuristic, not a security detector: no auth-failure, exfiltration, or
  intrusion signals, and cost-spike detection is explicitly deferred (CFactory #14).
- **Tamper-evident audit trail for forensics.**
  `PFactory/apps/web-server/server/services/audit_chain.py` maintains a per-row SHA-256 hash
  chain over the audit log (genesis-anchored, unit-separator canonical encoding), and
  `PFactory/apps/web-server/server/audit/__main__.py` provides an air-gapped external verifier
  (`python -m server.audit verify-chain <export.ndjson>`) that re-computes the chain on a clean
  machine to prove the log has not been inserted into, deleted from, or mutated. This is the
  authoritative evidence source for incident timelines and post-incident review. (Note: the
  chain protects against a DB-write attacker who cannot recompute forward; a signed external
  daily anchor is the documented follow-up for the recompute-from-scratch threat.)
- **Observability substrate.** `factory-gitops/apps/observe/` deploys OpenObserve (log/metrics
  aggregation) with `factory-gitops/apps/observe-auth/` fronting authentication. Dashboards and
  log search exist.

What is missing (the substance of this domain):

- **No incident-response runbook.** No documented severity classification, roles, escalation
  path, containment/eradication/recovery procedure, or communications plan for an internal
  incident. Factory#310 grounded posture item 6 records this gap directly. The
  `skills/operations/incident-management.md` files in PFactory and TFactory are generic Claude
  assistant skills, not a fleet runbook.
- **No breach-notification procedure.** No mapping of an incident to the SEC, NYDFS, GDPR, or
  card-brand notification clocks; no named decision-maker for the materiality determination.
- **No alerting or paging.** No Alertmanager, PagerDuty, Opsgenie, or Slack wiring. Anomalies
  surface passively in a UI panel; nothing pages a human. An incident detected at 3am is not
  detected until someone looks at the cockpit.
- **No security detection** beyond the pipeline heuristic (no auth-failure/exfil/intrusion
  signals).
- **No tabletop exercise** and no post-incident review template.

This runbook closes the documentation gaps below; alerting and tabletop execution are tracked
as remediation.

## Incident response runbook

### Severity classification

Assign severity at triage from the higher of impact or regulatory exposure. Severity drives the
response clock and the notification decision.

| Severity | Definition | Examples | Response start |
|---|---|---|---|
| Sev-1 (Critical) | Confirmed compromise, data breach, or fleet-wide outage; any incident with a plausible regulatory-notification trigger. | Credential/token leak with confirmed use; unauthorized access to Postgres job-state or MinIO evidence; malicious code shipped by the agents to a customer; loss of the audit chain. | Immediate, 24/7 |
| Sev-2 (High) | Serious security or availability degradation, single-service outage, or suspected (unconfirmed) breach. | Suspected credential leak pending confirmation; single sibling service down; NetworkPolicy-less Job observed making unexpected egress; sandbox escape attempt. | Within 1 hour |
| Sev-3 (Medium) | Contained security weakness actively exploited at low impact, or degraded non-critical function. | Auth-failure spike from one source; anomaly detector flags a repeated handback loop with a security signature; non-prod exposure. | Same business day |
| Sev-4 (Low) | Minor issue, no data or availability impact; most inbound `SECURITY.md` vulnerability reports enter here. | Vulnerability report of a non-exploited weakness; hardening finding. | Per `SECURITY.md` SLA (3-day ack / 7-day triage) |

Any incident that could be a "personal data breach" (GDPR), a "cybersecurity event" affecting
nonpublic information (NYDFS), or "material" to a reasonable investor (SEC) is Sev-1 or Sev-2
regardless of technical blast radius, because the notification clock, not the outage, is the
driver.

### Roles

| Role | Responsibility |
|---|---|
| Incident Commander (IC) | Owns the incident end to end; declares severity; runs the response; the single decision-maker. Default: security lead / on-call. |
| Technical lead(s) | Per-repo owner(s) executing containment/eradication/recovery on the affected service. |
| Comms / notification owner | Drafts and sends internal and external/regulatory notifications; tracks the notification clocks. May be the IC for a small team. |
| Materiality decision-maker | For SEC-reportable events, the accountable officer who determines materiality (not an engineering decision). Named in the org's disclosure controls; engaged by the IC at declaration. |
| Scribe | Maintains the incident timeline (or confirms the tamper-evident audit chain covers it). |

For the current team size one person may hold several roles; the IC role must always be a
single named human.

### 1. Detection and reporting

Sources: the CFactory anomaly panel (pipeline health), OpenObserve logs/metrics, inbound
`SECURITY.md` advisories, cloud/provider alerts, and human report. Any team member who suspects
an incident raises it immediately to the on-call/IC -- no filtering. Until paging is wired (see
Gaps), on-call actively checks the cockpit and OpenObserve at the start of each working session;
this manual polling is a known interim control, not the target state.

### 2. Triage

The IC confirms whether this is a real incident, assigns severity, and opens an incident record
(GitHub private advisory or tracking issue). Capture: what is affected, first-observed time,
detection source, and an initial data-exposure hypothesis. Start the clock: record the
timestamp the incident is *confirmed* -- this is t0 for every notification deadline below.

### 3. Containment

Stop the bleeding without destroying evidence. Typical actions: rotate/revoke the affected
credential via the rotation broker (Factory #292); scale down or cordon the affected
service/Job; revoke the shared wildcard `API_TOKEN` scope if a sibling is implicated (note this
is fleet-wide -- a known blast-radius weakness, Factory#310 item 2); apply an emergency
NetworkPolicy to a suspect Job; disable the `DISABLE_AUTH` / CFactory OPEN-mode paths if
relevant. Snapshot volumes before mutating them. Do not power-cycle in a way that loses forensic
state.

### 4. Eradication

Remove the root cause: revoke leaked keys everywhere, patch the exploited vulnerability, remove
malicious artifacts, invalidate compromised sessions/tokens, and confirm no persistence remains.
Verify against the tamper-evident audit chain that the attacker did not alter historical records
(`verify-chain` on an air-gapped export).

### 5. Recovery

Restore service from a known-good state, monitor closely for recurrence, and re-enable normal
operations only after the IC confirms eradication. Where durable state was affected, restore
follows the business-continuity/DR procedure (Factory#310 domain 11 -- note DR/backups are an
open fleet gap, which constrains recovery today and must be stated honestly in the incident
record).

### 6. Post-incident review

Within 5 business days of resolution, hold a blameless review. Produce: confirmed timeline
(sourced from the audit chain export), root cause, what detection/response worked and what did
not, whether notification obligations were met and on time, and dated remediation actions with
owners. File remediation as tracked issues under Factory#310. Feed lessons back into this
runbook and into detection rules.

### Forensics reference

The tamper-evident audit hash chain (`PFactory/apps/web-server/server/services/audit_chain.py`)
plus its air-gapped external verifier (`python -m server.audit verify-chain`) are the
authoritative, court-defensible timeline for any investigation. Export the NDJSON audit log,
verify the chain on a clean machine, and attach the verification result to the incident record.
This satisfies the evidence-integrity expectations of ISO A.5.28 (collection of evidence) and
FedRAMP IR-4.

## Breach notification matrix

Clocks start at t0 (incident *confirmed* at triage), except SEC which starts at the materiality
determination. When multiple regimes apply, the shortest clock governs.

| Regime | Trigger | Deadline (from) | Notify who | How |
|---|---|---|---|---|
| SEC Reg S-K Item 1.05 (8-K) | Cybersecurity incident determined **material** | **4 business days** from the materiality determination (make that determination without unreasonable delay after discovery) | SEC (Form 8-K, Item 1.05) | Public 8-K filing; materiality owner decides, comms owner files. Applies only if the entity is a public filer. |
| NYDFS 23 NYCRR 500.17(a) | Cybersecurity event that (i) requires notice to another government/self-regulatory body, or (ii) has a reasonable likelihood of materially harming normal operations | **72 hours** from determination that the event occurred | NY Department of Financial Services | NYDFS online cybersecurity portal. Applies only if the entity or its customers are NYDFS-covered financial firms (conditional scope). |
| GDPR Art. 33 | Personal-data breach with risk to individuals' rights and freedoms | **72 hours** from becoming aware | Lead supervisory authority (DPA) | DPA breach-notification form. Art. 34: also notify affected individuals "without undue delay" if high risk. Applies if EU/UK personal data is processed. |
| PCI DSS 12.10 / card brands | Suspected/confirmed compromise of cardholder data | **Immediately** (per card-brand rules; hours, not days) | Acquiring bank + card brands (Visa/Mastercard/etc.), forensic (PFI) engagement | Card-brand-specific process. **Out of scope unless a payment flow is introduced** (Factory#310 scopes PCI out today). Listed for completeness. |
| US state breach laws | Breach of residents' personal information | Varies by state ("without unreasonable delay"; some fixed caps) | State AG and/or affected residents | Per applicable state statute. Engage counsel. |
| Customer contractual | Per DPA / MSA notification clauses | Per contract (often 24-72h) | Affected customers | Contact per contract; comms owner tracks. |

Notification decision procedure: at triage and again at each material development, the IC and
materiality decision-maker jointly assess each row above. Record the assessment and the
decision (notify / not-notify + rationale) in the incident log even when the decision is
not-notify -- the documented determination is itself the audit evidence. Engage legal counsel
before any external regulatory notification. Never let engineering uncertainty about scope stall
the clock: if a regime plausibly applies, treat it as applicable until counsel says otherwise.

## Gaps

1. **No alerting/paging (highest priority).** Detection is passive UI + manual log review;
   nothing pages a human out-of-hours. Anomaly detector is pipeline-health only, not security
   (no auth-failure/exfil/intrusion signals); cost-spike deferred (CFactory #14).
2. **No security detection layer.** OpenObserve aggregates logs but has no alerting rules for
   auth failures, anomalous egress from untrusted Jobs, or credential misuse.
3. **Runbook untested.** This runbook has never been exercised; no tabletop, no post-incident
   review has run against it.
4. **Notification readiness unproven.** Materiality decision-maker and DPA/regulator contacts
   are not yet enumerated per-entity; the clocks are documented but the human chain is not
   rehearsed.
5. **Recovery is constrained by the open DR gap** (Factory#310 item 1 / domain 11): no
   tested backups for Postgres job-state or MinIO evidence, so step 5 recovery from data loss
   cannot currently be guaranteed.
6. **Blast-radius weakness** during containment: the shared wildcard `API_TOKEN` means
   revoking one sibling's access affects the fleet (Factory#310 item 2).

## Remediation plan

Phase 1 -- Make an incident visible (wire alerting):
- Add an Alertmanager (or equivalent) fed from OpenObserve/metrics with a paging integration
  (PagerDuty/Opsgenie/Slack) targeting the on-call rotation. Define the on-call rotation.
- Alert rules for: service down, gate/verification failure surge, and audit-chain verify
  failure.

Phase 2 -- Security detection:
- Add auth-failure and anomalous-egress alert rules (pairs with the Job NetworkPolicy work,
  Factory#310 domain 12). Emit security-relevant events into OpenObserve with alertable fields.
- Extend or complement the CFactory anomaly detector with security signatures; revisit
  cost-spike detection (CFactory #14) as an abuse signal.

Phase 3 -- Prove the runbook:
- Run one tabletop exercise per scenario class (credential leak, evidence-store exposure,
  agent-shipped-malicious-code) and record results.
- Populate the notification contact matrix per legal entity; confirm the materiality
  decision-maker and regulator portals.
- Adopt the post-incident review template (this document, section 6) and run the first review
  off the tabletop.

Phase 4 -- Continuous improvement:
- Feed every real incident and tabletop back into severity thresholds, detection rules, and this
  runbook. Review annually and after each Sev-1/Sev-2.

## Acceptance criteria

- [ ] IR runbook published with severity classification, roles, and the full detect -> triage ->
      contain -> eradicate -> recover -> review lifecycle (this document).
- [ ] Breach-notification matrix documents SEC 4-business-day, NYDFS 72-hour, and GDPR 72-hour
      clocks with named who/when/how and a recorded notification decision procedure (this
      document).
- [ ] Forensics procedure references the tamper-evident audit chain and its air-gapped verifier.
- [ ] Alerting is wired so that a security or availability incident pages a human (Phase 1).
- [ ] Security detection exists beyond the pipeline heuristic (auth-failure/exfil signals)
      (Phase 2).
- [ ] At least one tabletop exercise has been completed and its post-incident review filed
      (Phase 3).
- [ ] On-call rotation and materiality decision-maker are named and reachable.

Checkboxes reflect status: the first three (documentation) are met by this deliverable; the
remainder are the tracked remediation items.

## Evidence artifacts

| Artifact | Location / how produced |
|---|---|
| This IR runbook + notification matrix | `Factory/docs/compliance/policies/incident-response.md` |
| Coordinated disclosure policy + SLAs | `PFactory/SECURITY.md`, `AIFactory/SECURITY.md`, `TFactory/SECURITY.md` |
| Tamper-evident audit chain (forensic timeline) | `PFactory/apps/web-server/server/services/audit_chain.py` |
| Air-gapped chain verifier output | `python -m server.audit verify-chain <export.ndjson>` (`PFactory/apps/web-server/server/audit/__main__.py`) |
| Anomaly detection (detective control) | `CFactory/apps/backend/cfactory/copilot/anomalies.py`; surfaced in `CFactory/apps/frontend-web/src/CopilotPanel.tsx` |
| Observability / log substrate | `factory-gitops/apps/observe/` (OpenObserve), `factory-gitops/apps/observe-auth/` |
| Incident records | GitHub private advisories / tracking issues per incident |
| Post-incident review reports | Filed under Factory#310 per incident (template: section 6) |
| Alerting configuration | Phase 1 deliverable (Alertmanager/paging manifests in `factory-gitops`) -- pending |
| Tabletop exercise record | Phase 3 deliverable -- pending |
