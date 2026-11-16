---
status: draft
issue: 312
intent: intent/2026-11-16-312-mfa-and-review-schedule.md
---

# Spec: Keycloak MFA required action and access-review schedule

## Design

### 1. `keycloak-mfa` CronJob (factory-gitops, new Argo app `apps/keycloak-mfa/`)

One daily CronJob (05:10 UTC, `concurrencyPolicy: Forbid`, same shape as `apps/backups/minio-local`). It runs the **already pinned Keycloak image** (digest copied from `infra/keycloak/keycloak.yaml`), so no new image and no new signature-policy entry, and executes a POSIX script `keycloak-mfa.sh` delivered by a kustomize `configMapGenerator`. The script uses `kcadm.sh` against `http://keycloak:8080`, authenticating to the **master** realm with `KEYCLOAK_ADMIN_PASSWORD` from `factory-secrets` (existing key), and only ever operates on realm `factory`. Config/credentials file goes to an `emptyDir` (`--config`), root filesystem read-only, uid 1000, caps dropped.

Mode comes from `MFA_MODE` (plain value in the CronJob, default `audit`):

| mode | writes to Keycloak | effect |
|---|---|---|
| `audit` | **nothing** | list enabled users with no OTP/WebAuthn credential and print a count and usernames |
| `new-users` | required action `CONFIGURE_TOTP`: `enabled=true`, `defaultAction=true`; `webauthn-register` enabled | new users must enroll at first login; existing users untouched |
| `enforce` | as `new-users`, plus `CONFIGURE_TOTP` added to each enabled user with no `otp` or `webauthn` credential | existing users enroll at next login |

Safety rules (all in the script, all tested with a stub `kcadm.sh`):

- Unknown `MFA_MODE` exits non-zero with no write (fail closed to read-only).
- `MFA_EXEMPT_USERS` (comma list, default empty): never assigned the action (break-glass accounts).
- Skip disabled users and `service-account-*` users.
- Never add the action to a user who already has it, never remove an action or a credential, never touch the `master` realm.
- Any `kcadm` read failure aborts before writes (`set -eu`), so a partial listing cannot lead to enforcing on a subset by mistake; the job exits non-zero and the existing `job-watchdog` reports it.
- Secrets and tokens are never echoed; the password goes to `kcadm` through the environment-sourced variable only.

Rollback: set `MFA_MODE: audit` (stops further writes) and, to withdraw an assigned action from a user, `kcadm.sh update users/<id> -r factory -s 'requiredActions=[]'`; to withdraw the default, `kcadm.sh update authentication/required-actions/CONFIGURE_TOTP -r factory -s defaultAction=false`. Recovery for a locked-out user is the `master` admin, which the job never changes.

Open fact, observed not assumed: whether a GitHub-brokered login prompts for the required action. The runbook step says to enable `new-users`, log in with one test account, and only then enable `enforce`.

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

- `kcadm.sh update users/<id> -s 'requiredActions+=CONFIGURE_TOTP'` (array append) is unverified against the pinned 26.1 image; the stub cannot prove it. Mitigation: `audit` and `new-users` do not use it; first `enforce` run is observed by the owner, and a failed update aborts the job.
- Users enrolled only through GitHub MFA still get an OTP prompt in `enforce`. That is intended; the exempt list is the escape hatch.
- Job pod needs egress to `keycloak:8080` inside `factory`; the namespace has no default-deny for this label (the sandbox policy applies to sandbox jobs only).
- Reminder workflow: if `GITHUB_TOKEN` cannot create issues in this repo the job fails visibly; no silent skip.

## Verification

- `keycloak-mfa` script: `test.sh` with a stub `kcadm.sh` asserts each mode's calls (audit makes no write; new-users writes only the two action definitions; enforce updates only non-exempt, enabled, non-service users without a factor; rerun is idempotent; bad mode aborts), run by a workflow in factory-gitops on every PR; `manifest-validate` builds the kustomization and runs kubeconform.
- Reminder workflow: `actionlint` if configured, and a local dry run of the quarter computation for each month.
- Docs: link check via the repo's existing docs checks.
- Live: not applied by an agent; Argo syncs on merge, `audit` mode is read-only, and the first run's log is the evidence.
