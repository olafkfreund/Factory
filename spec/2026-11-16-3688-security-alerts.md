---
status: approved
issue: 3688
intent: intent/2026-11-16-3688-security-alerts.md
---

# Spec: auth-failure and egress alerts, IR tabletop (R-009)

## Design

The cluster has no Prometheus or Alertmanager (factory-gitops `apps/audit-anchor-alert/README.md`,
`docs/argocd-sync-honesty.md`), so the existing alert path is: a CronJob writes `job_health`
records to OpenObserve, job-watchdog watches the CronJob, and issues open in GitHub. Reuse it.

1. factory-gitops `apps/security-alerts`: CronJob every 15 minutes, stdlib Python 3.12 (copy of the
   `apps/secret-rotation` shape: ConfigMap script, hardened pod, `observe-root` login).
   - Rule `auth_failure_spike`: `count(*)` of `action = 'auth.failure'` rows in `audit_chain`
     over the last 30 minutes. Fires at `AUTH_FAIL_THRESHOLD` (default 10). Statuses `ok`,
     `firing`, `error`. The forwarder lags up to 15 minutes, hence the 30-minute window.
   - Rule `egress_anomaly`: `count(*)` of rows in the stream named by `EGRESS_STREAM` over the
     same window; fires at `EGRESS_THRESHOLD` (default 1). Contract: every row in that stream is one
     off-allowlist connection. `EGRESS_STREAM` is empty by default, so the rule reports
     `not_configured` and exits 0. A missing stream (404) reports `no_source`, never `ok`.
   - One `job_health` record per rule per run. One GitHub issue per firing rule while none is
     open (hidden marker, label `security-alert`); inert without `GITHUB_TOKEN`.
   - Optional paging: if `ALERT_WEBHOOK_URL` (from Secret `security-alert-webhook`, key `url`,
     optional) is set, POST `{"text": ..., "dedup_key": <rule>}` on every run in which a rule is
     firing, so a failed delivery is retried next run and the pager service dedupes on the key.
     A failed POST makes the run exit 1. Off by default; no URL is invented.
   - Both rules are always evaluated; the run then exits 1 if either errored or a delivery failed,
     so an `error` on one rule is never hidden by the other. `not_configured` is a status, not an error. So job-watchdog reports a dead evaluator.
2. Tests: `test_alerts.py` with network calls replaced, plus a CI workflow like
   `secret-rotation-test.yml`.
3. Factory docs: `docs/compliance/ir-tabletop.md` (scenario, inject schedule, roles, blank
   record template); link from `policies/incident-response.md` gap 3 and from the R-009 row's
   remaining-gap text. factory-gitops `docs/security-alerts.md` documents the rules, the
   OpenObserve Destination steps for routing existing `job_health` failures, and the open items.

## Alternatives rejected

- OpenObserve native alert rules: need a Destination (the missing pager) and are created via
  UI/API state that Argo CD does not manage; not reviewable or testable in git.
- Adding Prometheus/Alertmanager: the repo already decided against it for this gap
  (`docs/argocd-sync-honesty.md` "What was deliberately not done").
- Inventing an egress log schema or deploying the egress proxy: the proxy is the owner's
  rollout decision (`docs/egress-allowlist.md`, design only).

## Risks

- Auth-failure rows are only as complete as the `audit-siem-forward` feed; a stalled forwarder
  yields silent `ok`, and the forwarder caps a run at 10,000 rows, so a large backlog can push rows
  past the 30-minute window while the forwarder still reports success. Known limit, documented in
  `docs/security-alerts.md`; a forwarder-lag check is a follow-up, not in this slice.
- Threshold of 10 per 30 minutes is a first guess; tunable by env in the manifest.
- Issue opened in Factory: needs `GITHUB_TOKEN` from `factory-secrets`; absent means records only.

## Verification

`python3 apps/security-alerts/manifests/test_alerts.py` (thresholds, not_configured, 404, dedupe,
webhook off/on, exit codes); CI manifest-validate on the PR; `kubectl kustomize` renders.
The Factory docs are checked by the repo's docs lint if any.
