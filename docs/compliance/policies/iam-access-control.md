# IAM and Access Control

- **Domain:** IAM & access control (Factory#312)
- **Frameworks addressed:** ISO 27001 A.5.15 (access control), A.5.16 (identity management), A.5.17 (authentication information), A.5.18 (access rights), A.8.2 (privileged access), A.8.3 (information access restriction), A.8.5 (secure authentication); SOC 2 CC6.1–CC6.3 (logical access, provisioning/deprovisioning, least privilege); PCI DSS Req 7 (restrict access by need-to-know) and Req 8 (identify users, MFA); NYDFS 23 NYCRR §500.7 (access privileges) and §500.12 (MFA); FedRAMP / NIST 800-53 AC (Access Control) and IA (Identification & Authentication) families.

## Purpose

Define how the Factory fleet identifies principals, authenticates them, and restricts what each may do — across the four service planes (PFactory, AIFactory, TFactory, CFactory) and the shared cluster. This document states the grounded current state, the gaps against the frameworks above, and a phased remediation plan. It is assessor-facing: every claim cites a real file or environment variable in this monorepo set.

## Current state (grounded)

### Identity and authentication (humans)

- **Central IdP:** Keycloak 26.1 is the fleet identity provider — `factory-gitops/infra/keycloak/keycloak.yaml`. It runs one `factory` realm with one OIDC client per app, and **GitHub as an upstream identity-provider broker** (`factory-gitops/docs/keycloak-sso.md` §2–§3). Human logins to every portal flow through Keycloak via OIDC.
- **Session handling:** each service validates the OIDC JWT (or the `access_token` HttpOnly cookie set by the OIDC callback) in `TokenAuthMiddleware` — e.g. `AIFactory/apps/web-server/server/auth.py` (`_try_decode_jwt`, Strategy 1, lines 266–275). Role is taken from the `role` JWT claim, defaulting to `"user"`.
- **Org-scoped RBAC (AIFactory):** a real role model exists — `viewer / member / admin / owner` — enforced by `require_org_role(...)` in `AIFactory/apps/web-server/server/routes/organizations.py`, with per-project checks in `routes/project_authz.py`.

### Machine-to-machine authentication and the shared wildcard token

This is the single biggest access-control gap. Trace end to end:

- **Where it is defined:** a single secret key `APP_API_TOKEN` in the cluster-wide `factory-secrets` Secret, seeded out-of-band (`kubectl create secret generic factory-secrets ...`). It is injected into every plane:
  - `factory-gitops/apps/pfactory/manifests/manifests.yaml` — `APP_API_TOKEN` **and** `PFACTORY_MCP_SECRET`, both sourced from `factory-secrets/APP_API_TOKEN`.
  - `factory-gitops/apps/aifactory/manifests/manifests.yaml` — `APP_API_TOKEN` from the same key.
  - `factory-gitops/apps/tfactory/manifests/manifests.yaml` — same.
  - `factory-gitops/apps/cfactory/manifests/manifests.yaml` — `CFACTORY_UPSTREAM_TOKEN` **and** `CFACTORY_MCP_SECRET`, both from `factory-secrets/APP_API_TOKEN` (the cockpit must present the same shared token or every upstream fetch 401s).
- **Where it is consumed:** PFactory's outbound client reads it and sets `Authorization: Bearer <token>` on every sibling call — `PFactory/apps/backend/agents/tools_pkg/http_client.py` (`_read_token`, `request`, lines 93–161). CFactory probes siblings the same way — `CFactory/apps/backend/cfactory/adapters/base.py` (line 94–97).
- **What it grants:** on the receiving side, `_is_legacy_api_token()` does a constant-time match against `settings.API_TOKEN` and, on match, sets the principal to `{"id": "default", "role": "user", "is_service": True}` — `AIFactory/apps/web-server/server/auth.py` Strategy 2 (lines 277–297).
- **Why it is fleet-admin-equivalent:** `is_service_principal()` treats `is_service=True` as a trusted M2M caller that **bypasses all per-org / per-project authorization** — `AIFactory/apps/web-server/server/routes/project_authz.py` (lines 48–58: `return bool(user.get("is_service")) or user.get("role") == "admin"`). So the one shared token, present in every pod, is host-wide admin. Compromise of any single sibling yields fleet admin.
- **Deprecation status:** the token is marked DEPRECATED under #555. The only enforcement today is a **one-time log warning** (`_warn_legacy_api_token_once`, `auth.py` lines 64–83); the credential is still live and is the active PFactory->AIFactory M2M path. Deprecation without retirement is not a control.

### Scoped credentials that already exist (the target model)

- **`acw_` API keys (AIFactory):** DB-backed per-user/per-org keys with `mcp:read` / `mcp:write` scopes and constant-time validation — `AIFactory/apps/web-server/server/mcp_remote/auth.py` (`AuthenticatedKey`, `require_scope`, lines 32–144). Validated as Strategy 3 in `auth.py` (lines 299–319), carrying `org_id` scope rather than wildcard admin.
- **CFactory scoped keys:** `CFACTORY_API_KEYS` parsed into `{key: {read|write}}` scopes — `CFactory/apps/backend/cfactory/auth.py`.
- **Cluster RBAC (least-privilege, partial):** service accounts are scoped, not cluster-admin. AIFactory's SA is limited to `batch/jobs` (create/get/list/watch/delete) and `pods` + `pods/log` (read) — `factory-gitops/apps/aifactory/manifests/manifests.yaml` (lines 484–515). The credential-rotation broker (#292) is textbook least-privilege: `get`/`patch` on exactly one Secret — `factory-gitops/apps/cred-broker/manifests/manifests.yaml` (lines 9–19).
- **Access-review tooling (partial):** an NDJSON access-review export of the org member roster (email, role, `last_login_at`, active state) already exists — `AIFactory/apps/web-server/server/routes/access_review.py`, gated on `require_org_role("admin")`.

### MFA state

- **Not enforced.** Keycloak runs `start-dev` with H2 on a PVC and single replica (`keycloak.yaml` lines 33–34), and the realm + clients are configured **imperatively via `kcadm.sh`** (`keycloak-sso.md` §2), with **no realm export/import in gitops**. There is no TOTP, WebAuthn, or `requiredAction` for MFA anywhere in `factory-gitops`. MFA is effectively delegated to the upstream GitHub OAuth app and is neither required nor evidenced at the Keycloak layer. PCI Req 8.4/8.5 and NYDFS §500.12 require enforced MFA for all such access.

### Authentication bypasses

- **`DISABLE_AUTH` / `APP_DISABLE_AUTH`:** when set, `TokenAuthMiddleware` short-circuits and injects a global `admin` principal (`AIFactory/apps/web-server/server/auth.py` lines 223–229; setting default `False` in `config.py` line 114). It is **host-guarded**: `config.py` (lines 45–54) refuses to start with auth disabled on a non-loopback host, and gitops docs state "the cluster always runs real auth" (`factory-gitops/docs/build-and-deploy.md`). So the bypass is dev-only by design — but the switch exists in production images and relies on a runtime guard rather than being compiled out.
- **CFactory OPEN mode (fail-open default):** when `CFACTORY_API_KEYS` is empty the keystore is OPEN and **every request is allowed** — `CFactory/apps/backend/cfactory/auth.py` (`KeyStore.authorize`, lines 117–124; `is_open` derivation in `config.py` line 199). The gitops manifest does wire `CFACTORY_API_KEYS` from a Secret (`cfactory/manifests.yaml` line 61), but the safe default is fail-open, and the injected nginx key is described as a "harmless no-op while the keystore is open" (manifest line ~105). Fail-open is the wrong default for a control surface.

## Gaps

1. **Shared wildcard `API_TOKEN` = fleet admin (highest priority).** One token in `factory-secrets`, present in all four planes, grants `is_service=True` which bypasses all per-org/project authz. Violates least-privilege and segregation of duties (ISO A.8.2, SOC 2 CC6.1/CC6.3, PCI 7.2, NYDFS §500.7, NIST AC-6). Deprecation (#555) is log-only; the credential is still live.
2. **MFA not enforced.** No TOTP/WebAuthn required action in Keycloak; MFA neither mandated nor evidenced. Fails PCI 8.4/8.5, NYDFS §500.12, NIST IA-2(1)/(2).
3. **`DISABLE_AUTH` present in prod images.** Host-guarded but not removed; a full-bypass switch in the shipped artifact is an audit finding (NIST AC-3, SOC 2 CC6.1).
4. **CFactory fail-open default.** No keys => allow-all. Should fail closed (NIST AC-3, SOC 2 CC6.1).
5. **No fleet-wide human RBAC role model.** Org RBAC exists in AIFactory only; there is no documented least-privilege role catalog spanning all four services, and the JWT `role` defaults to `"user"` with no cross-plane role mapping.
6. **No periodic access-review process.** An export endpoint exists (`access_review.py`) but there is no defined cadence, approver, or retained evidence of a completed review (SOC 2 CC6.2/CC6.3, ISO A.5.18, SOX ITGC, NIST AC-2(3)).
7. **Keycloak is non-declarative and dev-mode.** `start-dev` + H2 + imperative `kcadm.sh` config means realm/MFA/client state is not in gitops and not reproducible or auditable.

## Remediation plan

Ownership split: **engineering** owns code/config changes (items in Phases 1–2); **docs/compliance (this program)** owns the role catalog, review cadence, and evidence retention (Phase 3). The existing credential-rotation broker (#292) is the reference pattern for scoped, rotatable machine credentials and should host the per-sibling tokens introduced below.

### Phase 1 — close the fail-open and bypass gaps (fastest, engineering)

- Make **CFactory fail-closed:** when `CFACTORY_API_KEYS` is unset in a non-loopback/hosted deployment, deny rather than allow (mirror the AIFactory `DISABLE_AUTH` host-guard in `config.py`). Keep OPEN mode only for loopback dev.
- **Gate `DISABLE_AUTH`** behind a build/runtime assertion that is impossible to enable on a cluster host (already partially present); track removing it from production images entirely.
- Enforce that every hosted deployment sets its keystore/token secret (fail startup if missing).

### Phase 2 — retire the shared wildcard token (#555) (engineering)

- **Mint per-sibling scoped credentials.** Replace the single `factory-secrets/APP_API_TOKEN` with one credential per M2M edge (PFactory->AIFactory, PFactory->TFactory, CFactory->each), each carrying only the scopes that edge needs — reuse the existing `acw_` scoped-key model (`mcp:read`/`mcp:write`, `org_id`-scoped) rather than inventing a new one. Rotate them via the #292 broker (`get`/`patch` one Secret, least-privilege SA already proven).
- **Remove the authz bypass:** change `is_service_principal()` so a service token grants only its scoped rights, not a blanket per-org/project bypass. Service principals get explicit scopes, not implicit admin.
- Prefer **mTLS between siblings** for transport identity where the ingress allows it, with the scoped bearer token carrying authorization; this removes reliance on a shared bearer secret entirely.
- Turn the #555 one-time warning into a **hard deprecation**: reject the legacy wildcard token once all edges are migrated.

### Phase 3 — MFA, RBAC model, and access reviews (engineering + docs)

- **Enforce MFA in Keycloak declaratively:** add TOTP (and WebAuthn where possible) as a realm `requiredAction`, and move Keycloak off `start-dev`/H2 to a `start` build with an external Postgres and a **realm export/import committed to gitops** so MFA policy is reproducible and auditable (`factory-gitops/infra/keycloak/`). Confirm the GitHub-broker path does not let users skip the Keycloak MFA step.
- **Document a fleet least-privilege role catalog** (viewer / operator / maintainer / owner, mapped to each service's existing checks) — this policy owns the catalog; engineering maps JWT/`acw_` scopes to it.
- **Establish quarterly access reviews:** define cadence, reviewer (org owner), and remediation SLA; drive the roster from the existing `access_review.py` NDJSON export and retain each completed review as evidence.

## Acceptance criteria

- [ ] No shared admin token: `factory-secrets/APP_API_TOKEN` is retired; each M2M edge uses a distinct scoped credential (or mTLS + scoped token), and the legacy wildcard path in `auth.py` rejects requests.
- [ ] `is_service=True` no longer bypasses per-org/project authz; service principals carry explicit scopes only.
- [ ] MFA (TOTP, WebAuthn where supported) is a Keycloak `requiredAction` for all human logins, defined declaratively in gitops, and verified for at least one login of every role.
- [ ] Keycloak realm + MFA policy is reproducible from a gitops-committed export/import (no imperative-only state).
- [ ] `DISABLE_AUTH` cannot be enabled on any cluster host; CFactory denies by default when no keys are configured (fail-closed).
- [ ] A documented fleet least-privilege role catalog exists and maps to enforced checks in all four services.
- [ ] At least one quarterly access review is completed, approved, and its evidence retained.

## Evidence artifacts

- **Token-scope inventory:** table of every M2M edge, its credential, and its scopes; proof that `APP_API_TOKEN` no longer appears in any `factory-gitops/apps/*/manifests/manifests.yaml`.
- **Keycloak MFA policy export:** the gitops-committed realm export showing the TOTP/WebAuthn `requiredAction`, plus a screenshot/log of an enrolled login per role.
- **Access-review exports:** dated NDJSON rosters from `access_review.py` (email, role, `last_login_at`, active state) with reviewer sign-off and any deprovisioning actions taken.
- **RBAC role catalog:** the least-privilege role definitions and their mapping to `require_org_role` / `acw_` scope checks and cluster RBAC (`aifactory` SA Role, `cred-broker` Role).
- **Fail-closed evidence:** startup logs / tests showing CFactory denying with no keys and services refusing to start with `DISABLE_AUTH` on a non-loopback host.
- **Deprecation-to-removal record:** the #555 change history from log-warning to hard rejection of the wildcard token.
