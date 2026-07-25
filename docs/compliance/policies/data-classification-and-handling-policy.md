# Data Classification and Handling Policy

- **Policy owner:** Security Owner (CISO function) — see [roles.md](../roles.md)
- **Applies to:** All data created, processed, or stored by the fleet
- **Review cadence:** Annually
- **Frameworks:** ISO/IEC 27001:2022 A.5.9-.14, A.8.10-.12; SOC 2 C1, P-series;
  GDPR Art. 5/6/17/28/30; NYDFS 500.13; NIST MP, SC-28

Control detail and current-state grounding live in
[data-governance.md](data-governance.md) (Factory#320).

## Purpose

To define how data is classified and how each class must be handled across its
lifecycle — including the specific case of PII crossing to third-party LLM providers,
which is the fleet's principal data-protection risk.

## Classification scheme

Classify by the most sensitive data an asset holds, considering both where it rests and
where it flows.

| Class | Definition | Examples | Handling floor |
|---|---|---|---|
| Public | Intended for public release | Published docs, blog, public repo code | No restriction |
| Internal | Non-public operational data | Task specs, plans, logs, metrics | Access-controlled; not shared externally |
| Confidential | Would cause harm if disclosed | Credentials, audit records, verification evidence, private source | Least-privilege access; encrypt at rest (target); tamper-evident where it is an audit record |
| Regulated | Personal or legally regulated data | PII, customer content that may contain PII | Minimize; redact before third-party egress; retention and erasure obligations apply |

## Policy statements

1. **Classify before you handle.** Data is treated at its class; when in doubt, treat as
   the higher class. Regulated data is minimized — do not introduce real PII where
   synthetic data suffices.
2. **PII egress is controlled.** Personal data sent to third-party LLM providers must be
   redacted. The redactor (`llm_pii_redactor.py`) currently runs on the audit row by
   default, not on the outbound request; enabling outbound scrubbing by default
   (`scrubBeforeSend`) is Wave 1 remediation and is recorded as risk R-004. Where data
   must not leave the boundary at all, route to a local model (the `EgressClass=LOCAL`
   lever, p510 Ollama) rather than a managed cloud provider.
3. **Redaction must not fail silently.** A redactor that fails open (passes content
   through unredacted on error) is a data-protection defect; failures are surfaced and
   treated, not swallowed.
4. **Retention is defined and enforced.** Audit records are retained 13 months (395
   days); verification evidence is intended to be retained to a 90-day/13-month floor.
   The MinIO ILM rule currently expires objects at 30 days, which can purge evidence
   before its claim closes — this durability bug is risk R-006 and Wave 1 remediation.
   Durable Postgres state has no retention policy yet (tracked, Factory#320).
5. **Encrypt confidential and regulated data at rest.** At-rest encryption for Postgres,
   MinIO, and Redis is not yet implemented (risk R-003); until it is, access to the
   underlying volumes is a compensating control and the gap is tracked (Factory#314).
6. **Data-subject obligations.** Regulated data carries retention, sub-processor
   disclosure, and erasure obligations. A per-record DSAR/erasure path (beyond
   whole-tenant tear-down) is a tracked gap; the DPIA/ROPA reference is
   `AIFactory/guides/compliance/dpia-data-flow.md`.

## Roles and responsibilities

- **Data owner (control owner, data governance)** — maintains the classification scheme,
  the redaction and retention controls, and the sub-processor list.
- **Contributors and operators** — classify data correctly and avoid introducing
  regulated data unnecessarily.
- **Security Owner** — owns the policy and approves exceptions.

## Related controls

- [data-governance.md](data-governance.md) — domain assessment and evidence
- [encryption-key-mgmt.md](encryption-key-mgmt.md) — at-rest encryption (R-003)
- [audit-logging.md](audit-logging.md) — evidence retention (R-006)
- [vendor-and-third-party-policy.md](vendor-and-third-party-policy.md) — LLM-provider data flow
- [risk-register.md](../risk-register.md) — R-003, R-004, R-006
