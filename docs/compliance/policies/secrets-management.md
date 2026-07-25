# Secrets Management and Rotation

- **Domain:** Secrets management & rotation (Factory#315)
- **Parent epic:** Factory#310
- **Frameworks addressed:**
  - ISO/IEC 27001:2022 — A.8.24 (use of cryptography), A.5.17 (authentication information)
  - SOC 2 — CC6.1 (logical access, credential protection)
  - PCI DSS v4.0 — 3.6 / 3.7 (cryptographic key management), 8.2.4 / 8.3 (credential lifecycle and rotation)
  - NYDFS 23 NYCRR 500 — 500.15 (encryption of nonpublic information), 500.7 (access privilege management)
  - FedRAMP / NIST 800-53 — IA-5 (authenticator management)

## Purpose

This document is the secrets-management control policy for the Factory fleet: how
long-lived secrets (API tokens, JWT signing keys, database passwords, agent PATs, CLI
OAuth credentials, and plan-signing keys) are stored, delivered to workloads, scanned
for, and rotated. It is an assessor-facing artifact — each control below cites the real
file that implements (or fails to implement) it, so a reviewer can verify the claim
directly against the repositories rather than take the policy on trust.

Scope: the four product services (PFactory, AIFactory, TFactory, CFactory), the
`factory-gitops` delivery repo, and the p510 k3d cluster they run on. The one credential
that already auto-rotates — the shared Claude OAuth token, via the credential broker
(Factory#292) — is credited here as the reference pattern the rest of the estate must be
brought up to.

## Current state (grounded)

### How secrets are stored and delivered

Correction to the epic's summary up front, because it matters to an assessor: the fleet
does **not** currently use SOPS-encrypted secrets in git. No `.sops.yaml`, no `sops`
metadata, and no encrypted `kind: Secret` manifests exist anywhere in `factory-gitops`
(verified by search on 2026-07-24). The actual mechanism is:

- **Host-level agenix** on the NixOS host (`nixos_config`, managed with
  `manage-secrets.sh`) for the bootstrap secret — the Tailscale operator auth key — which
  the bootstrap unit reads and seeds into the cluster as a `Secret`
  (`factory-gitops/docs/bootstrap-flow.md`, `docs/layout.md`).
- **Out-of-band `kubectl create secret`** for everything else. The gitops policy is
  explicit: *"Plaintext secrets: never. Use `kubectl create secret` out-of-band"*
  (`factory-gitops/docs/layout.md` lines 33-34). The two Secrets that hold the fleet's
  long-lived material are:
  - `factory-secrets` — `APP_API_TOKEN`, `JWT_SECRET`, `KEYCLOAK_ADMIN_PASSWORD`, DB
    credentials. Consumed via `secretKeyRef` in every product's Deployment
    (`factory-gitops/apps/{aifactory,tfactory,cfactory}/manifests/manifests.yaml`,
    `infra/keycloak/keycloak.yaml`).
  - `factory-cli-creds` — the CLI OAuth credentials (`claude-credentials.json` plus
    codex/copilot/gemini keys) mounted into build and verify pods
    (`factory-gitops/apps/tfactory/manifests/manifests.yaml`).

Net effect: secrets exist only in the live cluster and on the operator's host, never in
git. That is a defensible posture, but the decryption-key custody (who holds the agenix
identity, how the out-of-band Secrets are reconstructed on a cluster rebuild) is
**operator tribal knowledge, not evidenced** — see Gaps.

### Credential delivery: env, not argv

The standing rule after a TFactory GitHub PAT was once exposed on a command line is
**credentials via environment, never argv** — argv is world-readable via `ps` and leaks
into shell history and CI logs. This is codified as policy
(`AIFactory/skills/quality/security.md`: *"Secrets never in code, argv, or logs"*) and
enforced in practice:

- Machine-to-machine tokens are passed as env vars resolved from Secrets
  (`secretKeyRef`), never interpolated onto command lines.
- Git push authentication uses `gh auth git-credential` (a credential helper) rather than
  embedding a PAT in the push URL (Factory#725).
- The AIFactory web-server **scrubs host secrets from the agent subprocess environment**
  before spawning agent CLIs: `_AGENT_ENV_DENY_EXACT` in
  `AIFactory/apps/backend/core/auth.py` blanks `API_TOKEN`, `APP_API_TOKEN`, `JWT_SECRET`,
  `APP_JWT_SECRET`, `DATABASE_URL`, provider API keys, and Vault creds so a
  prompt-injected `env`/`printenv` cannot exfiltrate them (Factory#363). The agent's own
  OAuth vars are preserved.

### The credential broker (Factory#292) — the reference rotation pattern

One credential auto-rotates today, and it is a clean implementation worth crediting:

- A Kubernetes **CronJob** (`factory-gitops/apps/cred-broker/manifests/manifests.yaml`)
  runs every 4h (`schedule: "0 */4 * * *"`) and refreshes the shared Claude OAuth token
  in `factory-cli-creds` in place, so every service seeds a valid access token and none of
  them races to refresh (the root cause it fixed: Anthropic rotates the refresh token on
  every grant, so concurrent refreshers invalidate each other).
- **Least-privilege RBAC**: a namespaced `Role` granting `get, patch` on
  **exactly one** Secret by name (`resourceNames: ["factory-cli-creds"]`) — nothing else.
- **Never logs the token**: the `refresh.py` script is stdlib-only, prints only status
  and TTL to stderr, and exits non-zero on any failure so a broken broker surfaces as
  visible CronJob failures rather than a silently lapsed credential.
- **Hardened pod**: `runAsNonRoot`, `runAsUser: 65532`, `readOnlyRootFilesystem: true`,
  `allowPrivilegeEscalation: false`, `capabilities: drop [ALL]`, `seccompProfile:
  RuntimeDefault`, tight resource limits. Strategic-merge patch touches only the Claude
  key, leaving sibling CLI keys untouched.
- The refresh token rolls forward on each run (well inside its ~30d TTL), so no human
  re-login is needed while the broker runs; a consumed/expired refresh token fails loudly
  and asks for a human re-seed.

### Secret scanning

Secret-scanning code exists and is real:
`{PFactory,AIFactory,TFactory}/apps/backend/security/scan_secrets.py` (regex + entropy
patterns for API keys, tokens, private keys) and
`AIFactory/apps/backend/security/content_scan.py`. However, it is invoked **only
programmatically** from `apps/backend/analysis/security_scanner.py` — i.e. as part of the
scan the factory runs over *AI-generated code*, not as a gate over the fleet's own
commits. It is **not wired into any `.pre-commit-config.yaml` and not present in any
`.github/workflows/` file** (verified 2026-07-24). GitHub's native push-protection /
secret-scanning is the only pre-merge backstop, and its coverage is not evidenced.

### Encryption-at-rest key rotation (cross-reference, credited)

A separate, mature rotation mechanism exists for at-rest data-key material:
`AIFactory/apps/web-server/server/crypto/rotation.py` implements KMS root-key rotation
(re-wrapping per-org data keys under a new CMK / Vault key) with a documented runbook and
CLI (`python -m server.crypto rotate-root`). This belongs to the encryption-at-rest domain
(Factory#310 child #4) but demonstrates the fleet already has a working rotation-runbook
pattern to model application-secret rotation on.

## Gaps

1. **Rotation coverage is one credential deep.** Only the Claude OAuth token rotates.
   `JWT_SECRET`, `APP_API_TOKEN`, Keycloak admin password, database passwords, per-org
   `acw_` keys, agent GitHub PATs, and the trusted-plan HMAC signing key have **no
   documented owner and no rotation schedule**. `JWT_SECRET` in particular is
   auto-generated once and persisted to `~/.aifactory/.jwt_secret`
   (`AIFactory/apps/web-server/server/config.py`) — set-and-forget, never rolled.
   Fails PCI 3.7/8.3, NIST IA-5, ISO A.5.17.

2. **Shared cross-service secret (the wildcard `APP_API_TOKEN`).** The same
   `factory-secrets/APP_API_TOKEN` authenticates AIFactory, TFactory, CFactory, and the
   CFactory MCP bearer (`CFACTORY_MCP_SECRET` reuses it). One sibling compromise = fleet
   admin. The scoped `acw_` per-org key path already exists and is documented as the
   preferred M2M mechanism (`AIFactory/apps/web-server/server/auth.py`), but the shared
   token is still the live path. This is the shared-secret anti-pattern and is also
   tracked by the IAM domain (Factory#310 child #2). Fails least-privilege / segregation
   (SOC 2 CC6.1, NYDFS 500.7).

3. **Secret scanning is not a required pre-merge gate.** `scan_secrets.py` exists but is
   not a pre-commit hook or CI check on any of the fleet repos. A secret can reach git
   history with no automated block. Fails PCI 8.3 intent and the fleet's own stated rule.

4. **PAT scope minimization not evidenced.** Agent GitHub PATs are delivered by env (good)
   but there is no documented policy on their scope (fine-grained vs classic, repo
   allow-list, expiry). Given the prior PAT exposure, minimum-scope + short-expiry PATs
   should be the documented default. Fails NIST IA-5, PCI 8.3.

5. **No secret inventory.** There is no single register of "every long-lived secret, its
   owner, storage location, consumers, and rotation cadence." An assessor cannot confirm
   completeness of the controls above without it. Fails ISO A.5.17, SOC 2 CC6.1.

6. **Decryption-key custody not evidenced.** The agenix identity and the out-of-band
   `kubectl create secret` values are operator knowledge. On a cluster rebuild the runbook
   (recreate MinIO bucket, PLAIN `APP_API_TOKEN`, re-seed Claude token) is tribal, not a
   documented, tested custody procedure. Either evidence the custody or migrate to
   sealed-secrets / external-secrets / Vault so the source of truth is auditable.

## Remediation plan

### Phase 1 — Inventory and gate (low effort, high assurance)
- Produce the **secret inventory register** (Gap 5): a table in this folder listing every
  long-lived secret, owner, storage, consumers, rotation cadence, last-rotated date.
- Wire **`scan_secrets.py` as a required pre-commit hook and a required CI job** on all
  four product repos plus `factory-gitops` (Gap 3). Enable GitHub push-protection
  org-wide and record it as evidence.
- Document the **decryption-key custody procedure** (Gap 6): who holds the agenix
  identity, where the out-of-band Secret values are recorded, the rebuild re-seed runbook
  — as a written, testable procedure.

### Phase 2 — Retire the shared secret (depends on IAM #2)
- Cut CFactory, TFactory, and cross-service M2M calls over to scoped `acw_` keys (the
  mechanism already exists), leaving `APP_API_TOKEN` used by nothing, then delete it.
  Removes Gap 2.

### Phase 3 — Extend rotation (model on the broker + KMS runbook)
- Give each remaining long-lived secret a **documented owner and rotation cadence**, and
  automate where cheap: extend the credential-broker pattern (a least-priv CronJob
  patching one Secret) to `JWT_SECRET`, DB passwords, Keycloak admin, and the trusted-plan
  signing key; short-expiry + minimum-scope for agent PATs (Gaps 1, 4). Reuse the
  `crypto/rotation.py` runbook shape for anything KMS-backed.

### Phase 4 — Custody hardening (optional, if custody evidence is judged insufficient)
- Migrate out-of-band `kubectl` Secrets to **sealed-secrets or external-secrets/Vault** so
  the source of truth is version-controlled and auditable end-to-end, closing Gap 6
  structurally rather than by documentation alone.

## Acceptance criteria

- [ ] A secret inventory register exists listing every long-lived secret with owner,
      storage, consumers, and rotation cadence.
- [ ] Every long-lived secret has a **documented owner and a documented rotation
      cadence** (automated or scheduled-manual with evidence).
- [ ] No shared cross-service secret remains: `APP_API_TOKEN` is retired and M2M runs on
      scoped `acw_` keys (coordinated with IAM Factory#310 child #2).
- [ ] Secret scanning runs as a **required pre-merge gate** (pre-commit + CI) on all four
      product repos and `factory-gitops`; GitHub push-protection enabled org-wide.
- [ ] Agent PATs are minimum-scope with a documented expiry policy; delivery-via-env
      (never argv) is verified.
- [ ] Decryption-key custody is **evidenced**: a written, tested procedure for the agenix
      identity and out-of-band Secret reconstruction, or a migration to
      sealed/external-secrets/Vault.

## Evidence artifacts

- Credential broker: `factory-gitops/apps/cred-broker/manifests/manifests.yaml`
  (CronJob, least-priv Role, `refresh.py`), `factory-gitops/apps/cred-broker/application.yaml`.
- Secret delivery via `secretKeyRef`:
  `factory-gitops/apps/{aifactory,tfactory,cfactory}/manifests/manifests.yaml`,
  `factory-gitops/infra/keycloak/keycloak.yaml`.
- Out-of-band secret policy: `factory-gitops/docs/layout.md`,
  `factory-gitops/docs/bootstrap-flow.md`.
- Env-not-argv scrubbing: `AIFactory/apps/backend/core/auth.py` (`_AGENT_ENV_DENY_EXACT`);
  policy in `AIFactory/skills/quality/security.md`.
- Scoped-key path: `AIFactory/apps/web-server/server/auth.py`.
- JWT auto-generation (no rotation): `AIFactory/apps/web-server/server/config.py`.
- Secret scanners: `{PFactory,AIFactory,TFactory}/apps/backend/security/scan_secrets.py`,
  `AIFactory/apps/backend/security/content_scan.py`,
  `apps/backend/analysis/security_scanner.py` (invocation site).
- KMS root-key rotation runbook (cross-ref): `AIFactory/apps/web-server/server/crypto/rotation.py`.
