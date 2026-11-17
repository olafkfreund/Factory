# Access review record: <YYYY>-Q<n>

Copied into the issue "Access review <YYYY>-Q<n>" by `.github/workflows/access-review-reminder.yml` on the first day of each quarter. Procedure and checks: [access-review-runbook.md](access-review-runbook.md). Roles: [rbac-role-catalog.md](rbac-role-catalog.md). Never paste a key value here or in the evidence: keys appear as ids or `key_actor` hashes.

- **Period reviewed:** <YYYY>-Q<n>
- **Due:** the 15th of the first month after the quarter ends
- **Reviewer and signer:** the Security Owner (AR-004: sole reviewer and grantor, a recorded exception)
- **Evidence directory:** `factory-evidence/control-plane-push/access-review/<YYYY>-Q<n>/`

## Checklist

- [ ] 1. Exports collected read-only into one directory (the runbook's Inputs table)
- [ ] 2. `python3 scripts/access_review_report.py --in <dir> --out <dir>/review.md --now <YYYY-MM-DD>` run; no `acw_` token in the directory (`grep -rE 'acw_[A-Za-z0-9]{8,}' <dir>` prints nothing)
- [ ] 3. One action per finding written in `review.md`: revoke, accept with a reason, or set a date
- [ ] 4. `review.md` signed by the owner
- [ ] 5. `review.md` and the raw exports stored in the evidence directory
- [ ] 6. Revocations done within five working days of signing; anything slower is recorded below with an owner and a date

## Findings and actions

| Finding | Action (revoke / accept: reason / date) | Owner | Done on |
|---|---|---|---|
| | | | |

## State recorded this quarter

- **MFA** (from `keycloak-users.json`): `keycloak-mfa` mode `<audit | new-users | enforce>`; users without a second factor: `<n>`
- **Platform admin accounts** (kubectl, Argo CD, Keycloak admin): `<listed>`
- **Wildcard retirement** (`APP_API_TOKEN`, `CFACTORY_MCP_SECRET`): retirement date `<set | not set>`; legacy counters `<values>`

## Accepted exceptions

AR-004 (separation of duties), AR-005 (wildcard tokens, until the retirement date), MFA not enforced (until `keycloak-mfa` runs in `enforce`). See the [risk register](risk-register.md).

## Signature

Reviewer / signer: ____________________  Date: ____________
