# Audit Logging, Retention and Alerting

- **Domain:** Audit logging completeness, retention and SIEM/alerting (Factory#313)
- **Parent epic:** Factory#310
- **Frameworks addressed:**
  - ISO/IEC 27001:2022 — A.8.15 (logging), A.8.16 (monitoring activities), A.8.17 (clock synchronisation)
  - SOC 2 — CC7.2 (monitor components for anomalies), CC7.3 (evaluate security events)
  - PCI DSS v4.0 — Requirement 10 (log all access, protect logs from tampering, 12-month retention with 3 months immediately available, daily review, time synchronisation)
  - SOX ITGC — audit trail over changes to systems that affect financial reporting
  - NYDFS 23 NYCRR 500 — 500.6 (audit trail; retain records supporting normal operations 5 years, cybersecurity-event records 3 years)
  - FedRAMP / NIST 800-53 — AU family: AU-2 (auditable events), AU-3 (content), AU-6 (review, analysis and reporting), AU-9 (protection of audit information), AU-11 (retention)

## Purpose

This document describes the audit-logging control for the Factory fleet: what
security-relevant events are recorded, how the records are protected from
tampering, how long they are kept, and how security events reach a reviewer or
an alert. It is written for an assessor: it credits the tamper-evidence
engineering that is genuinely strong, and it states plainly where coverage,
retention-policy formalisation, central aggregation, and alerting are not yet in
place.

Scope covers the four service planes (PFactory, AIFactory, TFactory, CFactory)
and the shared GitOps platform (`factory-gitops`). PCI DSS is in scope only if
cardholder data flows through the fleet (see Factory#310 applicability table);
its retention and daily-review requirements are documented here so the control
is ready if that scope is taken.

## Current state (grounded)

The fleet has a real, tested tamper-evident audit trail. This is a strength, not
a stub.

### Tamper-evident hash chain

- **Shared chain module** — `AIFactory`, `PFactory` and `TFactory` each ship the
  same `apps/web-server/server/services/audit_chain.py`. Every `audit_logs` row
  stores a `prev_hash`; the chain value is a SHA-256 over the previous row's hash
  plus a canonical encoding of the current row
  (`id|action|user_id|org_id|resource_type|resource_id|created_at|details_json`,
  joined with the ASCII unit separator `0x1f` so field values cannot forge the
  delimiter). The first row chains to a `GENESIS` sentinel.
- **Per-tenant chains** — `compute_tenant_hash` / `verify_tenant_chain` derive a
  per-org genesis (`GENESIS-T-<org_id>`) and a `tenant:<org_id>` domain
  separator, so one tenant's chain segment cannot be spliced into another's.
- **GDPR erasure preserves verifiability** — erasure replaces `user_id` with its
  SHA-256 and NULLs PII inside `details_json` before the hash is computed, so the
  chain re-verifies after a right-to-erasure request (module docstring, P5.5).
- **Write path** — `apps/web-server/server/services/audit_service.py`
  (`log_audit_event`) looks up the current chain head and sets `prev_hash` on
  every request-scoped write. Audit writes are failure-safe (wrapped in
  try/except) so a logging failure never crashes the caller.
- **CFactory** keeps a deliberately smaller, separate implementation:
  `apps/backend/cfactory/audit.py` records every confirmed human-in-the-loop
  action as an HMAC-SHA256-chained `audit_entries` row
  (`entry_hash = HMAC(secret, canonical(fields) + prev_hash)`), with
  `AuditStore.verify()` recomputing the chain to detect mutation, reordering or
  deletion. Migration `557faa62dcdc_audit_hmac_chain.py`.

### Daily signed anchor + air-gapped external verifier

- **Anchor signer** — `apps/web-server/server/services/audit_anchor.py` signs the
  daily chain head with HMAC-SHA256 under a 32-byte key that is KMS-wrapped
  (`crypto/kms`) and versioned in `audit_signing_keys`, so KMS root-key rotation
  does not invalidate prior anchors. The unwrapped key lives in a `_SigningKey`
  newtype whose `__repr__` never serialises the bytes; verification is
  constant-time (`hmac.compare_digest`). This raises the bar above the bare chain:
  a DB admin who can recompute the chain still cannot forge the anchor without the
  unwrapped HMAC key.
- **Scheduler** — `charts/aifactory/templates/cronjob-audit-anchor.yaml` runs
  `python -m server.jobs.audit_anchor_cron` daily at 00:00 UTC (explicit
  `timeZone: UTC`), hardened (`runAsNonRoot`, `readOnlyRootFilesystem`,
  `drop: ALL`). A per-tenant anchor variant exists
  (`per_tenant_anchor_key.py`, values `audit.anchor.perTenant`).
- **Air-gapped verifier** — `apps/web-server/server/audit/__main__.py`
  (`verify-chain <export.ndjson>`) re-computes the chain end-to-end using only
  stdlib plus the shared `audit_chain` module, so an operator can verify an
  exported log on a clean, disconnected machine. Export is served by
  `apps/web-server/server/routes/audit.py` and `services/audit_export.py`.

### Event coverage, retention and observability today

- **Events recorded** — the `ACTION_*` constants in `audit_service.py` cover
  user register/login, org create/update/delete, member invite/remove/role-change,
  project and task lifecycle, API-key create/revoke, and the MCP control-plane
  namespace (`mcp.task.*`, distinguished from UI-driven actions for review). An
  LLM audit hook (`services/llm_audit_hook.py`) records PII-redacted prompt and
  response rows when the LiteLLM gateway is enabled.
- **Retention** — retention is set per row at write time: AIFactory defaults
  `retention_until` to 13 months (395 days; SOC 2 12-month + buffer).
  `apps/web-server/server/jobs/audit_retention.py` deletes rows past
  `retention_until`. Object-store logs are lifecycled in
  `factory-gitops/apps/minio/manifests/manifests.yaml` — `role=log` prefixes
  expire at 30 days, evidence at 90 days. Anchor-row pruning is documented at
  `audit.anchor.perTenantOptions.retentionDays: 1825` (5 years) but the pruning
  job is not shipped.
- **Observability backend** — `factory-gitops/apps/observe` deploys OpenObserve
  (OTLP-native) as the fleet trace/metric/log sink; AIFactory emits OTLP spans
  when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (`charts/aifactory` deployment +
  values). Migration `20260525_f1c7b9d3a2e5_audit_hardening.py` hardens the audit
  schema across the three Python services.

## Gaps

### Event-coverage completeness

1. **Background events are unchained.** `log_audit_event_bg` in
   `audit_service.py` (AIFactory and PFactory) constructs `AuditLog(...)` without
   a `prev_hash`, so any event logged from a WebSocket handler, scheduler or other
   non-request path writes a NULL `prev_hash` and is not covered by the
   tamper-evident chain. `verify_chain` is order-sensitive and expects a
   continuous chain; unchained interleaved rows weaken the guarantee for the whole
   window. This is the highest-priority completeness gap.
2. **Security-relevant negative events are not enumerated.** The `ACTION_*` set
   captures successful control-plane actions but not authentication *failures*,
   authorization *denials*, gate *rejections*, or admin configuration changes as
   first-class audit actions. AU-2 / PCI 10.2 expect failed access attempts and
   privilege changes to be logged.
3. **No unified fleet audit stream.** Four separate stores (three sharing the
   module over per-service Postgres, CFactory on its own schema) mean no single
   chronological, cross-service audit view. An assessor tracing one actor's
   activity across PARR must correlate four logs by hand.

### Retention-policy formalisation

4. **No documented, per-framework retention policy.** Retention today is a code
   default (395 days) plus a MinIO ILM rule (logs 30 days). Nothing maps the
   retention windows to the strictest in-scope obligation:
   - PCI DSS 10.5.1 — at least 12 months, with 3 months immediately available.
     The 30-day MinIO log expiry is below this for any in-scope log class.
   - FedRAMP AU-11 — at least 90 days online plus retention per the records
     schedule.
   - NYDFS 500.6 — 5 years (normal-operations records) / 3 years
     (cybersecurity-event records).
   - SOX ITGC — financial-reporting change trails commonly retained 7 years.
   The policy must state one window per data class that meets the strictest
   applicable framework, and the code defaults and ILM rules must be reconciled to
   it. The retention deletion job is also not evidenced as running fleet-wide
   (CronJob described as manual / "lands in v1.0.1").

### SIEM ingestion

5. **Audit rows are not forwarded to a SIEM.** The tamper-evident `audit_logs`
   and `audit_entries` rows live only in each service's Postgres. OpenObserve
   ingests OTLP traces and metrics, not the audit rows, so there is no central,
   queryable, retention-governed store of security events and no cross-service
   correlation or daily-review surface (PCI 10.4, AU-6, CC7.2).

### Alerting on security events

6. **No security alerting exists.** There is no `PrometheusRule`, Alertmanager
   config, or OpenObserve alert anywhere in the fleet. Nothing fires on
   authentication-failure spikes, gate rejections, a chain-break detected by
   `verify_chain` / `AuditStore.verify()`, or an anchor-signature mismatch, and
   nothing alerts when the daily anchor CronJob *fails* (a silent anchor gap
   erodes the tamper-evidence guarantee). The CFactory anomaly detector is a UI
   heuristic, not security detection.

### Residual tamper-evidence limitation

7. **Anchor v1.1 residual.** The current anchor stops an attacker who can
   recompute the chain but does not hold the unwrapped HMAC key. An attacker with
   *both* DB write access *and* the unwrapped key can still rewrite chain and
   anchor together. Closing this needs external publication of the anchor (S3
   Object Lock / WORM, RFC 3161 timestamp authority, or Sigstore) — designed and
   documented, not yet shipped (v1.2).

## Remediation plan

Phased, cheapest-integrity-win first.

- **Phase 1 — chain completeness (highest priority).**
  - Route `log_audit_event_bg` through the same chain-head lookup as
    `log_audit_event` (or funnel both through one shared writer that always sets
    `prev_hash`) so no event is written unchained. This is a single shared-writer
    fix, not a per-caller patch.
  - Add `ACTION_*` constants and call sites for authentication failures,
    authorization denials, gate rejections, and admin/config changes.
- **Phase 2 — retention policy.**
  - Publish a per-data-class retention schedule meeting the strictest in-scope
    framework; reconcile the AIFactory default and the MinIO ILM rules to it
    (raise the 30-day log expiry where in scope for PCI/FedRAMP).
  - Ship the retention CronJob fleet-wide with evidence it runs; ship the anchor
    pruning job or document the manual procedure as a control.
- **Phase 3 — central aggregation / SIEM.**
  - Forward `audit_logs` / `audit_entries` to OpenObserve (or an external SIEM) as
    a dedicated, retention-governed stream, preserving `prev_hash` so the chain
    remains verifiable off the source DB. Provide a unified fleet audit view.
- **Phase 4 — alerting.**
  - Add alert rules (OpenObserve alerts and/or `PrometheusRule`) for
    auth-failure spikes, gate rejections, chain-break / anchor-mismatch on verify,
    and anchor-CronJob failure. Route to the on-call channel defined by the
    incident-response domain (Factory#310 child 9).
- **Phase 5 — anchor v1.2.**
  - Publish the daily anchor externally (S3 Object Lock / RFC 3161 TSA / Sigstore)
    to close the both-write-and-key residual.

## Acceptance criteria

- [ ] Every audit write path sets `prev_hash`; no NULL-`prev_hash` rows are
      produced by `log_audit_event_bg` or any background writer.
- [ ] Authentication failures, authorization denials, gate rejections and
      admin/config changes are recorded as distinct audit actions.
- [ ] A written retention policy exists, mapping each data class to a window that
      meets the strictest in-scope framework, and code defaults + MinIO ILM rules
      match it.
- [ ] The retention job (and anchor pruning) runs on a schedule with evidence of
      execution across all planes.
- [ ] Tamper-evident audit rows are forwarded to a central, retention-governed
      SIEM with a unified cross-service view.
- [ ] Alerts fire on auth-failure spikes, gate rejections, chain-break /
      anchor-mismatch, and anchor-CronJob failure, and route to on-call.
- [ ] Anchor v1.2 (external publication) is shipped, closing the
      DB-write-plus-key residual.

## Evidence artifacts

- **Chain + external verifier output** — an exported NDJSON audit log plus
  `python -m server.audit verify-chain <export.ndjson>` printing
  `OK: <n> rows verified` on a disconnected machine
  (`AIFactory/apps/web-server/server/audit/__main__.py`).
- **CFactory chain verify** — `AuditStore.verify()` returning an empty list
  (`CFactory/apps/backend/cfactory/audit.py`; tests in
  `CFactory/tests/test_audit.py`, `test_audit_secret_guard.py`).
- **Anchor signer + schedule** —
  `AIFactory/apps/web-server/server/services/audit_anchor.py`,
  `charts/aifactory/templates/cronjob-audit-anchor.yaml`, and anchor tests
  (`tests/audit/test_audit_anchor_service.py`, `test_audit_anchor_cron.py`).
- **Retention config** — per-row `retention_until` and
  `apps/web-server/server/jobs/audit_retention.py`; MinIO ILM rules in
  `factory-gitops/apps/minio/manifests/manifests.yaml`; anchor
  `retentionDays` in `charts/aifactory/values.yaml`.
- **Schema hardening migration** —
  `.../database/alembic/versions/20260525_f1c7b9d3a2e5_audit_hardening.py`
  (AIFactory / PFactory / TFactory).
- **Observability backend** — `factory-gitops/apps/observe/manifests/manifests.yaml`
  (OpenObserve OTLP ingest).
- **Alert rules** — to be added (Phase 4); none exist today.
