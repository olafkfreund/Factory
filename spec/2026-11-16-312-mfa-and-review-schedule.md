---
status: draft
issue: 312
intent: intent/2026-11-16-312-mfa-and-review-schedule.md
---

# Spec: Keycloak MFA required action and access-review schedule

## Design

### 1. `keycloak-mfa` CronJob (factory-gitops, new Argo app `apps/keycloak-mfa/`)

One daily CronJob (05:10 UTC, `concurrencyPolicy: Forbid`, same shape as `apps/backups/minio-local`). It runs the **already pinned Keycloak image** (digest copied from `infra/keycloak/keycloak.yaml`), so no new image and no new signature-policy entry, and executes a POSIX script `keycloak-mfa.sh` delivered by a kustomize `configMapGenerator`. The script uses `kcadm.sh` against `http://keycloak:8080`, authenticating to the **master** realm with `KEYCLOAK_ADMIN_PASSWORD` from `factory-secrets` (existing key), and only ever operates on realm `factory`. Config/credentials file goes to an `emptyDir` (`--config`), root filesystem read-only, uid 1000, caps dropped.

Mode comes from `MFA_MODE` (plain value in the CronJob, default `audit`). A user "has a second factor" when `users/<id>/credentials` lists type `otp`, `webauthn` or `webauthn-passwordless`.

| mode | writes to Keycloak | effect |
|---|---|---|
| `audit` | **nothing** | list enabled users with no second factor, with a count; no service-account users |
| `new-users` | required action `CONFIGURE_TOTP`: `enabled=true`, `defaultAction=true` | users created from now on must enroll OTP at first login; existing users untouched |
| `enforce` | as `new-users`, plus `CONFIGURE_TOTP` added to each enabled, non-exempt user with no second factor | those users enroll at next login |

WebAuthn registration is not enabled here: Keycloak's `webauthn-register` action is not an alternative to OTP when OTP is mandatory, so adding it would not help users who cannot do OTP. Users who already hold a WebAuthn credential count as enrolled. WebAuthn as a choice is a follow-up.

Safety rules (all in the script, tested with a stub `kcadm.sh`):

- Unknown `MFA_MODE` exits non-zero with no write.
- **Reads first, then writes.** The script collects the realm's user list and each user's credentials and required actions into temp files with an explicit failure check on every `kcadm` call, builds the target list, and only then writes. A failed read exits before any write (`set -eu` is not relied on for pipelines).
- **Owner guard.** `enforce` aborts unless `MFA_REQUIRE_ENROLLED` (comma list of usernames, set to the owner) is non-empty and every listed user already has a second factor. Enrolling the owner first is therefore a code-enforced prerequisite, not a runbook hope.
- `MFA_EXEMPT_USERS` (comma list, default empty): never assigned the action by the job. This does **not** cover the realm default, which Keycloak applies to any newly created user; break-glass accounts must be created before `new-users` is switched on, or enrolled right away.
- Skip disabled users and `service-account-*` users; never add the action to a user who already has it; never remove an action or a credential; never touch the `master` realm.
- The password reaches `kcadm` from the environment variable only and is never echoed.

Rollback: set `MFA_MODE: audit` (stops further writes; it does **not** undo the realm default or already-assigned actions). Withdraw the default: `kcadm.sh update authentication/required-actions/CONFIGURE_TOTP -r factory -s defaultAction=false`. Withdraw an assigned action from one user: admin console, Users, Required user actions, remove "Configure OTP" only (do not set `requiredActions=[]`, it would also clear password-change and email-verification actions). Recovery for a locked-out user is the `master` realm admin, which the job never changes.

Open fact, observed not assumed: whether a GitHub-brokered login prompts for the required action. `new-users` only affects users created afterwards, so the runbook step is: create a fresh brokered test user (a throwaway GitHub account), log in, confirm the OTP prompt, then enroll the owner, set `MFA_REQUIRE_ENROLLED`, and only then enable `enforce`.

### 2. Aifactory App wiring and runbook live in the AIFactory spec (`spec/2026-11-16-1973-agent-token-admin-guard.md` in AIFactory); this spec only references them.

### 3. Access-review schedule and record (Factory)

- `docs/compliance/access-review-record-template.md`: the per-review record: period, due date, evidence directory (`factory-evidence/control-plane-push/access-review/<YYYY>-Q<n>/`), the runbook procedure as a checklist, the generator command, findings/actions table, accepted exceptions, MFA state, signature and the five-working-day revocation deadline.
- `.github/workflows/access-review-reminder.yml`: `schedule` on the 1st of January, April, July and October at 08:00 UTC plus `workflow_dispatch`. Permissions `contents: read`, `issues: write`. It computes the quarter that just ended, skips if an issue titled `Access review <YYYY>-Q<n>` already exists (open or closed), and otherwise runs `gh issue create --body-file` with the template. No third-party action except the pinned `actions/checkout` already used in the repo.
- `docs/compliance/access-review-runbook.md`: link the template and schedule; replace "MFA is recorded, not enforced" with the real state and the audit/new-users/enforce ladder; `risk-register.md` R-010 gets a status note (mitigation built, enforcement pending owner), not a closure.

### 4. #3702

Decision: per-org keys. CFactory#517 and #519 are merged: extra `/ws/events` sockets via `CFACTORY_<SVC>_ORG_TOKENS`, `tenant=key` form scopes events to that tenant. A multi-org key would need upstream schema and key-model changes for no capability the per-org keys lack. Recorded as an issue comment and closed.

## Alternatives rejected

- **Keycloak realm import/export file now**: the realm is built imperatively and holds secrets, users and the GitHub IdP; a half export could overwrite live state on sync. Idempotent kcadm configuration is the smaller, reversible step. Declarative realm export stays a recorded gap.
- **Enforce by default**: could prompt every user, including the owner, with no tested recovery. Rejected for audit-first.
- **A Keycloak authentication-flow (conditional OTP) change**: touches the browser and first-broker-login flows; a mistake locks everyone out. Required actions are per-user and removable.
- **Reminder as a cron on the cluster**: the review is a GitHub-tracked task; an issue is the audit trail.
- **A multi-org cockpit key (#3702)**: see above.

## Risks

- `kcadm.sh update users/<id> -s 'requiredActions+=CONFIGURE_TOTP'` (array append) is unverified against the pinned 26.1 image; the stub cannot prove it. Mitigation: `audit` and `new-users` do not use it, so the first live exercise is the owner's first `enforce` run, which also needs the owner guard to pass. If the append syntax is wrong the update fails and the job aborts without partial assignment beyond the users already updated. This remains an open verification, not a guarantee.
- Users enrolled only through GitHub MFA still get an OTP prompt in `enforce`. That is intended; the exempt list is the escape hatch.
- Job pod needs egress to `keycloak:8080` inside `factory`; the namespace has no default-deny for this label (the sandbox policy applies to sandbox jobs only).
- Reminder workflow: if `GITHUB_TOKEN` cannot create issues in this repo the job fails visibly; no silent skip.

## Verification

- `keycloak-mfa` script: `test.sh` with a stub `kcadm.sh` asserts each mode's calls (audit makes no write; new-users writes only the two action definitions; enforce updates only non-exempt, enabled, non-service users without a factor; rerun is idempotent; bad mode aborts), run by a workflow in factory-gitops on every PR; `manifest-validate` builds the kustomization and runs kubeconform.
- Reminder workflow: `actionlint` if configured, and a local dry run of the quarter computation for each month.
- Docs: link check via the repo's existing docs checks.
- Live: not applied by an agent; Argo syncs on merge, `audit` mode is read-only, and the first run's log is the evidence.
