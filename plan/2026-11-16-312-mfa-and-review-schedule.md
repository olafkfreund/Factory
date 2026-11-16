---
status: draft
issue: 312
spec: spec/2026-11-16-312-mfa-and-review-schedule.md
coders:
  # all steps by the lead: small, and the shell script is verified by its own stub test; a handoff would not repay its re-read
  1: lead
  2: lead
  3: lead
  4: lead
  5: lead
  6: lead
reviewers:
  - codex   # independent read of the final diffs against this plan
---

# Plan: Keycloak MFA required action and access-review schedule

Carries the approved spec (`spec/2026-11-16-312-mfa-and-review-schedule.md`) without needing it open.

## Approved decisions

- gitops CronJob `keycloak-mfa` (new Argo app `apps/keycloak-mfa/`, namespace `factory`), daily 05:10 UTC, `concurrencyPolicy: Forbid`, running the Keycloak image already pinned in `infra/keycloak/keycloak.yaml` (same digest), script via kustomize `configMapGenerator`, `kcadm.sh` against `http://keycloak:8080`, master-realm admin login with `KEYCLOAK_ADMIN_PASSWORD` from `factory-secrets`, operating on realm `factory` only. uid 1000, read-only root fs, `emptyDir` for the kcadm config, caps dropped.
- `MFA_MODE` default `audit` = no Keycloak writes. `new-users` = enable `CONFIGURE_TOTP` + `defaultAction=true`. `enforce` = also add `CONFIGURE_TOTP` to enabled, non-exempt, non-service users with no `otp`/`webauthn`/`webauthn-passwordless` credential. Unknown mode exits non-zero with no write.
- Reads before writes with explicit failure checks. `enforce` aborts unless `MFA_REQUIRE_ENROLLED` (non-empty) lists only users who already have a second factor. `MFA_EXEMPT_USERS` are never assigned. Never remove an action or credential, never touch `master`.
- No WebAuthn registration action in this job.
- Rollback is documented in the runbook: `MFA_MODE=audit`, `defaultAction=false`, remove only "Configure OTP" per user.
- Access review: record template `docs/compliance/access-review-record-template.md`; workflow `.github/workflows/access-review-reminder.yml` on the 1st of Jan/Apr/Jul/Oct 08:00 UTC plus `workflow_dispatch`, `contents: read` + `issues: write`, one issue per quarter just ended titled `Access review <YYYY>-Q<n>`, skip when one exists.
- #3702 closes with the per-org-keys decision; R-010 stays open.

Artifacts for AIFactory's #1973/#1700/#1701 live in the AIFactory repo (`spec|plan/2026-11-16-1973-agent-token-admin-guard.md`); the gitops aifactory wiring step belongs to that plan, executed in the same gitops PR.

## Steps

Factory repo (this PR):

1. `docs/compliance/access-review-record-template.md` (new): period/due-date header, evidence path, checklist from `access-review-runbook.md` (collect, generate, read findings, actions, sign, store, revoke within 5 working days), findings/actions table, accepted exceptions (AR-004, AR-005, MFA state), signature block. → verify: the checklist covers every numbered runbook step (diff the numbered list by eye and record it in the PR).
   Traps: never put a key value in the template; the runbook forbids `acw_` strings in evidence.
2. `.github/workflows/access-review-reminder.yml` (new): schedule + dispatch, quarter computation (Jan->previous year Q4, Apr->Q1, Jul->Q2, Oct->Q3; dispatch accepts an optional `quarter` input), `gh issue list --state all --search` dedupe on the exact title (match the title exactly in the output, closed issues included), `gh issue create --body-file` from the template with `sed` for the placeholders. Pinned `actions/checkout` SHA copied from another workflow in the repo. → verify: run the shell block locally for 12 month values with a stubbed `gh` covering no issue, an open issue and a closed issue; `actionlint` if installed.
   Traps: Factory workflow rules in `.github/workflows` (pin by SHA, minimal `permissions`); a required check must not go missing, this workflow is not a PR check.
3. `docs/compliance/access-review-runbook.md`: link the template and schedule; replace the "MFA state is recorded, not enforced" lines with the real state (CronJob built, audit default, owner enables enforce) and add the audit -> new-users -> enforce ladder and rollback. `docs/compliance/risk-register.md` R-010: status note, still open. → verify: `grep -n "enforced" docs/compliance/*.md` shows no sentence claiming enforcement; every relative link added resolves (`test -f`); run the repo's markdown/doc tests under `tests/` if any cover `docs/compliance`.
   Traps: do not claim MFA is enforced; the owner has not enabled it.
factory-gitops repo (separate PR, base `main`):

4. `apps/keycloak-mfa/application.yaml` (new Argo app, path `apps/keycloak-mfa/manifests`, `prune`, `selfHeal`), `apps/keycloak-mfa/manifests/{kustomization.yaml,cronjob.yaml,keycloak-mfa.sh,test.sh}`, `.github/workflows/keycloak-mfa-test.yml` (no `paths` filter, runs `sh apps/keycloak-mfa/manifests/test.sh` with a stub `kcadm.sh`). `docs/keycloak-sso.md`: new section "MFA" with the ladder, rollback and break-glass notes, and `docs/` nav entry if the mkdocs nav lists pages. → verify: `sh test.sh`; `kustomize build`; `kubeconform`; the repo's manifest-validate (kyverno policies: image digest, securityContext).
   Traps: the Keycloak image digest must equal the one in `infra/keycloak/keycloak.yaml`; no secret echoed; `automountServiceAccountToken: false`; resource requests/limits (JVM: kcadm needs about 256 Mi; set `JAVA_OPTS_KC_HEAP`-style limits with a 512 Mi limit) so the job-watchdog sees success.
5. `apps/aifactory/manifests/manifests.yaml` and `docs/aifactory-github-app-cutover.md` in the same gitops PR (AIFactory plan `plan/2026-11-16-1973-agent-token-admin-guard.md`): add `AIFACTORY_GITHUB_APP_ID`, `AIFACTORY_GITHUB_APP_INSTALLATION_ID`, `AIFACTORY_GITHUB_APP_PRIVATE_KEY` as `secretKeyRef` to `factory-secrets` with `optional: true` (all three or none), `AIFACTORY_AGENT_TOKEN_ADMIN_POLICY: "warn"`, keep `GITHUB_TOKEN`; the runbook lists the cutover order (add all three keys and remove the `GITHUB_TOKEN` entry in one window, confirm no other PAT source, leave `AIFACTORY_AGENT_GITHUB_TOKEN` unset, boot check, probe-copilot from a workstation for #1701, revoke admin scopes, set policy `refuse`). Also check `chart-vs-gitops` expectations. → verify: `kustomize build apps/aifactory/manifests` shows the entries, `kubeconform`.

6. Issue handling (after both PRs are open): comment on Factory#3702 `Decision (owner delegation 2026-11-16): per-org keys` and close it (`gh issue close 3702 --reason completed`); comment on Factory#312 what was done and what remains (enable `new-users` then `enforce`; production cutover off `APP_API_TOKEN`/`CFACTORY_MCP_SECRET`; PF/TF enforcement flag; admin key revoke S4); #312 stays open. Comment the decisions on AIFactory#1973, #1700, #1701; they stay open for owner steps. → verify: `gh issue view` states.

## Tests

- `sh apps/keycloak-mfa/manifests/test.sh` in factory-gitops: audit makes zero writes and lists unenrolled users with a count; new-users docs name the fresh brokered test-user check and the exemption-versus-realm-default limit; new-users writes only the required-action definition; enforce updates only non-exempt enabled users without a factor, skips service accounts, is idempotent on rerun, aborts when `MFA_REQUIRE_ENROLLED` is empty or names a non-enrolled user, aborts on a failed read before any write, aborts on an unknown mode.
- Reminder workflow quarter computation for every month; dedupe stub.
- factory-gitops `manifest-validate`; Factory docs/pre-commit checks.

## Rollback

Revert the PRs. The Argo app prunes the CronJob. Realm state the job may have written (default action, assigned actions) is undone by the rollback commands in the runbook; `audit` mode writes nothing.
