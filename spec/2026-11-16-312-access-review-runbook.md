---
status: draft
issue: 312
intent: intent/2026-11-16-312-access-review-runbook.md
---

# Spec: access-review runbook, role catalog and report generator

## Design

Carries slices H1, H2, H3 of the approved `plan/2026-10-27-312-fleet-rbac-role-model.md` unchanged in substance, and adds one script the plan only implied.

**Docs (hub, `docs/compliance/`)**

- `rbac-role-catalog.md` (H1): principal kinds, roles `viewer < member < admin < owner`, `platform-admin`, agent rules, JWT-role guardrail, service-principal edge table, cluster-workload note, and the action matrix. Each "Enforced by" cell cites a file in the service repo, checked against that repo's `origin/dev` on the day of writing; cells for task routes say whether `RBAC_ENFORCE_TASK_ROUTES` is on.
- `access-review-runbook.md` (H2): cadence, inputs table, checks, output layout, `review.md` template, the never-a-key-value grep, and how to run the generator.
- `risk-register.md` (H2): two acceptance entries, **AR-004** (the owner is sole reviewer and grantor; SoD exception) and **AR-005** (`APP_API_TOKEN` and `CFACTORY_MCP_SECRET` standing exception, linked to R-002; retirement date "not set"). The plan named AR-003 and AR-004; AR-003 is now claimed by an unsigned draft in `r007-ha-options.md`, so the ids move up by one. Accepted 2026-10-27 (the owner's answers 1 and 5 in the plan), review by 2027-04-27.
- H3: IAM policy gaps 4, 5, 6 updated; `control-matrix.md` IAM row, `README.md` and `roles.md` link the new files.

**Generator** `scripts/access_review_report.py` (stdlib only). Input: a directory of read-only exports; every file optional, and a missing file becomes a finding ("input not provided"), never a silent pass.

| File | Content |
|---|---|
| `members-<svc>.ndjson` | AIFactory `/api/admin/access-review` lines (`email, role, active, last_login_at`), optionally with `org_id` and `tenant_groups` (the collector adds them from Keycloak) |
| `cfactory-keys.json` | list of `{actor, scope}` (the `key_actor` hash, never the key; `write` maps to `member`, `read` to `viewer`) |
| `legacy-counters.json` | list of `{name, count}` (`_warn_legacy_api_token_once` hits, CFactory #504 legacy MCP counter), recorded as evidence |
| `keys.json` | list of `{key_id, owner, owner_role, scopes, autonomy_ceiling, last_used_at, expires_at, service}` |
| `bindings.json` | list of `{name, kind, subjects:[{kind,name}], justification}` |
| `keycloak-users.json` | list of `{username, enabled, mfa}` (MFA recorded, not enforced) |
| `platform-admins.json` | list of `{system, account}` |
| `exceptions.json` | `{wildcard_retirement_date}` or absent |

Checks, as in the plan: key scopes wider than the owner's role (a `viewer` may hold only `mcp:read`); any member above `viewer`, active or not, with no login for 90 days (a missing `last_login_at` counts as no login); an email with more than one role in one org, and, when `tenant_groups` is present, anything other than exactly one group (otherwise reported "manual: tenant group not in export"); key unused 90 days or with no expiry; null `autonomy_ceiling`; binding without justification, or with a `User` subject (a `Group` subject is flagged for manual assessment of its members); wildcard retirement date unset; MFA state listed per Keycloak user; legacy counters and CFactory key inventory listed as evidence. Output: `review.md` with Findings, Actions, Accepted exceptions (AR-004, AR-005, MFA not enforced), Signature (blank, the owner signs). Exit 0 always on a successful render; exit 2 if any input contains an `acw_` token shape (it refuses to write output), so a secret cannot reach the evidence store. `--now` fixes the clock for tests.

## Alternatives rejected

- **Generator inside each service.** Three implementations of one report; the hub already owns the evidence layout.
- **Calling the APIs from the script.** Needs credentials; the owner or the collector fetches exports, the script only reads them.
- **Docs only.** Leaves the first review (due 2027-01-15) as manual assembly with no test.
- **Enforcing MFA or flipping `RBAC_ENFORCE_TASK_ROUTES`.** Owner decisions, out of scope.

## Risks

- Docs cite lines in other repos that drift: cite the file and symbol, line only where checked.
- Generator reports false assurance on a missing input: mitigated by treating missing as a finding.
- Recording AR-004/AR-005 as accepted: the plan records the owner's 2026-10-27 answers; the entries cite it.

## Verification

`pytest tests/test_access_review_report.py` (new: each check fires, a clean input has no findings, missing input is a finding, token-shaped input exits 2 and writes nothing); `ruff check` on the script; `grep -n 'AR-004\|AR-005' docs/compliance/risk-register.md`; every link in the catalog resolves (`git -C <repo> show origin/dev:<path>`); hub CI green.
