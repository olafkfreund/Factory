---
status: approved
issue: 3688
spec: spec/2026-11-16-3688-security-alerts.md
coders:
  1: lead   # small tricky logic, written by the lead; codex reviews the diff
  2: lead
  3: lead
  4: lead
reviewers:
  - codex   # independent read-only review of each draft and the final diff
---

# Plan: auth-failure and egress alerts, IR tabletop (R-009)

Decisions carried from the approved spec: new factory-gitops app `apps/security-alerts`, a CronJob
every 15 minutes evaluating two rules (`auth_failure_spike` = count of `action = 'auth.failure'` rows in `audit_chain`, 30 min window,
env `AUTH_FAIL_THRESHOLD` default 10; `egress_anomaly` = row count in stream `EGRESS_STREAM`, env `EGRESS_THRESHOLD` default 1, stream default empty, reports
`not_configured`, 404 reports `no_source`, never ok). Both rules always evaluated; one `job_health`
record each; one GitHub issue per firing rule while none is open (label `security-alert`, inert
without `GITHUB_TOKEN`); optional webhook (`security-alert-webhook`/`url`, optional) POSTed on every
firing run with `dedup_key`; exit 1 if any rule errored or a delivery failed. Factory docs:
tabletop scenario plus record template. Known limit: forwarder backlog can evade the window.
This slice leaves Factory#3688 open.

## Steps

(repo factory-gitops, worktree `.../teams/f3688a/factory-gitops`, branch `feat/3688-security-alerts`)

1. `apps/security-alerts/manifests/alerts.py` and `test_alerts.py`, modelled on
   `apps/secret-rotation/manifests/report.py` and `test_report.py` → `python3 apps/security-alerts/manifests/test_alerts.py`
   Test cases: below threshold ok; at threshold firing; not_configured exits 0; 404 gives no_source; auth query error still evaluates egress and exits 1; issue created once and deduped on an open marker; no GITHUB_TOKEN inert; webhook off sends nothing, on posts with dedup_key each firing run, POST failure exits 1.
   Traps: stdlib only; never print a value or `str(e)`; OpenObserve search needs start/end in
   microseconds and not 0; 404 means stream missing.
2. `apps/security-alerts/{application.yaml,manifests/kustomization.yaml,manifests/manifests.yaml}`
   and `.github/workflows/security-alerts-test.yml` (copy of secret-rotation's) → `kubectl kustomize apps/security-alerts/manifests` renders, repo yaml lint/manifest-validate passes.
   Traps: image digest pinned like secret-rotation; restartPolicy Never; ConfigMap generator without
   hash suffix; no RBAC needed (no Kubernetes API access), so `automountServiceAccountToken: false`.
3. `docs/security-alerts.md` in factory-gitops: rules, env, statuses, how to supply the webhook
   Secret, how to build the OpenObserve Destination for existing `job_health` failures, egress source contract, known limits → read-through; link from `docs/job-health-watchdog.md`.
4. (repo Factory, worktree `.../f3688a/Factory`, branch `docs/3688-ir-tabletop`)
   `docs/compliance/ir-tabletop.md` (scenario, injects, roles, record template), link from
   `docs/compliance/policies/incident-response.md` gap 3 and from the R-009 row of
   `docs/compliance/risk-register.md` (remaining gap text only; do not change scores) → `grep` links resolve; docs lint if present.

## Tests

- `python3 apps/security-alerts/manifests/test_alerts.py` exits 0.
- `kubectl kustomize apps/security-alerts/manifests >/dev/null`.
- PR checks green on exact head SHA.

## Rollback

Delete `apps/security-alerts` (Argo prunes); revert the Factory docs commit. Nothing else depends on it.
