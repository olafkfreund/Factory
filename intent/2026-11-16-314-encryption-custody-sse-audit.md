---
status: approved
issue: 314
author: olafkfreund
---

# Intent: encryption at rest, finish the agent-doable slice of Factory#314

## Problem

Factory#314 still has three unchecked items. Current evidence (comment of 2026-11-14, repo state 2026-11-16):

- Encrypt at rest: MinIO SSE-S3 is on for new writes; objects written before it are not evidenced as encrypted. Postgres/disk is unencrypted (risk R-014 accepted). LUKS steps exist but name p510 while the storage is on p620.
- SOPS/agenix decryption-key custody with rotation: the custody section lists loss and compromise cases but gives no copy-paste re-key or identity-rotation commands, no custody register and no way to check an offline backup.
- KES vs the built-in static KMS key: one sentence, no decision record.
- `docs/compliance/policies/encryption-key-mgmt.md` still says "no data-at-rest encryption", "no rotation", "no KMS". Auditors read it; it contradicts the cluster.

## Proposed outcome

- A read-only script that audits `mc stat --versions --recursive --json` output and says which existing objects are not SSE-S3, so the owner's check 3 is one command.
- Custody section with exact identity-rotation and offline-backup-check steps, plus a custody register.
- A KES-vs-static-key decision record (no KES deployed; reasons and trigger to revisit).
- LUKS runbook corrected to the real host with exact commands, still owner-run.
- The compliance policy states current reality with dated evidence links.
- One epic comment ticking what is done, listing owner actions.

## Affected users and systems

Factory (docs, artifacts), factory-gitops (docs, scripts, one workflow path list). No cluster, secret or manifest change.

## Constraints

No live cluster change, no secret read, no KES or MinIO config change (the drill is untested, rotation is owner-gated). Script is read-only on its input and has no network or subprocess use. No acceptance box on #314 is ticked as done unless evidence exists.

## Open questions

None. KES deployment, LUKS, etcd encryption and FIPS stay with the owner.
