---
status: draft
issue: 312
author: olafkfreund
---

# Intent: access-review runbook, role catalog and report generator

## Problem

Epic #312 has three unchecked items. Checked against code on 2026-11-16:

- **Wildcard token retirement:** done (PFactory#991, TFactory#1496, AIFactory#2017, CFactory#510, Factory#3680).
- **Fail-closed / `DISABLE_AUTH`:** done in code. CFactory `/api` and `/mcp` deny when no keys are set unless `api_dev_open` / `mcp_dev_open` is true (`CFactory apps/backend/cfactory/config.py:260-283`, `auth.py`). AIFactory and PFactory refuse `DISABLE_AUTH` on a non-loopback host (`AIFactory server/config.py:45-54`, `PFactory server/config.py:141-174`); TFactory has the same guard (`config.py:251`). The remaining ask, removing the switch from production images, is not a code gap and stays a tracked residual.
- **Fleet RBAC role model + access reviews:** the design and plan are approved (`spec|plan/2026-10-27-312-fleet-rbac-role-model.md`) and the service slices S1, S2, S5 have landed (PFactory#939/#946, TFactory#1450/#1456). The hub slices H1, H2, H3 never landed: there is no role catalog, no access-review runbook, no AR risk-acceptance entries, and the IAM policy still says "Org RBAC exists in AIFactory only". There is also no tool that turns the review inputs into `review.md`, so the Q4 2026 review (due 2027-01-15) would be assembled by hand.
- **MFA in Keycloak:** needs the owner (realm change, enrollment). Out of scope.

## Proposed outcome

- `docs/compliance/rbac-role-catalog.md` and `docs/compliance/access-review-runbook.md` exist and are linked from the compliance README, roles, IAM policy and control matrix.
- The risk register records the two standing exceptions the owner already approved on 2026-10-27 (separation of duties; `APP_API_TOKEN` and `CFACTORY_MCP_SECRET`).
- `scripts/access_review_report.py` reads the exports the runbook lists and writes a draft `review.md` with the runbook's automated checks, so the first review is a signature, not an assembly job.

## Affected users and systems

Factory hub docs and `scripts/` only. No service, gitops or cluster change.

## Constraints

- Never read or print key values; the generator must reject input containing an `acw_` token.
- Read-only inputs. No MFA enforcement, no gitops change.
- AR ids: `AR-003` is claimed by the unsigned draft in `r007-ha-options.md`; use the next free ids.

## Open questions

None. The AR-005 retirement date for the wildcard exception stays "not set" (owner input) and is reported as a finding.
