# Access Control Policy

- **Policy owner:** Security Owner (CISO function) — see [roles.md](../roles.md)
- **Applies to:** All human and machine identities that reach fleet systems or data
- **Review cadence:** Annually, and on any change to the identity or authorization model
- **Frameworks:** ISO/IEC 27001:2022 A.5.15-.18, A.8.2-.5; SOC 2 CC6.1-.3;
  NYDFS 500.7 and 500.12; NIST AC-2/AC-3/AC-6, IA-2

Control detail and current-state grounding live in the IAM domain assessment,
[iam-access-control.md](iam-access-control.md) (Factory#312). This policy states the
rules; that document evidences them.

## Purpose

To ensure that access to fleet repositories, runtime, data stores, and administrative
functions is granted only on need, scoped to the least privilege required, authenticated
strongly, and reviewed on a defined cadence.

## Scope

All identities: human contributors (via GitHub and the Keycloak `factory` realm),
machine/service accounts, CI/CD identities, and the LLM agents that act on the fleet's
behalf. All access planes: GitHub organization and repositories, the Keycloak IdP, the
application APIs (org RBAC), scoped `acw_` MCP keys, cluster RBAC, and the data stores
(Postgres, MinIO, Redis).

## Policy statements

1. **Least privilege.** Every identity receives the minimum access needed for its role.
   Cluster service accounts are scoped to the specific verbs and resources they use (for
   example the cred-broker Role can only get/patch the single `factory-cli-creds`
   Secret); application access is governed by org RBAC roles
   (viewer/member/admin/owner).
2. **Strong authentication.** Human access is federated through Keycloak with GitHub as
   the upstream IdP. Multi-factor authentication is required for human access to
   administrative and code-writing functions. MFA is not yet enforced at the IdP; until
   it is (tracked in the IAM domain), it is a documented risk in the
   [risk register](../risk-register.md), not an accepted absence.
3. **No shared standing admin credentials.** Machine-to-machine access must use scoped,
   attributable credentials (`acw_` keys carry explicit `mcp:read` / `mcp:write`
   scopes). The shared wildcard `APP_API_TOKEN`, which currently grants an
   `is_service=True` authorization bypass, is being retired in favour of scoped
   per-service credentials; its continued existence is risk R-002 in the register.
4. **Authentication is fail-closed.** Auth-disable switches (`DISABLE_AUTH`,
   `APP_DISABLE_AUTH`, CFactory OPEN mode) must never be set in production images or
   manifests. Their presence is treated as a misconfiguration incident.
5. **Joiner / mover / leaver.** Granting, changing, and revoking access follows role
   changes promptly. Revocation on departure is immediate.
6. **Periodic access review.** Access is reviewed at least quarterly using the
   `access_review.py` export; unexpected or stale grants are removed and the review is
   retained as evidence.
7. **Segregation of duties.** Where feasible, no single identity both authors and
   solely approves a privileged change; see
   [secure-sdlc-policy.md](secure-sdlc-policy.md).

## Roles and responsibilities

- **Security Owner** — owns this policy, approves role definitions and exceptions, and
  signs off the quarterly access review.
- **Control owner (IAM)** — maintains the identity model, runs the access review, and
  drives retirement of the shared wildcard token.
- **Contributors and agent operators** — request only the access they need and report
  excess or unexpected access.

## Related controls

- [iam-access-control.md](iam-access-control.md) — IAM domain assessment and evidence
- [secrets-management.md](secrets-management.md) — credential storage and rotation
- [secure-sdlc-policy.md](secure-sdlc-policy.md) — code-change authorization
- [risk-register.md](../risk-register.md) — R-002 (wildcard token), MFA gap
