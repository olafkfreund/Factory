# Data Governance, Classification, Retention and PII Egress

- **Domain:** Data governance (Factory#320)
- **Parent epic:** Factory#310
- **Frameworks addressed:**
  - ISO/IEC 27001:2022 — A.5.9 (inventory of information and assets), A.5.10 (acceptable use), A.5.11 (return of assets), A.5.12 (classification of information), A.5.13 (labelling), A.5.14 (information transfer); A.8.10 (information deletion), A.8.11 (data masking), A.8.12 (data leakage prevention)
  - SOC 2 — C1.1/C1.2 (confidentiality: identify and protect confidential information, dispose of it); P-series privacy criteria (P1 notice, P4 use/retention, P5 access, P6 disclosure to third parties, P8 monitoring)
  - PCI DSS v4.0 — Requirement 3 (protect stored account data; do not retain cardholder data longer than necessary)
  - GDPR — Art. 5 (storage limitation, integrity/confidentiality), Art. 6 (lawful basis), Art. 17 (erasure), Art. 28 (processor/sub-processor), Art. 30 (records of processing), Art. 44-49 (transfers)
  - NYDFS 23 NYCRR 500 — 500.13 (asset management and data retention limits)
  - FedRAMP (NIST 800-53) — MP family (media protection), SC-8/SC-28 (transmission and at-rest confidentiality), SI-12 (information handling and retention)

## Purpose

This document establishes how the Factory fleet classifies the data it holds, how long
each class is retained, and how it controls personal data (PII) leaving the trust
boundary — most acutely, the PII that flows outbound to third-party LLM providers
(Anthropic, OpenAI, Bedrock, Vertex) on every task. It is the assessor-facing statement
of the fleet's confidentiality, privacy, and retention posture, and it is honest about
the two structural gaps the 2026-07-23 audit flagged as fleet gap #7: PII is sent to LLM
providers by default, and there is no classification scheme or Postgres-level retention
policy behind the per-store lifecycle rules that already exist.

## Current state (grounded)

The fleet has real, working data-handling machinery — a PII redactor, per-store lifecycle
rules, tenant isolation, and a first-class local-model egress option — but the machinery
is configured conservatively (opt-in, backward-compatible) and is not yet backed by a
classification scheme or a documented retention/residency policy. What exists:

### What data flows where

The authoritative inventory is the AIFactory DPIA
(`AIFactory/guides/compliance/dpia-data-flow.md`), which carries a GDPR Art. 30 Records of
Processing table and a per-store PII inventory. In summary, personal data can exist in:

- **Free-form prompt/spec text** — authored by users, may contain arbitrary pasted PII.
  This is the primary uncontrolled ingress point.
- **Outbound LLM request bodies** — prompt + context sent to the model provider on every
  call. Recipients include the third-party LLM vendor.
- **LLM audit rows** — prompt/response captured per call into Postgres (`audit_hooks`).
- **Workspace artifacts** — files the agent writes (MinIO/S3 or PVC), may contain PII.
- **Auth/identity** — email, display name, IdP `sub`, login timestamps (from OIDC/SAML).
- **Audit logs** — user ID, action, request fingerprint, IP, user-agent.

### Redaction posture

The LLM PII redactor lives at
`AIFactory/apps/backend/services/llm_pii_redactor.py` (Epic #35/#38, v1.2 #210). It applies
built-in regex patterns plus operator-supplied custom patterns:

- US SSN (hyphenated `\d{3}-\d{2}-\d{4}` only — bare 9-digit runs are excluded to avoid
  false positives against order/record IDs)
- Email, US phone (parenthesised and hyphenated forms)
- Credit-card numbers: 13-19 digit runs validated with a Luhn checksum (runs that fail
  Luhn are left unchanged, which removes the false-positive problem that dropped CC
  detection from v1.1)

The critical posture fact: by default the redactor runs on the **audit row only**, not on
the outbound request. The module's own docstring states it plainly: "A high-sensitivity
tenant whose prompt contains PII still sends that PII to the LLM provider." The
`scrubBeforeSend` mode (`scrub_outbound=True`) that would redact the outbound prompt is
opt-in, gated on `LITELLM_AUDIT_SCRUB_OUTBOUND=true`, and defaults to `False`
(`_env_scrub_outbound_default()` in
`AIFactory/apps/backend/providers/openai_compatible.py`). The redactor is also
failure-safe in a way that widens exposure: if the web-server's PYTHONPATH cannot import
the redactor, the audit hook proceeds **without redaction** rather than failing
(`llm_audit_hook.py` `_build_redactor` -> `_PassthroughRedactor`).

Two egress guards exist but are command-layer/broker-layer, not data-content DLP, and both
default off:

- `AIFactory/apps/backend/security/egress.py` — blocks allowlisted network commands
  (`curl`, `wget`, `ssh`, ...) run by the agent; opt-in via `AIFACTORY_EGRESS_POLICY`
  (default `off`). It is a compensating control for pods without a default-deny
  NetworkPolicy, and it inspects command targets, not payload content.
- `PFactory/apps/backend/pfactory_secrets/egress.py` — an honest-egress manifest for the
  credential broker; the per-project egress gate defaults OFF
  (`.pfactory.yml` `egress.enabled`).

### Local-model egress option

The fleet has a genuine data-residency lever for LLM calls. `PFactory/apps/backend/byo_llm.py`
classifies every model endpoint into an `EgressClass`: `LOCAL` (localhost/LAN — "no data
egress"), `SELF_HOSTED` (your own routable server), or `MANAGED_CLOUD` (third-party managed
API). An Ollama endpoint on a local host classifies as `LOCAL`; the fleet runs local
models on the p510 Ollama host today. Choosing a local or self-hosted model is therefore
the one control that removes third-party PII egress entirely — but it is an operator
deployment choice, not a policy default, and it is not yet tied to any data class.

### Retention

Retention is real but per-store and uneven, not policy-driven:

- **MinIO/object store** — lifecycle (ILM) rules in
  `factory-gitops/apps/minio/manifests/manifests.yaml`: logs expire at 30 days, evidence at
  90 days (evidence must outlive the VAL claim that references it).
- **Evidence workspaces** — `PFactory/apps/backend/agents/evidence/retention.py` and the
  TFactory twin: failures kept `forever`, flagged `90_days`, passing `7_days`, plus a
  per-task size cap (default 500MB), keyed off the verdict.
- **LLM audit rows** — 13 months (395 days) in `llm_audit_hook.py` (SOC 2 12-month evidence
  + 1-month buffer); the general audit retention job uses the same 13-month default.
- **Prometheus metrics** — default 15-day retention (aggregated/anonymised).

Tenant/org isolation exists (tear-down on `Organization.deleted_at`), which is the closest
thing to an erasure mechanism today.

### What is missing

There is **no data-classification scheme** anywhere in the fleet (no tiers, no labels, no
asset inventory tied to classes), **no retention policy for the Postgres durable job-state**
(only logs/evidence/audit rows have retention; the operational databases that hold specs,
task records, and prompt history do not), **no data-residency statement**, and **no
DSAR/right-to-erasure tooling** beyond whole-tenant tear-down.

## Data classification scheme

The fleet adopts a four-tier scheme. Every data store and data flow is assigned exactly one
tier (the highest tier of any element it contains), and handling rules follow from the tier.

| Tier | Definition | Examples in the fleet | Handling rules |
|---|---|---|---|
| **Public** | Intended for or already in the public domain; disclosure causes no harm. | Published docs, blog posts, open-source code, public API schemas, aggregated/anonymised metrics. | No restriction. May leave the boundary freely. |
| **Internal** | Non-public operational data; disclosure is undesirable but low-impact. | Task metadata, build logs, non-PII spec text, tokens/cost counts, Prometheus series. | Access limited to authenticated fleet users. 30-90 day retention per store. No third-party egress except the LLM call where required. |
| **Confidential** | Sensitive business or security data; disclosure causes material harm. | Prompt/spec bodies, LLM request/response content, workspace artifacts, audit rows, credentials/secrets (which also fall under Factory#316 secrets policy). | Encrypt in transit and at rest. Access on least-privilege. Redact before any third-party egress. Retention bounded and documented. Erasure on tenant tear-down. |
| **Regulated** | Data whose handling is dictated by law/contract: PII, cardholder data (PCI), or customer data under a DPA. | Any prompt/artifact/audit content containing PII (SSN, email, phone, PAN); auth identity data; customer data pasted under a B2B DPA. | All Confidential rules PLUS: **must not be sent to a third-party (MANAGED_CLOUD) LLM in the clear** — either scrubbed (`scrub_outbound`) or routed to a LOCAL/SELF_HOSTED model. Data-residency honoured. DSAR/erasure supported. Sub-processor disclosed. Retention set to the minimum necessary. |

Labelling: because the primary ingress (free-form prompt text) is user-authored and cannot
be reliably classified at rest, the scheme classifies by **store and flow** (a store that
can contain PII is Regulated) rather than by per-record scanning. The LLM request path is
treated as Regulated-by-default, which is what forces `scrub_outbound` on (see Remediation).

## Gaps

1. **PII egress to LLM providers by default (fleet gap #7).** Outbound scrubbing
   (`scrub_outbound`) defaults off; the redactor protects the audit row, not the request
   sent to Anthropic/OpenAI. For Regulated data this is a confidentiality and GDPR
   Art. 44 transfer exposure. The redactor's PYTHONPATH failure-safe further degrades to
   no redaction silently.
2. **No data-classification scheme.** Nothing assigns tiers or labels to stores/flows, so
   there is no basis for tier-driven handling, and A.5.12/C1.1 have no evidence.
3. **No retention policy for Postgres durable state.** Logs, evidence, and audit rows have
   retention; the operational databases (specs, task records, prompt history) do not. Fails
   GDPR Art. 5 storage limitation, NYDFS 500.13, PCI 3, SI-12.
4. **No data-residency statement** and **no documented sub-processor list** at the fleet
   level (the DPIA names the categories but the operator-facing register is not published).
5. **No DSAR / right-to-erasure tooling** for individual data subjects; only whole-tenant
   tear-down exists (GDPR Art. 17).
6. **Egress guards are command/target-level, not content DLP.** No output-side DLP inspects
   payload content leaving the boundary (overlaps Factory#313 agentic-AI governance).

## Remediation plan

Phased so the highest-exposure gap (default PII egress) closes first.

### Phase 1 — Regulated data does not leave in the clear (closes gap #1)

- Flip the deployment default so `LITELLM_AUDIT_SCRUB_OUTBOUND=true` (scrub-before-send on)
  for any deployment handling Regulated data; document the residual prompt-quality trade-off.
- Change the redactor's PYTHONPATH import failure from fail-open (passthrough) to fail-closed
  for Regulated deployments, or make the missing-redactor condition a startup assertion so a
  misconfigured deployment cannot silently ship PII to the provider.
- Publish the LOCAL/SELF_HOSTED model routing (`byo_llm.py` `EgressClass`) as the sanctioned
  path for Regulated data: no third-party egress at all.
- Publish the sub-processor list (LLM vendors, KMS, IdP, Postgres/object-store host) and the
  DPA references, seeded from the DPIA's ROPA table.

### Phase 2 — Classification and labelling (closes gaps #2, #4)

- Ratify the four-tier scheme above; produce the store-and-flow inventory that assigns each
  Postgres table, MinIO prefix, and LLM flow a tier (extend the DPIA data inventory).
- Publish a data-residency statement (where each store physically lives; which flows cross
  a border).

### Phase 3 — Retention automation and erasure (closes gaps #3, #5)

- Define retention for every Postgres store keyed by tier, and automate pruning the same way
  logs/evidence/audit rows are already pruned (reuse the `audit_retention` job pattern).
- Build a DSAR/erasure path for an individual data subject (search + tombstone across
  Postgres audit rows and workspace artifacts), not only whole-tenant tear-down.
- Add output-side content DLP on the egress path (coordinate with Factory#313).

## Acceptance criteria

- [ ] Four-tier classification scheme (public/internal/confidential/regulated) ratified and
      published, with handling rules per tier.
- [ ] Every Postgres store, MinIO prefix, and LLM flow assigned a tier (store-and-flow
      inventory published, extending the DPIA data inventory).
- [ ] Regulated data is not sent to a third-party (MANAGED_CLOUD) LLM in the clear:
      `scrub_outbound` default-on for Regulated deployments AND/OR LOCAL/SELF_HOSTED routing
      documented as the sanctioned path.
- [ ] Redactor no longer fails open silently — missing-redactor is fail-closed or a startup
      assertion for Regulated deployments.
- [ ] Retention policy documented and automated for Postgres durable state (not only
      logs/evidence/audit rows).
- [ ] Data-residency statement published.
- [ ] Sub-processor list published with DPA references.
- [ ] DSAR / right-to-erasure path exists for an individual data subject (beyond tenant
      tear-down).

## Evidence artifacts

| Control area | Artifact | Location |
|---|---|---|
| PII redaction (built-in + custom patterns, Luhn CC) | `llm_pii_redactor.py` | `AIFactory/apps/backend/services/llm_pii_redactor.py` |
| Audit-row redaction + retention + failure-safe | `llm_audit_hook.py` | `AIFactory/apps/web-server/server/services/llm_audit_hook.py` |
| Outbound scrub default (`scrubBeforeSend`, default off) | `_env_scrub_outbound_default` | `AIFactory/apps/backend/providers/openai_compatible.py` |
| Local/self-hosted egress classification | `byo_llm.py` (`EgressClass`) | `PFactory/apps/backend/byo_llm.py` |
| Agent command-layer egress guard | `security/egress.py` | `AIFactory/apps/backend/security/egress.py` |
| Credential-broker honest-egress manifest | `pfactory_secrets/egress.py` | `PFactory/apps/backend/pfactory_secrets/egress.py` |
| Object-store lifecycle (logs 30d / evidence 90d) | MinIO ILM manifest | `factory-gitops/apps/minio/manifests/manifests.yaml` |
| Evidence retention (failures/flagged/passing + size cap) | `agents/evidence/retention.py` | `PFactory/apps/backend/agents/evidence/retention.py` (+ TFactory twin) |
| Audit retention (13-month default) | `audit_retention.py` | `{AIFactory,PFactory,TFactory}/apps/web-server/server/jobs/audit_retention.py` |
| Data-flow, ROPA (Art. 30), PII inventory | DPIA data-flow | `AIFactory/guides/compliance/dpia-data-flow.md` |
| Redaction/egress tests | `test_pii_redactor.py`, `test_secrets_egress.py` | `AIFactory/tests/llm_gateway/`, `{PFactory,TFactory}/tests/` |
