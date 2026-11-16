---
status: draft
issue: 312
author: olafkfreund
---

# Intent: Keycloak MFA required action and access-review schedule

## Problem

Epic #312 (IAM) still has two items the code and gitops can move, checked against current code on 2026-11-16:

- **MFA in Keycloak is not enforced** (risk R-010, NYDFS 500.12 gap). The `factory` realm is built by hand with `kcadm.sh` (`factory-gitops docs/keycloak-sso.md`); nothing in gitops says OTP is a required action, so a user can log in with no second factor recorded.
- **The quarterly access review has a runbook and a generator but no record template and no schedule.** The runbook says "quarterly, due the 15th of the next month" (`docs/compliance/access-review-runbook.md`), yet nothing reminds anyone, and each review would start from a blank page.
- **#3702 (multi-org cockpit key)** is an open owner decision: per-org keys (shipped in CFactory#517/#519, tenant-bound) versus one multi-org key needing schema changes upstream.

Already done and out of scope here: scoped keys replacing the wildcard (code), fail-closed CFactory, `DISABLE_AUTH` guards, role catalog, runbook, generator (Factory#3757). Production cutover off `APP_API_TOKEN` and `CFACTORY_MCP_SECRET` stays the owner's.

## Proposed outcome

- A gitops CronJob keeps the Keycloak `factory` realm's OTP required action enabled and default for new users, and reports every user without an OTP credential. It starts in **audit** mode and cannot lock anyone out; the owner flips it to **enforce** after enrolling their own OTP.
- A record template and a quarterly scheduled workflow open the access-review issue with the checklist, so the Q4 2026 review is prompted.
- #3702 is decided and recorded: per-org keys; closed.
- The runbook and risk register say what MFA state is real.

## Affected users and systems

`factory-gitops` (new Argo app `keycloak-mfa`, `factory` namespace, talks only to `keycloak:8080`); Factory `docs/compliance/` and `.github/workflows/`. Keycloak `factory` realm users, including GitHub-brokered ones.

## Constraints

- Never touch the `master` realm (it is the recovery path) or any credential; the job only toggles required actions.
- Default must not lock out the owner: audit first, break-glass exemption list, no credential deletion.
- Admin password is read from the existing `factory-secrets` key `KEYCLOAK_ADMIN_PASSWORD`; no new secret, nothing printed.
- No live cluster action by an agent; Argo CD syncs the merge.
- Changes small, no new third-party image (the pinned Keycloak image already carries `kcadm.sh`).

## Open questions

None. Decision taken by owner delegation (2026-11-16): per-org keys for #3702; audit-then-enforce for MFA, because it is the least risky to operate.
