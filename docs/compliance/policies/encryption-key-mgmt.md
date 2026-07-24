# Encryption at Rest and Key Management

- **Domain:** Encryption at rest & key management (Factory#314)
- **Frameworks addressed:** ISO/IEC 27001 A.8.24 (use of cryptography); SOC 2 CC6.1 (logical access / data protection); PCI DSS Req. 3 (stored data) and Req. 4 (data in transit); NYDFS 23 NYCRR 500.15 (encryption of nonpublic information); FedRAMP SC-12 / SC-13 / SC-28 (cryptographic key establishment and management, cryptographic protection, protection of information at rest) with FIPS 140 validation.
- **Parent epic:** Factory#310 (audit-readiness), top gap #3.
- **Status:** Draft. Encryption-at-rest controls are NOT yet implemented; this document states the honest current posture and the remediation plan.

## Purpose

Define how the Factory fleet protects data using cryptography: what is encrypted in transit, what is (and is not) encrypted at rest, and how cryptographic keys and secrets are generated, stored, custodied, and rotated. Scope covers the two durable data stores that hold job state and evidence — Postgres and MinIO — plus Redis, Kubernetes Secrets, and the application-level keys (`JWT_SECRET`, `acw_` API keys, database credentials, signing keys, provider tokens). The controlling assertion an assessor tests is: sensitive data is encrypted at rest with evidence, and the keys protecting it are managed under a documented lifecycle.

## Current state (grounded)

### In transit (partial — external only)

- Public ingress for every service (`*.freundcloud.org.uk`) is fronted by a Cloudflare Tunnel connector; TLS terminates at Cloudflare's edge. See `factory-gitops/infra/cloudflared/cloudflared.yaml` — the tunnel ingress maps each hostname to an in-cluster Service.
- Origin traffic from the connector to Services is plain HTTP over the cluster network (`service: http://…svc.cluster.local:PORT` in the same file). There is no in-cluster mTLS / service mesh.
- Postgres uses `POSTGRES_HOST_AUTH_METHOD=scram-sha-256` for password auth (`factory-gitops/apps/postgres/manifests/manifests.yaml`) but the 5432 wire itself is not TLS-wrapped; app-to-DB and app-to-MinIO traffic is cleartext on the pod network.

### Secrets at rest (Kubernetes Secrets — base64, not encrypted)

- SOPS is referenced only as a generic secret-source *option* in `Factory/docs/dev/secrets-and-tokens.md` ("…from your secret source (agenix / SOPS / sealed-secrets)…"). There is no `.sops.yaml`, no `age` recipient, and no SOPS-encrypted file committed anywhere in the fleet or in `factory-gitops`. The epic's "SOPS-encrypted secrets in git" describes intent, not the deployed reality.
- Sensitive values are created out-of-band with `kubectl create secret` and are NOT committed to git. See the header comments in `factory-gitops/apps/postgres/manifests/manifests.yaml` (`factory-secrets/POSTGRES_PASSWORD`) and `factory-gitops/apps/minio/manifests/manifests.yaml` (`minio-creds`). This keeps plaintext out of the repo but means the secrets live as base64 (not encrypted) in the cluster.
- No sealed-secrets controller, no External Secrets Operator, and no Vault are deployed (`factory-gitops/apps/` contains none; the only matches for those terms are comments saying "no sealed-secrets / ESO yet"). Kubernetes Secrets therefore sit in etcd, and the k3s default has no `EncryptionConfiguration` (none exists in `factory-gitops/bootstrap/`), so Secrets are effectively plaintext-at-rest in etcd on disk.

### Data at rest (none)

- Postgres — the durable control-plane state store (job_states and per-service tables, RFC-0016) — is a single-replica StatefulSet on an RWO `local-path` PVC (`factory-gitops/apps/postgres/manifests/manifests.yaml`). The k3s `local-path` provisioner writes to a plain host directory on the node's filesystem. No LUKS/dm-crypt, no encrypted StorageClass, no `pgcrypto` / column encryption, no TDE.
- MinIO — the object store for PARR artifacts and evidence — runs with `args: ["server", "/data", …]` on an RWO `local-path` PVC (`factory-gitops/apps/minio/manifests/manifests.yaml`). It is started with no server-side encryption (SSE-S3 / SSE-KMS) and no `MINIO_KMS_*` configuration. Objects, including audit evidence, are stored unencrypted on the host disk.
- Redis (`factory-gitops/apps/redis/manifests/manifests.yaml`) and Keycloak (`factory-gitops/infra/keycloak/keycloak.yaml`) are likewise on `local-path` with no at-rest encryption.
- Net: no data-at-rest encryption exists on any store. This is the state the epic flags as gap #3.

### Key management posture

- The only automated rotation in the fleet is the credential broker for the Claude OAuth token, which refreshes and rolls the refresh/access token forward (`factory-gitops/apps/cred-broker/manifests/manifests.yaml`).
- No key-management system, no envelope encryption, and no data-encryption keys exist. There is no KMS resource in `factory-gitops`.
- Long-lived application secrets have no rotation automation and no documented custody: `JWT_SECRET`, the `acw_` API keys, the shared `POSTGRES_PASSWORD`, the MinIO root access/secret keys, and the runtime GitHub PAT. `Factory/docs/dev/secrets-and-tokens.md` documents manual, operator-driven "rotate on leak" procedures only (for example `acw_` keys are revoked by hand in the factory's key management, and MinIO creds are rotated by recreating the Secret and bouncing consumers).

## Gaps

1. No encryption at rest for Postgres data (plain `local-path` PVC).
2. No encryption at rest for MinIO objects, including audit evidence (no SSE, no KMS).
3. No encryption at rest for Redis and Keycloak volumes.
4. Kubernetes Secrets are base64-only; etcd has no `EncryptionConfiguration`, and no SOPS/sealed-secrets/ESO/Vault is deployed despite being referenced in docs.
5. No key-management system or envelope encryption; no defined data-encryption-key hierarchy or key-encryption key.
6. No key-custody documentation: who holds the master/decryption key, where it lives, and who can access it is not evidenced.
7. No rotation policy or automation for `JWT_SECRET`, `acw_` keys, DB credentials, MinIO root keys, or signing keys (only the Claude OAuth broker rotates).
8. In-cluster traffic (app-to-DB, app-to-MinIO, connector-to-Service) is not encrypted in transit.
9. FedRAMP-specific: no FIPS 140-validated cryptographic modules are asserted for any of the above.

## Remediation plan

Phased; each phase is independently shippable and leaves evidence behind.

### Phase 1 — Encrypt the storage substrate (fastest coverage)

- Enable node-level volume encryption so every `local-path` PVC (Postgres, MinIO, Redis, Keycloak) is encrypted at rest transparently: provision the node data directory on a LUKS/dm-crypt-backed disk, or move to a StorageClass whose backing volumes are encrypted (cloud provider EBS/PD encryption, or an encrypted-LVM local class). This is the single lowest-effort control that closes gaps 1-3 at once.
- Evidence: `cryptsetup status` / `lsblk` showing the encrypted device under the k3s local-path root, or the StorageClass `parameters` showing `encrypted: "true"` and the CMK reference.

### Phase 2 — Encrypt Kubernetes Secrets and formalize secret custody

- Turn on etcd encryption at rest via a k3s `EncryptionConfiguration` (aescbc/secretbox, or a KMS provider plugin), committed under `factory-gitops/bootstrap/`.
- Adopt one real secret-encryption path for git-managed secrets — SOPS+age or sealed-secrets — and actually use it (add `.sops.yaml` with the age recipient, or deploy the sealed-secrets controller), replacing the out-of-band `kubectl create secret` flow. This makes the epic's "SOPS-encrypted secrets in git" claim true.
- Evidence: `EncryptionConfiguration` manifest; a committed `.sops.yaml` / encrypted secret file with the recipient; a demonstrated decrypt on the cluster only.

### Phase 3 — Object-store and database application-layer encryption

- MinIO: enable server-side encryption. Auto-encrypt the `factory-artifacts` bucket with SSE-KMS backed by a KMS/KES service (`MINIO_KMS_KES_*`), or at minimum SSE-S3 with an auto-generated master key held in the (now-encrypted) Secret store. Evidence artifact prefixes must be marked for encryption via a bucket encryption policy in the `minio-create-bucket` Job.
- Postgres: where Phase 1 volume encryption is not available (or defense-in-depth is required), add `pgcrypto` for column-level encryption of the most sensitive fields, and/or terminate a cloud-managed encrypted Postgres (RDS/Cloud SQL with a customer-managed key).
- Evidence: `mc encrypt info fac/factory-artifacts` showing the active rule; a read of an object confirming ciphertext on disk; for Postgres, the KMS key ARN/id or the `pgcrypto` schema.

### Phase 4 — Formal key management (KMS, hierarchy, rotation)

- Stand up a key-management service (cloud KMS, or self-hosted Vault Transit / MinIO KES) as the root of trust. Define the key hierarchy: a key-encryption key (KEK) in the KMS wrapping data-encryption keys (DEKs) used by the stores — envelope encryption. Document custody: who can administer the KMS, split-knowledge/dual-control for the KEK, and break-glass procedure.
- Define and automate a key-rotation policy with explicit intervals and triggers-on-compromise for: `JWT_SECRET`, `acw_` keys, `POSTGRES_PASSWORD`, MinIO root keys, signing keys, and the runtime GitHub PAT. Extend the cred-broker pattern (already proven for the Claude OAuth token) or a scheduled Job to rotate these and restart consumers.
- Evidence: KMS key policy and rotation configuration; a rotation runbook plus at least one dated rotation event in the audit log; a key-custody register naming holders and controls.

### Phase 5 — FedRAMP only: FIPS 140-validated crypto

- Where FedRAMP is in scope, assert FIPS 140-2/140-3 validated modules for TLS, at-rest encryption, and the KMS (FIPS-mode KMS, FIPS-validated OpenSSL/Go boringcrypto builds for the services). Evidence: CMVP certificate numbers for each module and a mapping to SC-12/13/28.

### Cross-cutting — In-transit hardening (supports PCI Req. 4 / SC-8)

- Enable TLS on the Postgres wire and on app-to-MinIO (HTTPS endpoint), and consider in-cluster mTLS for connector-to-Service. Not strictly "at rest" but assessors test encryption holistically; tracked here so the crypto story is complete.

## Acceptance criteria

- [ ] Postgres data is encrypted at rest (encrypted volume/StorageClass, cloud-managed CMK, or pgcrypto) with evidence.
- [ ] MinIO objects — including the evidence prefixes — are encrypted at rest (SSE-S3 or SSE-KMS) with evidence.
- [ ] Redis and Keycloak volumes are encrypted at rest (covered by Phase 1 substrate encryption) with evidence.
- [ ] Kubernetes Secrets are encrypted at rest in etcd via a committed `EncryptionConfiguration`.
- [ ] Git-managed secrets use a real encryption path (SOPS+age or sealed-secrets) that is actually deployed and used, not just referenced in docs.
- [ ] A key-management system is in place with a documented KEK/DEK hierarchy (envelope encryption).
- [ ] Key custody is documented: holders, access controls (dual-control on the KEK), and break-glass procedure.
- [ ] A key-rotation policy with defined intervals exists and is automated for `JWT_SECRET`, `acw_` keys, DB creds, MinIO root keys, and signing keys; at least one rotation is evidenced in the audit log.
- [ ] In-transit encryption covers app-to-DB and app-to-MinIO (PCI Req. 4 / SC-8).
- [ ] FedRAMP scope only: FIPS 140-validated modules asserted with CMVP certificate references.

## Evidence artifacts

- `factory-gitops/apps/postgres/manifests/manifests.yaml` — current unencrypted `local-path` StatefulSet (baseline).
- `factory-gitops/apps/minio/manifests/manifests.yaml` — current MinIO Deployment with no SSE/KMS (baseline).
- `factory-gitops/apps/redis/manifests/manifests.yaml`, `factory-gitops/infra/keycloak/keycloak.yaml` — other `local-path` stores.
- `factory-gitops/infra/cloudflared/cloudflared.yaml` — external TLS termination; plain-HTTP origins (in-transit baseline).
- `factory-gitops/apps/cred-broker/manifests/manifests.yaml` — the one existing automated key/token rotation (pattern to extend).
- `Factory/docs/dev/secrets-and-tokens.md` — current manual, rotate-on-leak secret procedures; the SOPS reference to be made real.
- To be produced by remediation: `EncryptionConfiguration` manifest; `.sops.yaml` / sealed-secrets controller manifest; `mc encrypt info` output; StorageClass/LUKS evidence; KMS key policy + rotation config; key-custody register; rotation runbook and dated rotation audit entries; CMVP certificates (FedRAMP).
