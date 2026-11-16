---
status: draft
issue: 314
intent: intent/2026-11-16-314-key-rotation-policy.md
---

# Spec: Key-rotation policy page and in-cluster age reporting

## Design

**Factory** (`docs/compliance/policies/key-rotation.md`, linked from `docs/compliance/README.md`): a
short policy page. Table of classes with max age, owner (platform operator, four-eyes reviewer as in the
R-016 runbook), and a link to the procedure (gitops `docs/secrets-management.md` runbook and
per-secret rows). It states: the ledger in gitops is the per-credential record; the Secret annotation is
the in-cluster cross-check; the stamp procedure; the assurance limit; the 90/365 conflict and the choice made.

**factory-gitops** (new app `apps/secret-rotation/`, auto-discovered by the app-of-apps):

- `report.py` (stdlib), CronJob daily 06:00 UTC, `concurrencyPolicy: Forbid`, `restartPolicy: Never`
  (Factory#438), no retries beyond one.
- A ServiceAccount with a Role granting `get` on exactly the listed Secret names. The job requests each
  Secret with `Accept: application/json;as=PartialObjectMetadata;g=meta.k8s.io;v=v1`, so the API returns
  metadata only; values never enter the process. It reads the annotation `rotation.factory.dev/rotated-at`
  (`YYYY-MM-DD`).
- Policy table in `report.py`: `factory-secrets` 90d; `minio-creds`, `factory-db-{aifactory,pfactory,tfactory}`,
  `cfactory-api-keys`, `oauth2-proxy-{cfactory,observe,odin}`, `observe-root`, `odin-ssh-key`,
  `otel-otlp-auth`, `factory-cli-creds` 365d. `minio-kms` and the audit HMAC are compromise-only and not listed.
- Per Secret, status: `ok`; `due_soon` (within 30 days of the deadline); `overdue`; `unstamped` (annotation
  missing or invalid: age measured from 2026-11-07, the policy start, like the ledger; overdue once past
  the interval); `missing` (404, Secret absent). A 403 or any other API error is not a status: the run reports what it has, then exits 1, so broken RBAC cannot pass as a clean daily run.
- Emits one record per Secret to OpenObserve `job_health` (`source: secret-rotation`, `kind: secret_rotation`,
  name, age, max age, status) using the `observe-root` credential and the `/_json` path of
  `apps/backups/drill/emit.py`.
- Opens one GitHub issue per overdue/unstamped-overdue Secret on `olafkfreund/Factory` (label
  `secret-rotation`, body marker `<!-- secret-rotation:<name> -->`, dedupe against open issues, inert
  without `GITHUB_TOKEN`), reusing cred-broker's `alert` shape. The body names the Secret, age, max age and
  the runbook link; never a value.
- Exit 0 when the report was delivered (an overdue Secret is a finding, reported by the issue, not a job
  failure, so job-watchdog does not duplicate it); exit 1 when `job_health` delivery or the API fails.
- CI: `test_report.py` runs the decision logic and the exit codes against a local stub; a workflow runs it.

The stamp (owner, after rotation, same window as the ledger row):
`kubectl -n factory annotate secret <name> --overwrite rotation.factory.dev/rotated-at=$(date -u +%F)`.
The stamp is the oldest evidenced last-rotated date among ALL credentials still in the Secret (read it from
the ledger rows), not necessarily today: rotating the oldest key leaves the next-oldest as the new stamp. After
a recreate, restore that date, not today.
`kubectl annotate` merges metadata and does not touch `.data`; if the bootstrap recreates the Secret, the
step must re-stamp, so the manage-secrets / bootstrap flow documents the stamp as its last step.

## Alternatives rejected

- Read ledger from the doc inside the cluster: the ledger already has a weekly check; it cannot show live state.
- Automatic rotation: out of scope and the accepted control is manual (R-016).
- Annotation per key (`rotated-at.<KEY>`): precise but 20+ annotations on `factory-secrets`, more to stamp wrongly.
- Fail the CronJob when overdue: job-watchdog would open a second issue for the same fault.
- Reuse the job-watchdog script: it is a 1300-line embedded script; a small separate job keeps blast radius low.

## Risks

- First run: all 13 Secrets are `unstamped`; none overdue until 2027-02-05 (90d) / 2027-11-07 (365d). No flood.
- RBAC `get` on a Secret can read its values; mitigated by the metadata Accept header and a script that never
  requests the full object. A change to the script could regress that; the test asserts the header.
- Issue creation uses the shared `GITHUB_TOKEN`; absent token means inert, not failure.
- Rebase conflict with the concurrent wave: the app is a new directory, so conflicts are unlikely.

## Verification

`python3 apps/secret-rotation/manifests/test_report.py` (statuses, boundary days, dedupe, header, exit codes);
`kustomize build apps/secret-rotation/manifests`; repo CI (manifest validation, new workflow); Factory docs
link check. No kubectl writes to the live cluster.
