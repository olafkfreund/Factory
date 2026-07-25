# Risk Register

- **Owner:** Security Owner (CISO function) — see [roles.md](roles.md)
- **Review cadence:** Quarterly at the management review, and on any material change
- **Frameworks:** ISO/IEC 27001:2022 Clause 6.1.2 / 8.2; SOC 2 CC3.1-.4;
  SEC Reg S-K Item 106(b); FFIEC management

This is the fleet's living risk assessment. It is seeded from the real top gaps this
compliance program surfaced by inspecting the live code and manifests (not the marketing
summary), and it is maintained per the methodology below.

## Methodology

Each risk is a row: asset -> threat -> likelihood x impact -> treatment -> residual, with
a named owner. Scoring:

- **Likelihood** and **Impact** each 1-5 (1 rare/negligible, 5 almost certain/severe).
- **Inherent risk** = likelihood x impact (1-25). Bands: **Low** 1-6, **Medium** 8-12,
  **High** 15-25.
- **Existing controls** cite the real control (file, RFC, CI job) or "none".
- **Treatment** is one of mitigate / accept / transfer / avoid, with an owner and target
  wave.
- **Residual risk** is re-scored after the planned treatment is in place; it is not the
  current score until the treatment actually lands.
- **Risk owner** is named. Accepting a residual risk above the Medium band requires
  Security Owner sign-off recorded here.

Scores below are the assessment as of 2026-07-24. "Residual (target)" is the expected
score once the cited treatment wave completes; it does not yet reflect a closed control.

## Register

| ID | Asset | Threat / vulnerability | L | I | Inherent | Existing controls | Treatment (owner, wave) | Residual (target) | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-001 | Postgres job-state; MinIO evidence/artifacts | No backups of either store; RPO effectively unbounded; a node/volume loss or corruption is unrecoverable | 3 | 5 | 15 High | Tamper-evident audit chain assumes data survives (it would not); no `pg_dump`/WAL/versioning | Mitigate — off-cluster encrypted `pg_dumpall` + MinIO versioning/replication, then tested restore (BC/DR owner, Wave 2) | 5 (L1 x I5) | In progress (Factory#321) |
| R-002 | All application data and admin functions | Shared wildcard `APP_API_TOKEN` grants `is_service=True`, bypassing authz fleet-wide; broad blast radius | 3 | 5 | 15 High | Scoped `acw_` keys exist as target model; `#555` deprecation is log-only, token still live | Mitigate — retire wildcard for scoped per-service credentials; remove `is_service` blanket bypass (IAM owner, Wave 2) | 5 (L1 x I5) | Open (Factory#312) |
| R-003 | Postgres, MinIO, Redis, Keycloak volumes | No encryption at rest; K8s Secrets base64-only in etcd (no EncryptionConfiguration); cluster-internal cleartext | 3 | 4 | 12 Medium | TLS at Cloudflare edge; agenix host key; volume access-control only | Mitigate — at-rest encryption + KMS/envelope, etcd EncryptionConfiguration (encryption owner, Wave 3) | 4 (L1 x I4) | Open (Factory#314) |
| R-004 | Personal data in task content | PII egresses to third-party LLM providers by default; outbound redaction is off by default and the redactor fails open | 4 | 4 | 16 High | `llm_pii_redactor.py` (audit-row only by default); `EgressClass=LOCAL` lever; egress guards (default off) | Mitigate — default `scrubBeforeSend` on; fix fail-open; publish sub-processor list (data owner, Wave 1) | 8 (L2 x I4) | In progress (Factory#320) |
| R-005 | Production deployments | Weak separation of duties: push-to-`main` auto-deploys, ArgoCD self-heals, one actor can author+merge+deploy; branch protection uneven and admin-bypassable | 3 | 4 | 12 Medium | PR review + CI gates; branch protection on 3/6 repos; Fides change-gate built but unwired | Mitigate — branch protection as code fleet-wide; deploy approvals; four-eyes via Fides; signed commits (change-mgmt owner, Wave 3) | 4 (L1 x I4) | In progress (Factory#316) |
| R-006 | Verification evidence in MinIO | ILM expires objects at 30 days while retention is claimed at 90 days/13 months; evidence can be purged before its claim closes | 4 | 3 | 12 Medium | MinIO ILM rules exist but misconfigured; `audit_retention.py` (13-month) for audit rows | Mitigate — correct ILM to the intended 90-day/13-month floor (audit-logging owner, Wave 1) | 3 (L1 x I3) | In progress (Factory#313/#321) |
| R-007 | Postgres, MinIO | Single-instance on node-local RWO storage; no HA, no versioning/replication; a single node failure is an outage and potential data loss | 3 | 4 | 12 Medium | Single replica each; `nfs` RWX exists but itself single-backed | Mitigate — HA Postgres with PITR (e.g. CloudNativePG); redundant object store; off single-node storage (BC/DR owner, Wave 3) | 6 (L2 x I3) | Open (Factory#321) |
| R-008 | CFactory container images | CFactory ships unscanned and unsigned (no Trivy, no SBOM, no cosign), and there is no signature-verification admission gate cluster-wide | 3 | 4 | 12 Medium | Cosign + dual SBOM + Trivy on PFactory/AIFactory/TFactory; CodeQL on all five | Mitigate — bring CFactory to parity; add Kyverno/policy-controller image-verification gate (supply-chain owner, Wave 2) | 4 (L1 x I4) | Open (Factory#317/#318) |
| R-009 | Detection and response capability | No alerting or paging and no security detection layer beyond a pipeline heuristic; incidents may go unnoticed; the IR runbook is untested | 4 | 4 | 16 High | Audit chain + air-gapped verifier for forensics; `SECURITY.md` disclosure (3/6 repos) | Mitigate — alerting on anchor-failure/chain-break/auth-spikes; paging; tabletop the runbook (IR owner, Wave 1) | 6 (L2 x I3) | In progress (Factory#313/#319) |
| R-010 | Human and admin accounts | MFA not enforced at the IdP; a phished/leaked credential grants access without a second factor | 3 | 4 | 12 Medium | Keycloak SSO with GitHub upstream; org RBAC | Mitigate — enforce TOTP/WebAuthn required-action; export realm to gitops (IAM owner, Wave 2) | 4 (L1 x I4) | Open (Factory#312) |
| R-011 | Audit trail completeness | Background/WebSocket events write NULL `prev_hash` (unchained); negative events (auth/authz failures) not first-class; a gap weakens tamper-evidence and forensics | 3 | 3 | 9 Medium | Foreground hash-chain + daily signed anchor + verifier | Mitigate — chain background events; enumerate negative `ACTION_*`; forward to a SIEM (audit-logging owner, Wave 2) | 3 (L1 x I3) | Open (Factory#313) |
| R-012 | Per-task untrusted-code Jobs | No microVM/syscall boundary and coarse `443 -> 0.0.0.0/0` egress; a sandbox escape or data-exfil path is not fully contained | 2 | 4 | 8 Medium | bwrap sandbox (#363, default-on); per-task NetworkPolicy + non-root securityContext (default-on); gVisor wired but deferred | Mitigate — per-destination egress allowlist; PodSecurity Admission on task namespaces; evaluate microVM where substrate allows (runtime owner, Wave 3) | 4 (L2 x I2) | Partially mitigated (Factory#322) |
| R-013 | Trusted-plan signing keys | HMAC plan-signing keys have no key ID, expiry, or rotation; a leaked key cannot be cleanly rotated/revoked | 2 | 4 | 8 Medium | Signed task contracts (RFC-0002); injection/egress guards; independent verification | Mitigate — add `kid`, expiry, rotation; approved-model registry with eval gate; output DLP (agentic-AI owner, Wave 3) | 4 (L2 x I2) | Open (Factory#323) |

## Risk-acceptance log

No residual risk above the Medium band has been formally accepted. Any acceptance (for
example, deferring HA Postgres and accepting R-007's single-instance risk for a defined
period) is recorded here with the Security Owner's sign-off, a compensating control, and
an expiry date, and is revisited at the next management review.
