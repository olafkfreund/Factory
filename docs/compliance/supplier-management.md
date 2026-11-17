# Supplier Management: Vendor and Sub-processor Register

- **Policy owner:** Security Owner (CISO function) — see [roles.md](roles.md)
- **Review cadence:** Annually per vendor, and on any material change
- **Frameworks:** ISO/IEC 27001:2022 A.5.19-A.5.22; SOC 2 CC9.2 and CC6.4 (inherited
  physical security); NYDFS 500.11 (reference only, not applicable: see
  [framework-applicability.md](framework-applicability.md)); FFIEC outsourcing booklet;
  GDPR Art. 28
- **Issue:** Factory#3695

This operationalizes [vendor-and-third-party-policy.md](policies/vendor-and-third-party-policy.md).
It is a procedure and a register skeleton. It does not state which terms are in force or
which assurance reports are held: those are for the Security Owner to record from the
contracts and provider documents. A.5.20, A.5.22 and CC9.2 stay Planned/Gap until then.

## 1. Register

One row per supplier that processes fleet data or runs fleet code. "Owner to record"
means the Security Owner fills it from the provider's own documents, citing the document
and date.

| Supplier | Function | Data processed | Sub-processor of fleet data? | Processor terms in force | Assurance report (SOC 2 / ISO) | Last review |
|---|---|---|---|---|---|---|
| Anthropic | LLM provider | Task content sent to agents (PII-scrubbed outbound, see [data-governance.md](policies/data-governance.md)) | Yes | Owner to record | Owner to record | Owner to record |
| OpenAI | LLM provider | Same | Yes | Owner to record | Owner to record | Owner to record |
| Local model host (Ollama on the operator host) | Self-hosted LLM, the egress-class `LOCAL` option | Task content, stays on host | No (operator-run) | Not applicable, owner to confirm | Not applicable | Owner to record |
| GitHub | Source, CI/CD, OIDC | Source code, workflow logs | Yes | Owner to record | Owner to record | Owner to record |
| Cloudflare | Edge, TLS, tunnel | Traffic metadata and transit | Yes | Owner to record | Owner to record | Owner to record |
| Hosting substrate (operator host or cloud) | Cluster, storage | All fleet data at rest | Owner to record | Owner to record | Owner to record (CC6.4 inherited physical security) | Owner to record |

Add rows for any supplier found by the annual re-review. Publishing: the owner
publishes the sub-processor columns of this register where a customer can read them
(for example the documentation site), and records the date and place.

## 2. Processor-terms checklist (per supplier)

- [ ] Does the supplier process personal data for the fleet? If no, record why.
- [ ] A processor agreement or DPA is in force (record document and date), or the gap is recorded.
- [ ] It restricts use to our instructions, and states retention and deletion.
- [ ] It lists the supplier's own sub-processors, and says how changes are notified.
- [ ] Breach notification time is stated and is compatible with the incident-response
      timelines in [incident-response.md](policies/incident-response.md).
- [ ] Audit or assurance rights are stated, or an assurance report replaces them.
- [ ] Transfer mechanism is stated for any cross-border processing.
- [ ] Training-data use: the provider does not train on fleet data, or the gap is recorded.

## 3. Assurance reports

For each supplier the owner requests the latest SOC 2 Type II report or ISO 27001
certificate, evaluates scope, period and exceptions, and records the document, period
and any complementary user-entity controls the fleet must supply. A report that cannot be
obtained stays a recorded gap in the register with a compensating note (for example
reduced data shared). For the hosting substrate, this report is the evidence for the
inherited physical security in SOC 2 CC6.4.

## 4. Annual re-review

Once a year and on any material change (a vendor breach, a change in data shared):

1. Re-confirm the register rows against the current contracts and the provider's documents.
2. Check each assurance report's period still covers the review date.
3. Check the sub-processor list for changes.
4. Record findings in the [risk register](risk-register.md) and the management review.

### Annual re-review record (template)

> TEMPLATE: not a record. Leave every field empty until the review has happened.

| Field | Value |
|---|---|
| Review year | |
| Date held | |
| Reviewer | |
| Suppliers reviewed | |
| Terms and reports confirmed (document, date) | |
| Gaps and compensating notes | |
| Changes since last review | |
| Actions (owner, due date) | |
| Signature | |
