---
status: draft
issue: 314
author: olafkfreund
---

# Intent: Key-rotation policy page and in-cluster age reporting

## Problem

Verified against current main (2026-11-16): a rotation policy, a per-credential ledger and a weekly
ledger check already exist in factory-gitops (`docs/secrets-management.md`, `scripts/rotation-ledger-check.py`,
`.github/workflows/secret-rotation-due.yml`), and `docs/compliance/policies/encryption-key-mgmt.md` has a
manual runbook (R-016). What is still missing for #314 item 3:

1. Nothing in the cluster shows how old each live Secret's current value is. The ledger is a document;
   it can drift from reality and says nothing about the running Secrets.
2. An overdue credential only turns a weekly workflow red. There is no `job_health` record and no issue.
3. The compliance side has no single page an assessor reads: interval, owner and procedure per class,
   plus how the owner records a rotation. The two docs also disagree: the runbook says 90 days for API
   tokens, the gitops policy says 365 days.

## Proposed outcome

- `docs/compliance/policies/key-rotation.md`: interval, owner and procedure link per secret class, the
  stamping procedure, and the reconciliation of the 90/365 conflict (open question below).
- A CronJob in factory-gitops that reads only the metadata annotation `rotation.factory.dev/rotated-at`
  of each listed Secret in `factory`, reports age vs policy to `job_health`, and opens one GitHub issue
  per overdue Secret (cred-broker pattern). It rotates nothing.
- The owner stamps the annotation after a rotation, in the same window as the ledger row.

## Affected users and systems

Owner (rotates by hand, stamps); namespace `factory` Secrets (metadata only); OpenObserve `job_health`;
Factory issue tracker; factory-gitops and Factory docs.

## Constraints

- Never reads, logs or transmits a Secret value: the job asks the API for `PartialObjectMetadata`, so
  values never reach the process.
- No new credential: `observe-root` and the optional `factory-secrets/GITHUB_TOKEN`, as cred-broker does.
- Annotation is per Secret, the ledger is per credential: the stamp is the rotation date of the OLDEST
  credential in that Secret, so one rotated key cannot hide an overdue sibling. Acknowledging an alert
  never resets age; only an evidenced rotation, recorded in the ledger, does.
- An unstamped Secret is measured from the policy start date (2026-11-07), exactly as the ledger does
  for `unknown` rows, so it cannot be cleared by stamping without a rotation date.
- Assurance limit: the date is operator-reported. It does not detect a value that changed without a stamp,
  or ledger drift; it makes missing and stale stamps visible and alerting.
- Out of scope: automated rotation, KMS, encryption at rest, `minio-kms` and `CFACTORY_AUDIT_HMAC_SECRET`
  (compromise-only). `factory-cli-creds` is included for its codex/copilot/gemini keys; the Claude key in it
  is the cred-broker's and has its own expiry alert.
- Another wave is merging into the same repos: keep diffs tight, rebase before push.

## Open questions

Which interval governs API tokens, 90 days (Factory runbook, accepted 2026-10-24) or 365 days (gitops
policy and ledger)? This work applies the stricter accepted control: 90 days for `factory-secrets` (it holds
the API tokens and the oldest credential decides), 365 days for the other Secrets. The gitops ledger rows for
tokens still say 365; aligning them is a follow-up for the owner, noted on the policy page.
