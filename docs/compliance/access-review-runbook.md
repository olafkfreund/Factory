# Access Review Runbook

- **Owner and signer:** the Security Owner (AR-004: sole reviewer and grantor, a recorded exception)
- **Cadence:** quarterly, due by the 15th of the first month after the quarter ends (Q4 2026: **2027-01-15**), and within five working days of anyone leaving or changing role
- **Frameworks:** SOC 2 CC6.2, CC6.3; ISO/IEC 27001:2022 A.5.18; NIST AC-2(3); SOX ITGC access
- **Roles reviewed:** [rbac-role-catalog.md](rbac-role-catalog.md)
- **Record and reminder:** `.github/workflows/access-review-reminder.yml` opens the issue "Access review <YYYY>-Q<n>" on the first day of January, April, July and October from [access-review-record-template.md](access-review-record-template.md); it tracks the sign-off, the evidence path and the revocation deadline

## Procedure

1. Collect the exports below, read-only, into one directory. Never export a key value: keys appear as ids or `key_actor` hashes.
2. Run the generator, then read the findings.

   ```bash
   python3 scripts/access_review_report.py --in <dir> --out <dir>/review.md --now <YYYY-MM-DD>
   grep -rE 'acw_[A-Za-z0-9]{8,}' <dir>   # must print nothing
   ```

   The generator exits 2 and writes nothing if any input holds an `acw_` token shape. A missing input is a finding, not a pass.
3. Write one action per finding in `review.md`: revoke, accept with a reason, or set a date. The owner signs.
4. Store `review.md` and the raw exports at `factory-evidence/control-plane-push/access-review/<YYYY>-Q<n>/`.
5. Do the revocations within five working days of signing. Anything slower is recorded as an exception with an owner and a date.

## Inputs

Each row's command is read-only and its output is reduced to the schema in the plan (`plan/2026-11-16-312-access-review-runbook.md`, "Generator contract"). Reduce with `jq`, keeping only the listed fields.

| File in `<dir>` | Source |
|---|---|
| `members-<service>.ndjson` | AIFactory `GET /api/admin/access-review?org_id=` (lines: `email, role, active, last_login_at`). PF and TF: by hand from the membership tables until slice S3. Add `org_id` and `tenant_groups` from Keycloak when available |
| `keys.json` | No service lists other members' keys through the API. The platform admin runs a read-only query per service database (`SELECT id, user_id, scopes, autonomy_ceiling, last_used_at, expires_at FROM api_keys`; never select the key hash or prefix), joins the owner's current role from `org_members`, and writes `{key_id, owner, owner_role, scopes, autonomy_ceiling, last_used_at, expires_at, service}` |
| `cfactory-keys.json` | `{actor, scope}` derived from `CFACTORY_API_KEYS` by the platform admin, as `key_actor` hashes |
| `bindings.json` | `kubectl get rolebinding,clusterrolebinding -A -o json \| jq '[.items[] \| {name: .metadata.name, kind, subjects: (.subjects // []), justification: (.metadata.annotations["factory.io/justification"] // "")}]'`; the reviewer fills `justification` where the annotation is absent |
| `keycloak-users.json` | `kcadm.sh get users -r <realm>` and, per user, `kcadm.sh get users/<id>/credentials -r <realm>`; `mfa` is `totp`, `webauthn` or `none` from the credential types |
| `platform-admins.json` | `{system, account}` listed by hand: kubectl, ArgoCD, Keycloak admin |
| `legacy-counters.json` | `{name, count}` from the `_warn_legacy_api_token_once` logs and the CFactory legacy-MCP counter (CFactory#504) |
| `exceptions.json` | `{"wildcard_retirement_date": "YYYY-MM-DD"}` once the owner sets it |

## review.md template

The generator writes this; the reviewer completes it.

```markdown
# Access review draft (<date>)
## Findings            one line per finding, from the generator
## Evidence recorded   MFA state, platform-admin accounts, CFactory key actors, legacy counters
## Actions             per finding: revoke | accept (reason) | date. Revoke within five working days of signing
## Accepted exceptions AR-004, AR-005 (retirement date), MFA not enforced
## Signature           reviewer / signer, date
```

## Checks the generator runs

- A key's scopes are wider than its owner's role (a `viewer` may hold only `mcp:read`).
- A member above `viewer`, active or not, with no login in 90 days, or none recorded.
- An email with more than one role in one org; a member without exactly one tenant group (reported "manual" when the export has no groups).
- A key unused for 90 days, a key with no expiry, a key with a null `autonomy_ceiling`.
- A binding with no recorded justification, bound to a human (`User`), or bound to a `Group` (assess the group's members by hand).
- The wildcard retirement date is not set.

MFA state is recorded for every Keycloak user. Enforcement is built but off until the owner turns it on: the gitops CronJob `keycloak-mfa` (factory-gitops `apps/keycloak-mfa`, [keycloak-sso.md](https://github.com/olafkfreund/factory-gitops/blob/main/docs/keycloak-sso.md) section "MFA") runs in `audit` mode by default, which writes nothing and logs users without a second factor. The owner climbs `audit`, `new-users`, `enforce` one change at a time; `enforce` refuses to run unless the owner is already enrolled. Record the mode and the unenrolled count in each review. Until `enforce` has run, MFA is an accepted exception.

## Accepted exceptions (listed in every review)

AR-004 separation of duties, AR-005 `APP_API_TOKEN` and `CFACTORY_MCP_SECRET`, and MFA not enforced (until `keycloak-mfa` runs in `enforce`). See the [risk register](risk-register.md).

## Not covered

Live cluster listings and Keycloak exports are collected by a person with access; this runbook does not give an agent that access.
