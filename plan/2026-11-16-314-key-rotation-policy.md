---
status: approved
issue: 314
spec: spec/2026-11-16-314-key-rotation-policy.md
coders:
  1: lead   # small tricky logic, written by the lead (codex reviews the diff); no handoff, 4 steps in 2 repos
  2: lead
  3: lead
  4: lead
reviewers:
  - codex   # final `codex review --base` on each repo
---

# Plan: Key-rotation policy page and in-cluster age reporting

Approved decisions (from the spec): a daily CronJob `secret-rotation-report` in factory-gitops reads the
annotation `rotation.factory.dev/rotated-at` (YYYY-MM-DD) of 13 named Secrets in `factory` via
`PartialObjectMetadata` GETs (never values), classifies each (`ok`, `due_soon` within 30d, `overdue`,
`unstamped` measured from 2026-11-07, `missing` on 404), emits one `job_health` record per Secret
(`observe-root`, `/_json`), opens one issue per overdue Secret on `olafkfreund/Factory` (label
`secret-rotation`, marker `<!-- secret-rotation:<name> -->`, deduped, inert without `GITHUB_TOKEN`), exits 1 on
403/API error or delivery failure, else 0. Max age: `factory-secrets` 90d; `minio-creds`,
`factory-db-{aifactory,pfactory,tfactory}`, `cfactory-api-keys`, `oauth2-proxy-{cfactory,observe,odin}`,
`observe-root`, `odin-ssh-key`, `otel-otlp-auth`, `factory-cli-creds` 365d. The stamp is the oldest evidenced
last-rotated date among all credentials in the Secret. Nothing rotates.

Rebase on the current base before step 1 and again before each push.

## Steps

1. factory-gitops `apps/secret-rotation/manifests/report.py` and `test_report.py` (new): classification,
   metadata GET with the PartialObjectMetadata Accept header, job_health emit, issue dedupe, exit codes →
   verify `python3 apps/secret-rotation/manifests/test_report.py` passes. Includes: a 200 then a 403 emits the collected records, then exits 1.
   Traps: stdlib only; never print a value; `from a import b` plain names for ruff.
2. factory-gitops `apps/secret-rotation/manifests/{manifests.yaml,kustomization.yaml}` and
   `apps/secret-rotation/application.yaml` (new): ServiceAccount, Role (`get` on the 13 names) and RoleBinding,
   CronJob `0 6 * * *`, `concurrencyPolicy: Forbid`, `backoffLimit: 0`, pinned python image digest as cred-broker, ConfigMap via configMapGenerator
   (`disableNameSuffixHash`), securityContext like cred-broker → verify `kustomize build apps/secret-rotation/manifests`.
   Traps: `restartPolicy: Never`, no `ttlSecondsAfterFinished`, `GITHUB_TOKEN` optional.
3. factory-gitops `.github/workflows/secret-rotation-test.yml` (new, no paths filter, pinned action SHAs copied
   from cred-broker-test.yml) and `docs/secrets-management.md`: add the stamp as the last step of the "Rotation runbook" (the agenix / `manage-secrets.sh edit` then bootstrap
   or `kubectl patch` flow, also after a Secret is recreated) using the oldest evidenced date from the ledger rows, not today and a "Rotation age report" subsection under Rotation policy → verify the workflow command locally.
   Traps: do not edit the ledger markers (checker is strict).
4. Factory `docs/compliance/policies/key-rotation.md` (new) plus a row in `docs/compliance/README.md`:
   classes, max age, owner, procedure links, stamp procedure, assurance limit, 90/365 note → verify links
   resolve (`rg` for the targets) and README row renders.

## Deviations

- Step 3/4: the stamp rule excludes compromise-only credentials (`CFACTORY_AUDIT_HMAC_SECRET`, in `factory-secrets`), found by the Codex review; otherwise that Secret could never clear after 90 days.

## Tests

- `python3 apps/secret-rotation/manifests/test_report.py` → OK.
- `kustomize build apps/secret-rotation/manifests` → renders the Role, CronJob and ConfigMap with report.py.
- `python3 scripts/rotation-ledger-check.py --validate-only docs/secrets-management.md` → still valid.
- PR checks green on the exact head SHA.

## Rollback

Delete `apps/secret-rotation/` (ArgoCD prunes the CronJob, Role and ConfigMap); revert the doc commits. The
annotation on Secrets is inert metadata and can stay. Close any `secret-rotation` issues by hand.
