---
status: draft
issue: 314
intent: intent/2026-10-24-314-risk-acceptance.md
---

# Spec: Postgres at-rest risk acceptance

## Design
Evidence (p620, 2026-10-24): lsblk shows no crypt/LUKS device in any chain; /dev/mapper holds only "control"; the PV path /mnt/code/k3d/storage (bind-mounted at /var/lib/rancher/k3s/storage in k3d-factory-server-0) is on /dev/sdb1 ext4 (plain). Add R-014 "Postgres at rest unencrypted, accepted until a regulated tenant", mark matrix row Partial, add acceptance-log entry, annotate policy.
## Alternatives rejected
LUKS migration now: needs downtime and key custody design; out of scope for the clean-slate push. pgcrypto: app change.
## Risks
Disk theft or snapshot exposes Postgres data; compensating: physical host access control, no regulated tenant.
## Verification
Docs diff review; #314 stays open with comment.
