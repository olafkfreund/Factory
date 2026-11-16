---
status: draft
issue: 314
author: olafkfreund
---

# Intent: Key-rotation policy and age reporting for long-lived secrets

## Problem

Only the Claude OAuth credential rotates (cred-broker). `JWT_SECRET`, `APP_API_TOKEN`,
database credentials, MinIO keys, `acw_`/CFactory API keys and signing keys have no
documented interval, owner or procedure, and nothing shows how old any of them is.
Epic #314 item 3 ("Key-rotation policy + automation") is open, and an assessor
(ISO A.8.24, SOC 2 CC6.1, PCI 3.7/8.3, NIST IA-5) cannot confirm a rotation cadence.

## Proposed outcome

- A rotation policy in `docs/compliance/policies/` with an interval, owner and procedure link per secret class.
- A CronJob in factory-gitops that reads one metadata annotation (`rotated-at`) per listed Secret in
  namespace `factory`, reports age against the policy to the `job_health` stream, and opens one GitHub
  issue per overdue secret (cred-broker pattern, Factory#3687 / gitops#340).
- The owner stamps the annotation after each rotation; the procedure is documented.

## Affected users and systems

Owner (stamps annotations, rotates by hand); namespace `factory` Secrets (metadata read only);
OpenObserve `job_health`; the Factory issue tracker.

## Constraints

- The automation never rotates anything and never reads or logs a Secret value (RBAC `get` on named Secrets
  returns data, so the job reads only `metadata` and prints names, ages and counts).
- No new credential: reuses `observe-root` and the optional `GITHUB_TOKEN` as cred-broker does.
- Another wave is merging into the same repos: keep diffs tight, rebase before pushing.
- Out of scope: automated rotation itself, KMS, encryption at rest (other #314 items).

## Open questions

None. An unstamped Secret is reported as "unknown age" and treated as overdue, so the first run
raises issues until the owner stamps the current rotation date.
