---
status: draft
issue: 324
intent: intent/2026-11-07-324-compliance-records-refresh.md
---

# Spec: refresh stale compliance records

## Evidence base (measured 2026-11-07, about 15:25 UTC, read-only)

Every changed row cites one of these items, called E1 to E12 below. Cluster
items come from `kubectl --context k3d-factory` on p620. Repo items come from
`origin/main`. Issue state comes from `gh`.

- **E1 Backups.** CronJob `postgres-backup` (`15 2 * * *`, factory-gitops
  `apps/backups/manifests/manifests.yaml`) reports `lastSuccessfulTime`
  2026-11-07T02:15:06Z. The last three Jobs are Complete. The Job log lists
  `factory-backups/postgres/factory-cluster-2026110{3..7}T0215*Z.sql.gz`.
- **E2 MinIO.** The Job `minio-create-bucket` completed 2026-10-22T21:49:16Z.
  Its log shows versioning enabled on `factory-artifacts`, `factory-backups`
  and `factory-evidence`, and three lifecycle read-backs:
  `factory-artifacts` = `log-*-30d` + `evidence-*-90d`,
  `factory-backups` = `backups-14d`, and `factory-evidence` = `evidence-90d`.
  The source is factory-gitops `apps/minio/manifests/manifests.yaml:335-361`,
  where an import is read back and the Job fails if a rule's ID is missing.
  The declared rules are `backups-14d`, which expires current versions after 14
  days and noncurrent versions after 7, and `evidence-90d`, which expires after
  90 days with noncurrent after 30. The read-back asserts only rule IDs, so the
  day counts are as declared, not as read back. The manifest comment on
  `evidence-90d` says that "SOC2's 12-month observation window wants Days 365".
  No ILM rule has a 13-month expiry.
- **E3 Single instance.** The `postgres` StatefulSet and the `minio` Deployment
  each have `replicas: 1`.
- **E4 Restore drill.** The drill of 2026-08-10 is recorded in `dr-runbook.md`
  (commit 03c87f8 of 2026-08-10, #662). It restored 52 of 52 tables with a
  data-restore step of 17s and an RPO of up to 24h. It is a dated record that
  cannot be measured again, and it does not measure full-path RTO.
- **E5 CFactory supply chain.** `image-build.yml:164,199,233` runs Trivy as a
  HIGH/CRITICAL gate. `deploy.yml:242-243` runs `cosign sign` by digest, and
  `deploy.yml:139-151,266` attests a dual SBOM. Deploy runs on `main` succeeded
  from 2026-10-24 to 2026-10-30.
- **E6 Kyverno.** ClusterPolicy `verify-factory-image-signatures` is
  `Enforce`, `failurePolicy: Ignore`, and Ready. Rule
  `verify-cfactory-signature` covers `cfactory` and `cfactory-frontend`, with
  subject regexp
  `^https://github\.com/olafkfreund/CFactory/\.github/workflows/deploy\.yml@refs/heads/main$`.
  The running image `cfactory:sha-b24d6f4` passes `cosign verify`.
  Factory#3665 (fail closed for gateway, fides and fides-reporter) is OPEN.
  Factory#522 is CLOSED. CFactory#191, a PR, is MERGED.
- **E7 Alerting.** `audit-anchor-alert` runs daily; its last success was
  2026-11-07T06:00:06Z, with log "whole audit chain verified, verdict=ok, 26803
  rows walked … delivered status=ok to OpenObserve stream 'job_health'".
  `trace-silence-check` runs hourly; its last success was 2026-11-07T14:43:04Z.
  The anchor-alert README says there is no Alertmanager and no webhook.
  factory-gitops `docs/argocd-sync-honesty.md:230` says "No paging
  destination." Factory `docs/compliance/policies/incident-response.md:69,191`
  says there has been no tabletop and the runbook was never exercised.
- **E8 SIEM forward.** `audit-siem-forward` runs every 15 min; its last success
  was 2026-11-07T15:15:05Z, with log "forwarded 7 record(s)". It is documented
  in factory-gitops `docs/audit-siem-forwarding.md`.
- **E9 Audit chain.** AIFactory `apps/web-server/server/services/audit_service.py:113-169,241-258`
  shares the chain helpers between the request and background writers.
  `ACTION_AUTH_FAILURE` is at `audit_service.py:91` and `auth.py:159-162`;
  `ACTION_AUTHZ_DENIED` is at `routes/project_authz.py:170-175`. In the live
  `aifactory` DB, 0 of 29 `audit_logs` rows have a NULL `prev_hash`.
- **E10 Plan keys.** AIFactory `apps/backend/trusted_plan.py:26-43` has a
  `kid` keyring and `AIFACTORY_TRUSTED_PLAN_RETIRED_KIDS` revocation, with no
  expiry. PFactory `apps/backend/plan/emit/signing.py:14-99` signs with a
  `kid` when a keyed variable is set. The live `aifactory` and `pfactory`
  Deployments set only the legacy, unkeyed `AIFACTORY_TRUSTED_PLAN_KEY_PFACTORY`.
- **E11 Issues.** Factory #313, #317, #318, #319, #321 and #323 are CLOSED.
  #3681 (off-cluster copy of the postgres backups) is OPEN. These open-issue
  searches (`gh search issues --state open`) found no matching issue; the only
  hit was a substring match on epic #310:
  - "paging", "tabletop" and "HA postgres" in Factory, factory-gitops,
    AIFactory and PFactory;
  - "trusted plan key", "plan signing" and "kid" in Factory, AIFactory and
    PFactory;
  - "minio backup", "re-drill restore drill" and "evidence retention" in
    Factory and factory-gitops.
- **E12 Logs freshness.** `evidence-collector` last succeeded
  2026-11-07T03:00:07Z.

## Design

### Scoring convention (risk-register.md)

L, I and Inherent stay as the 2026-07-24 assessment recorded them. The
Residual column of a re-measured row becomes `Current N (Lx x Iy) 2026-11-07;
target M`. That keeps the register's rule that a residual is not the current
score until its treatment lands. Add one Methodology bullet:

> **Mitigated** means the whole treatment has landed and been measured, so the
> Residual score is the current score. A partly landed treatment is re-scored
> as "Current" with its date and stays In progress or Open.

The "Scores below…" paragraph gains one sentence. It names the re-measured
rows (R-001, R-006, R-007, R-008, R-009, R-011, R-013), the date 2026-11-07,
and this spec.

### Register rows

| Row | Existing controls (new evidence) | Current | Status |
|---|---|---|---|
| R-001 | E1 nightly dump; E2 versioning and `backups-14d`; E4 drill. The gap that remains: the dumps share the host and volume class with Postgres and with the evidence store (dr-runbook.md "single-failure-domain"); MinIO itself is not backed up | 10 (L2 x I5) Medium; target 5 | In progress (Factory#3681 off-cluster copy; MinIO backup and scheduled re-drill: no open issue) |
| R-006 | E2 ILM: evidence 90d and logs 30d, with each rule ID enforced by read-back. The gap that remains: the treatment's 13-month floor is in no ILM rule, and the `factory-evidence` 90-day expiry is shorter than the 12-month SOC 2 window that its own manifest comment names | 6 (L2 x I3) Low; target 3 | In progress (no open issue) |
| R-007 | Text only: add "versioning on all three buckets (E2), no replication" and keep E3 single instance | unchanged | Open (no open issue; Factory#321 closed) |
| R-008 | E5 CFactory Trivy, cosign and dual SBOM; E6 Kyverno `Enforce` with a CFactory rule, running image verifies. The gap that remains: `failurePolicy: Ignore` fails open when Kyverno is unavailable, and some first-party images are not yet fail-closed | 8 (L2 x I4) Medium; target 4 | In progress (Factory#3665) |
| R-009 | E7 audit-chain integrity alert to OpenObserve `job_health`, trace-silence check; E8 SIEM forward. The gap that remains: no paging destination, no alert rule on auth-failure or egress anomalies, IR runbook never exercised | 12 (L3 x I4) Medium; target 6 | In progress (no open issue; #313/#319 closed) |
| R-011 | E9 background writer chained, 0 NULL `prev_hash` live; negative actions `auth.failure`, `authz.denied`; E8 SIEM forward | 3 (L1 x I3) Low | Mitigated 2026-11-07 |
| R-013 | E10 `kid` keyring and retired-kid revocation in code. The gap that remains: the live deployment uses the legacy unkeyed key, and there is no expiry | 8 (L2 x I4) Medium, unchanged | Open (no open issue; Factory#323 closed) |

In each re-measured row, the Threat / vulnerability text keeps the threat as it
was assessed, because L, I and Inherent score it. The text gains the suffix
"_(state at 2026-07-24; see Existing controls for 2026-11-07)_". It is not
rewritten, so the threat and the inherent score still match.

Rows R-002 to R-005, R-010, R-012 and R-014 to R-016 are not touched.

### SoA (statement-of-applicability.md)

| Control | Old | New | Justification |
|---|---|---|---|
| A.5.29 | Planned | Partial | BC policy; DR runbook; E1 nightly backups operate. Partial: everything sits in one failure domain (Factory#3681) |
| A.5.30 | Planned | Partial | E4 measured data-restore RTO 17s and RPO up to 24h; DR runbook. Partial: full-path RTO not measured, no scheduled re-drill (no open issue), off-cluster copy missing (Factory#3681) |
| A.8.13 | Planned | Partial | E1 nightly `pg_dumpall`, E2 versioning and 14-day retention. Partial: no off-cluster copy (Factory#3681); the MinIO object store itself is not backed up |
| A.8.14 | Planned | Planned | Text: E3; "Factory#321 closed; no open issue" |
| A.8.15 | Implemented | Implemented | Drop "Partial: background events unchained (R-011)"; cite E9 |
| A.8.16 | Planned | Partial | E7 and E8 operate. Partial: no paging destination, no auth-failure or egress alert rules (R-009, no open issue) |
| A.8.8 | Partial | Partial | Replace "CFactory unscanned (Factory#317)" with the E5 CFactory Trivy gate. The other qualifiers are untouched |
| A.5.33, A.8.10 | Implemented | Implemented | Replace "note evidence ILM bug / ILM misconfig (R-006)" with "E2: ILM keeps evidence 90 days; no 13-month ILM floor (R-006)" |
| Note at line 98 | — | — | Replace "(and the Kyverno admission rules, which have the same looseness and no `cfactory` rule at all) is Factory#522" with the E6 exact-subject rule; Factory#522 closed. The pipeline's own regexp claim is not re-measured and stays as written |

The header gains "Rows A.5.29, A.5.30, A.5.33, A.8.8, A.8.10, A.8.13 to A.8.16
re-measured 2026-11-07". Summary: A.5 is 25/3/8/1, A.8 is 25/5/3/1, and the
total is **54 Implemented / 8 Partial / 14 Planned / 17 Not Applicable**,
which still sums to 93.

### SOC 2 gap assessment (soc2-gap-assessment.md), re-derived by its own rules

| Row | Relied-on SoA (new) | Old | New | Reason |
|---|---|---|---|---|
| A1.3 | A.5.30 Partial | Gap | **Partial** | The ceiling is now Partial, and the E4 drill is an operating output. It is not Met: there is no recurring drill and no off-cluster copy |
| CC7.5 | A.5.26 I, A.5.29 P, A.5.30 P | Gap | **Partial** | The ceiling is Partial. Recovery from data loss is proven only on-host (E4), and the IR runbook is untested (R-009) |
| CC9.1 | A.5.29 P, A.5.30 P, A.8.13 P, A.8.14 Planned | Gap | Gap | A.8.14 is still Planned, so the ceiling is Planned. Only the text is updated |
| A1.2 | same four | Gap | Gap | Same ceiling. The text drops "SoA records no backups" and the "does not yet reflect" note |
| CC7.2 | A.8.15 I, A.8.16 P | Gap | **Partial** | The ceiling is Partial. The E7 alert produces an operating output in `job_health`. Gaps: no paging, no auth-failure or egress detection |
| CC7.3 | A.5.25 I, A.8.16 P | Gap | Gap | The ceiling allows Partial, but there is no record that any event was ever triaged and the runbook was never exercised (E7). This follows the CC1.2 precedent (defined, no record = Gap) and rule 5 (round down). Only the text is updated |

Text-only corrections in rows that cite refreshed risks or SoA rows:

- CC2.1: drop "Background events unchained" and "no SIEM forward" (E8, E9), and
  keep "no unified fleet audit stream".
- CC6.5 and C1.2: replace "ILM expires evidence at 30 days against a 90-day
  claim" with "ILM keeps evidence 90 days (E2); no 13-month floor, and shorter
  than a 12-month SOC 2 window".
- CC6.8, CC7.1, CC9.2: R-008 now reads current 8 Medium, without "register
  text outdated".
- CC7.4: R-009 now reads current 12.
- CC6.5 and C1.2 risk columns: R-006 now reads current 6 Low.

Risk column format for re-measured risks: `R-001 (15 High; current 10 Medium,
2026-11-07)`. Mitigated risks read `R-011 (9 Medium; mitigated, current 3 Low,
2026-11-07)`. R-011 is the only risk Mitigated by this refresh.

Document-level text:

- **Scope.** The risk-score sentence names the 2026-11-07 re-measure.
- **Status legend.** The paragraph "Where a register row is outdated … not
  edited. For example R-008 …" is replaced by a statement that the register was
  refreshed on 2026-11-07 and that both scores are shown.
- **Evidence pointers.** The paragraph lists the refreshed SoA rows.
- **Summary.** Security is 0 / 24 / 9, Availability 0 / 2 / 1, Confidentiality
  unchanged, and the total is **0 Met / 27 Partial / 11 Gap**, which still sums
  to 38.
- **High-risk list.** The list keeps the inherent ≥15 risks. R-001 and R-009
  gain "(current 10 Medium / 12 Medium, 2026-11-07)".
- **ISO summary.** It reads 54/8/14/17. The Partial list has 8 entries: A.5.21,
  A.5.29, A.5.30, A.8.8, A.8.13, A.8.16, A.8.21, A.8.23. In the Planned table,
  the `#313` row is removed and `#321` lists A.8.14 only, for 14 in total.
- **Sign-off paragraph.** "Before signing, refresh…" is replaced by a paragraph
  saying the rows were refreshed on 2026-11-07 (linking this spec). Off-cluster
  backup stays open under Factory#3681.

### dr-runbook.md

- "Retention is whatever MinIO's lifecycle policy allows" now reads: the
  declared `backups-14d` lifecycle rule expires dumps after 14 days and
  noncurrent versions after 7 (E2, as declared; the read-back checks the rule
  ID).
- References to #321 as the live tracker are updated, because #321 is CLOSED
  (E11):
  - line 39, full-path RTO: "outstanding (#321 closed; no open issue)";
  - line 63, off-box destination: "Tracked on Factory#3681";
  - line 170: the heading becomes "Outstanding (Factory#321 closed 2026-08-10)".
- In the Outstanding list, "Off-box backup destination" gains "(Factory#3681)".
  "MinIO versioning + backup" is split: versioning is done (E2, ticked), and
  MinIO backup stays unticked with no open issue.

### control-matrix.md

The matrix carries a status per domain, and three of its rows contradict the
evidence. Its legend uses Strong, Partial and Gap.

- Line 35, Business continuity / DR: **Gap → Partial**. E1 and E4 show a real
  control that operates. It is Partial, not Strong: on-host only, MinIO is not
  backed up, and there is no HA.
- Line 58, BC/DR evidence row:
  - Implementing control: nightly `pg_dumpall` (E1); MinIO versioning (E2);
    restore drill 2026-08-10 (E4).
  - Top gap: a single failure domain, with no off-cluster copy (Factory#3681);
    MinIO is not backed up; single instance (E3).
  - Issue: #321, #3681.
- Line 50, Audit logging top gap: "Background/WS events unchained; no SIEM
  forward; no security alerting" becomes "no paging; no alert rules for
  auth-failure or egress anomalies" (E7, E8, E9). The status (line 27,
  Partial) is unchanged.
- Line 56, Incident response top gap: "No IR runbook wired to alerting;
  untested; no paging" becomes "Runbook untested (no tabletop); no paging; an
  audit-chain alert exists (E7)". The status (line 33, Gap) is unchanged:
  nothing new shows the IR process operating.
- Vuln row, line 54: "CFactory even-coverage in flight (CFactory#191)" becomes
  "CFactory Trivy gate live (E5, CFactory#191 merged)".

## Alternatives rejected

- **Re-scoring L and I in place.** This would overwrite the inherent score and
  break the register's own rule that a residual is current only once its
  treatment lands. It would also break the gap assessment's "register's
  recorded scores" link.
- **Closing R-001, R-008 and R-009.** Their treatments have only partly landed
  (backups on-host, fail-open admission, no paging).
- **Moving A.8.14 to CC9.1's Gap column to lift CC9.1 to Partial.** That
  reclassifies a control the row relied on, only to raise a rating. Round down.
- **Lifting CC7.3 to Partial.** There is no evaluation record, and the CC1.2
  precedent applies.
- **Refreshing every stale row in the SoA and the matrix.** That is out of
  scope. Only rows that the evidence base above contradicts are refreshed.
- **Marking R-006 Mitigated.** Its treatment names a 13-month floor that no
  ILM rule carries. Round down.

## Risks

- Point-in-time evidence: a CronJob can fail tomorrow. Each cite carries its
  date. No host changes.
- Count drift between the row tables and the summaries. The verification
  recounts them mechanically.
- Over-crediting: A1.3, CC7.5 and CC7.2 rise to Partial. Each rests on an
  operating output (a drill record, the Job logs), not on configuration alone.

## Verification

- Recount the SoA statuses per theme from the table rows with a grep/awk count,
  and compare the result to the summary table and to the ISO summary in the gap
  assessment.
- Recount the gap assessment's Met/Partial/Gap per category from the rows, and
  compare the result to the Summary table.
- For each refreshed SOC row, check by hand that its status is no better than
  its worst relied-on SoA row.
- `grep -n 'register text outdated\|not yet updated\|does not yet reflect\|Before signing, refresh'`
  must return nothing.
- Every R-00x score cited in the gap assessment must match the register.
- control-matrix.md lines 35, 50, 54, 56 and 58 match the spec.
- Markdown tables must keep their column counts: every row has the same number
  of `|` as its header.
