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
- **Mitigated** means the whole treatment has landed and been measured, so the
  Residual score is the current score. A partly landed treatment is re-scored
  as "Current" with its date and stays In progress or Open.

Scores below are the assessment as of 2026-07-24. "Residual (target)" is the expected
score once the cited treatment wave completes; it does not yet reflect a closed control.
Rows R-001, R-006, R-007, R-008, R-009, R-011 and R-013 were re-measured on 2026-11-07
([spec](../../spec/2026-11-07-324-compliance-records-refresh.md)). Their L, I and
Inherent stay as assessed, and the Residual column gives the current score with
its date.

## Register

| ID | Asset | Threat / vulnerability | L | I | Inherent | Existing controls | Treatment (owner, wave) | Residual (target) | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-001 | Postgres job-state; MinIO evidence/artifacts | No backups of either store; RPO effectively unbounded; a node/volume loss or corruption is unrecoverable _(state at 2026-07-24; see Existing controls for 2026-11-07)_ | 3 | 5 | 15 High | CronJob `postgres-backup` (`15 2 * * *`, factory-gitops `apps/backups/manifests/manifests.yaml`) last succeeded 2026-11-07T02:15:06Z, last three Jobs Complete, dumps `factory-backups/postgres/factory-cluster-2026110{3..7}T0215*Z.sql.gz`; Job `minio-create-bucket` (completed 2026-10-22T21:49:16Z) enabled versioning on `factory-artifacts`, `factory-backups` and `factory-evidence` and read back lifecycle rule `backups-14d` (factory-gitops `apps/minio/manifests/manifests.yaml:335-361`); restore drill 2026-08-10 in `dr-runbook.md` (commit 03c87f8, #662). The gap that remains: the dumps share the host and volume class with Postgres and with the evidence store (dr-runbook.md single-failure-domain); MinIO itself is not backed up | Mitigate — off-cluster encrypted `pg_dumpall` + MinIO versioning/replication, then tested restore (BC/DR owner, Wave 2); remaining gap tracked in Factory#3681 | Current 10 (L2 x I5) 2026-11-07; target 5 | In progress (Factory#3681 off-cluster copy; MinIO backup and scheduled re-drill: no open issue) |
| R-002 | All application data and admin functions | Shared wildcard `APP_API_TOKEN` grants `is_service=True`, bypassing authz fleet-wide; broad blast radius | 3 | 5 | 15 High | Scoped `acw_` keys exist as target model; `#555` deprecation is log-only, token still live | Mitigate — retire wildcard for scoped per-service credentials; remove `is_service` blanket bypass (IAM owner, Wave 2) | 5 (L1 x I5) | Open (Factory#312) |
| R-003 | Postgres, MinIO, Redis, Keycloak volumes | No encryption at rest; K8s Secrets base64-only in etcd (no EncryptionConfiguration); cluster-internal cleartext | 3 | 4 | 12 Medium | TLS at Cloudflare edge; agenix host key; volume access-control only | Mitigate — at-rest encryption + KMS/envelope, etcd EncryptionConfiguration (encryption owner, Wave 3) | 4 (L1 x I4) | Open (Factory#314) |
| R-004 | Personal data in task content | PII may egress to third-party LLM providers when the deployment kill-switch is set or via two unscrubbed direct CLI spawns (AIFactory#1860) | 4 | 4 | 16 High | `llm_pii_redactor.py` (outbound scrub on by default, fails closed; mandatory for `regulated` projects); `EgressClass=LOCAL` lever; egress guards (default off) | Mitigate — close the CLI-spawn gap (AIFactory#1860); publish sub-processor list (data owner, Wave 1) | 8 (L2 x I4) | In progress (Factory#320) |
| R-005 | Production deployments | Weak separation of duties: push-to-`main` auto-deploys, ArgoCD self-heals, one actor can author+merge+deploy; branch protection uneven and admin-bypassable | 3 | 4 | 12 Medium | PR review + CI gates; branch protection on 3/6 repos; Fides change-gate built but unwired | Mitigate — branch protection as code fleet-wide; deploy approvals; four-eyes via Fides; signed commits (change-mgmt owner, Wave 3) | 4 (L1 x I4) | In progress (Factory#316) |
| R-006 | Verification evidence in MinIO | ILM expires objects at 30 days while retention is claimed at 90 days/13 months; evidence can be purged before its claim closes _(state at 2026-07-24; see Existing controls for 2026-11-07)_ | 4 | 3 | 12 Medium | Job `minio-create-bucket` (completed 2026-10-22T21:49:16Z) read back ILM rules `evidence-*-90d` and `log-*-30d` on `factory-artifacts`, `evidence-90d` on `factory-evidence` and `backups-14d` on `factory-backups`, and fails if a rule ID is missing (factory-gitops `apps/minio/manifests/manifests.yaml:335-361`); `audit_retention.py` (13-month) for audit rows. The gap that remains: the treatment's 13-month floor is in no ILM rule, and the `factory-evidence` 90-day expiry is shorter than the 12-month SOC 2 window that its own manifest comment names | Mitigate — correct ILM to the intended 90-day/13-month floor (audit-logging owner, Wave 1); remaining gap: no open issue | Current 6 (L2 x I3) 2026-11-07; target 3 | In progress (no open issue) |
| R-007 | Postgres, MinIO | Single-instance on node-local RWO storage; no HA, no versioning/replication; a single node failure is an outage and potential data loss _(state at 2026-07-24; see Existing controls for 2026-11-07)_ | 3 | 4 | 12 Medium | Single replica each (`postgres` StatefulSet and `minio` Deployment both `replicas: 1`) on node-local storage; `nfs` RWX exists but itself single-backed; versioning on all three buckets (`minio-create-bucket`, 2026-10-22) | Mitigate — HA Postgres with PITR (e.g. CloudNativePG); redundant object store; off single-node storage (BC/DR owner, Wave 3); remaining gap: no open issue | 6 (L2 x I3) | Open (no open issue; Factory#321 closed) |
| R-008 | CFactory container images | CFactory ships unscanned and unsigned (no Trivy, no SBOM, no cosign), and there is no signature-verification admission gate cluster-wide _(state at 2026-07-24; see Existing controls for 2026-11-07)_ | 3 | 4 | 12 Medium | CFactory `image-build.yml:164,199,233` runs Trivy as a HIGH/CRITICAL gate; `deploy.yml:242-243` runs `cosign sign` by digest and `deploy.yml:139-151,266` attests a dual SBOM (deploy runs on `main` succeeded 2026-10-24 to 2026-10-30); Kyverno ClusterPolicy `verify-factory-image-signatures` is `Enforce` and Ready, rule `verify-cfactory-signature` covers `cfactory` and `cfactory-frontend` with an exact deploy.yml subject, and running image `cfactory:sha-b24d6f4` passes `cosign verify`; CFactory#191 merged, Factory#522 closed. The gap that remains: `failurePolicy: Ignore` fails open when Kyverno is unavailable, and some first-party images are not yet fail-closed | Mitigate — bring CFactory to parity; add Kyverno/policy-controller image-verification gate (supply-chain owner, Wave 2) | Current 8 (L2 x I4) 2026-11-07; target 4 | In progress (Factory#3665) |
| R-009 | Detection and response capability | No alerting or paging and no security detection layer beyond a pipeline heuristic; incidents may go unnoticed; the IR runbook is untested _(state at 2026-07-24; see Existing controls for 2026-11-07)_ | 4 | 4 | 16 High | CronJob `audit-anchor-alert` (daily, last success 2026-11-07T06:00:06Z: whole audit chain verified, verdict=ok, 26803 rows walked, delivered to OpenObserve stream `job_health`); CronJob `trace-silence-check` (hourly, last success 2026-11-07T14:43:04Z); CronJob `audit-siem-forward` (every 15 min, last success 2026-11-07T15:15:05Z, forwarded 7 records; factory-gitops `docs/audit-siem-forwarding.md`). The gap that remains: no paging destination (factory-gitops `docs/argocd-sync-honesty.md:230`); no auth-failure or egress-anomaly alert in factory-gitops origin/main (auth failures are only queryable in the `audit_chain` stream, factory-gitops `docs/audit-siem-forwarding.md:84-90`); IR runbook never exercised (`policies/incident-response.md:69,191`) | Mitigate — alerting on anchor-failure/chain-break/auth-spikes; paging; tabletop the runbook (IR owner, Wave 1); remaining gap: no open issue | Current 12 (L3 x I4) 2026-11-07; target 6 | In progress (no open issue; #313/#319 closed) |
| R-010 | Human and admin accounts | MFA not enforced at the IdP; a phished/leaked credential grants access without a second factor | 3 | 4 | 12 Medium | Keycloak SSO with GitHub upstream; org RBAC | Mitigate — enforce TOTP/WebAuthn required-action; export realm to gitops (IAM owner, Wave 2) | 4 (L1 x I4) | Open (Factory#312) |
| R-011 | Audit trail completeness | Background/WebSocket events write NULL `prev_hash` (unchained); negative events (auth/authz failures) not first-class; a gap weakens tamper-evidence and forensics _(state at 2026-07-24; see Existing controls for 2026-11-07)_ | 3 | 3 | 9 Medium | AIFactory `audit_service.py:113-169,241-258` shares the chain helpers between the request and background writers, and 0 of 29 live `audit_logs` rows have a NULL `prev_hash`; negative actions `auth.failure` (`audit_service.py:91`, `auth.py:159-162`) and `authz.denied` (`routes/project_authz.py:170-175`) exist; CronJob `audit-siem-forward` (last success 2026-11-07T15:15:05Z) | Mitigate — chain background events; enumerate negative `ACTION_*`; forward to a SIEM (audit-logging owner, Wave 2) | Current 3 (L1 x I3) 2026-11-07; target 3 | Mitigated 2026-11-07 |
| R-012 | Per-task untrusted-code Jobs | No microVM/syscall boundary and coarse `443 -> 0.0.0.0/0` egress; a sandbox escape or data-exfil path is not fully contained | 2 | 4 | 8 Medium | bwrap sandbox (#363, default-on); per-task NetworkPolicy + non-root securityContext (default-on); gVisor wired but deferred | Mitigate — per-destination egress allowlist; PodSecurity Admission on task namespaces; evaluate microVM where substrate allows (runtime owner, Wave 3) | 4 (L2 x I2) | Accepted risk AR-001 until 2027-04-24 (Factory#322) |
| R-013 | Trusted-plan signing keys | HMAC plan-signing keys have no key ID, expiry, or rotation; a leaked key cannot be cleanly rotated/revoked _(state at 2026-07-24; see Existing controls for 2026-11-07)_ | 2 | 4 | 8 Medium | AIFactory `apps/backend/trusted_plan.py:26-43` has a `kid` keyring and `AIFACTORY_TRUSTED_PLAN_RETIRED_KIDS` revocation, with no expiry; PFactory `apps/backend/plan/emit/signing.py:14-99` signs with a `kid` when a keyed variable is set. The gap that remains: the live `aifactory` and `pfactory` Deployments set only the legacy unkeyed `AIFACTORY_TRUSTED_PLAN_KEY_PFACTORY`, and there is no expiry | Mitigate — add `kid`, expiry, rotation; approved-model registry with eval gate; output DLP (agentic-AI owner, Wave 3); remaining gap: no open issue | Current 8 (L2 x I4) 2026-11-07; target 4 | Open (no open issue; Factory#323 closed) |
| R-014 | Postgres (data-postgres-0) | Postgres at rest unencrypted, accepted until a regulated tenant: PV is a plain local-path dir on p620 `/dev/sdb1` ext4, no LUKS/dm-crypt in the chain (verified 2026-10-24) | 2 | 3 | 6 Low | Physical host access control; scram-sha-256 auth; MinIO SSE-S3 on (factory-gitops#71, #310) | Accept — until a regulated tenant onboards; then LUKS-backed PV or pgcrypto (Security Owner) | 6 | Accepted (Factory#314), review 2027-04-24 |
| R-015 | Deployed fleet, agent attack surface | No independent external penetration test; unfound logic, prompt-injection or egress flaws that scanners cannot see | 2 | 4 | 8 Medium | Trivy P0 required gate (VR-0001/VR-0002 closures); CodeQL ratchet (`.github/workflows/codeql-ratchet.yml`, Factory#813); Dependabot (`.github/dependabot.yml`); gitleaks (`.github/workflows/secret-scan.yml:13`) | Accept — until a customer contract or certification audit requires a test (Security Owner); review 2027-04-24 | 8 (L2 x I4) | Accepted (Factory#317) |
| R-016 | `factory-secrets`, `minio-creds` and other long-lived secrets | Rotation is manual (agenix); a missed rotation or undetected leak leaves a stale credential valid | 3 | 3 | 9 Medium | agenix custody on p510; gitleaks required check on 5 code repos (`.github/workflows/secret-scan.yml`); factory-gitops "no literal secrets in manifests" check; rotation runbook in [encryption-key-mgmt.md](policies/encryption-key-mgmt.md) | Accept — manual rotation, 90d tokens / 365d keys / immediate on exposure (Security Owner, review 2027-04-24) | 9 (accepted) | Accepted (Factory#315) |

## Risk-acceptance log

| ID | Risk | Accepted | Review by | Decided |
|---|---|---|---|---|
| AR-001 | R-012 runtime isolation: no gVisor/microVM boundary on per-task Jobs; CIS baseline not assessed | 2026-10-24 | 2027-04-24 (six months) | Decided (lead, user-approved 2026-10-24) |

**AR-001 compensating controls (live, with evidence).**
- NetworkPolicy `factory-sandbox-jobs-egress`, selector `factory.io/kind: task`, Ingress+Egress: `factory-gitops apps/factory-namespace/manifests/networkpolicy-sandbox-jobs.yaml:100,131`. Known residual: 3-5 s unconfined window at pod start (Factory#517); egress is 443 to public, not per-destination.
- Job seccomp `RuntimeDefault`, `runAsNonRoot`: `AIFactory apps/backend/core/job_dispatch.py:633-635`. TFactory nix lanes run root with capability add-backs (runtime-isolation.md gap 3).
- Kyverno image-signature enforcement, `validationFailureAction: Enforce`: `factory-gitops apps/kyverno-policies/manifests/verify-factory-image-signatures.yaml:206`.
- bwrap sandbox (#363), default-on.

**Revisit triggers (either reopens R-012):** untrusted multi-tenant workloads arrive; or runsc supports nix builds (gVisor deferred by #274 because nix local builds fail under runsc). Microvm/Kata likewise.
**CIS baseline:** not assessed; a kube-bench run is the revisit action (due before the review date).

No residual risk above the Medium band has been formally accepted. Any acceptance (for
example, deferring HA Postgres and accepting R-007's single-instance risk for a defined
period) is recorded here with the Security Owner's sign-off, a compensating control, and
an expiry date, and is revisited at the next management review.

- **2026-10-24 — R-014, Postgres at rest unencrypted.** Decided (lead, user-approved 2026-10-24). Evidence: on p620, `lsblk -o NAME,TYPE,FSTYPE,MOUNTPOINT` shows no crypt/LUKS device; `findmnt -T /mnt/code/k3d/storage` = `/dev/sdb1` ext4 (the local-path PV dir, mounted at `/var/lib/rancher/k3s/storage` in `k3d-factory-server-0`). Accepted until a regulated tenant; compensating: host access control, scram-sha-256. Expiry/review: 2027-04-24 (six months).
### AR-002 — R-015 no external penetration test (Factory#317)

- **Decided (lead, user-approved 2026-10-24):** no external pen test until a customer contract or certification audit requires one.
- **Sign-off:** Security Owner via the lead, 2026-10-24. Residual is Medium (8), within the band that needs no extra sign-off.
- **Compensating controls:** Trivy P0 required gate; CodeQL at 0 actionable with a weekly ratchet (Factory#813); Dependabot; gitleaks. Their file evidence is in the R-015 row.
- **Expiry / review date:** 2027-04-24 (six months), or immediately when a contract or audit requires a test.
- **Not covered:** logic flaws and the agent surface (prompt injection, egress, untrusted-code Jobs) that automated scanners do not model.


| ID | Decision | Compensating control | Expiry / review |
|---|---|---|---|
| R-016 | Decided (lead, user-approved 2026-10-24): accept manual agenix rotation of `factory-secrets` and `minio-creds` (Factory#315). Plan: [plan/2026-10-24-315-risk-acceptance.md](../../plan/2026-10-24-315-risk-acceptance.md) | Runbook and cadence in [encryption-key-mgmt.md](policies/encryption-key-mgmt.md); gitleaks required check; factory-gitops `docs/secrets-management.md` inventory | Review 2027-04-24 |
