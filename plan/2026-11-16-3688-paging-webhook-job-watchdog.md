---
status: approved
issue: 3688
spec: spec/2026-11-16-3688-paging-webhook-job-watchdog.md
coders:   # every file-editing step is done by the lead: small, security-sensitive edits where a handoff costs more than it saves
  all: lead
reviewers:
  - codex   # independent read-only review of the diff (agy is off by owner decision)
---

# Plan: Page critical job-watchdog findings through the optional webhook

Decisions carried over from the approved spec:

`job-watchdog`'s `notify()` already decides one action per record: open, reopen, escalate, renotify, close. After the action, a new `page()` POSTs `{"text", "dedup_key"}` (the issue marker as key) when the severity is critical and the action is open, reopen, escalate or renotify. `ALERT_WEBHOOK_URL` comes from the optional Secret. `page()` also fires on every later run while a critical issue stays open, with the same `dedup_key`, so a failed POST is retried by the next run without extra state (the pager must de-duplicate by `dedup_key`, the same contract as `security-alerts`). `page()` never raises and never prints the URL or exception text; a failure is appended to `PAGE_FAILS` and `main()` returns 7 after the heartbeat, so the heartbeat still proves the watchdog ran while the CronJob goes red.

## Steps

1. factory-gitops `apps/job-watchdog/manifests/manifests.yaml`: add `PAGE_FAILS`, `page()`, the call in `notify()`, exit 7 in `main()`, selftest block, and the `ALERT_WEBHOOK_URL` optional secretKeyRef env. The selftest must include a two-run case: the first POST fails (counted in `PAGE_FAILS`, URL never printed), the next run with the unchanged open critical finding POSTs again with the same `dedup_key`; and a mutation check (removing the quiet-run `page()` call fails the selftest). `main()` returns 7 after the heartbeat when `PAGE_FAILS` is non-empty (read check; the heartbeat call precedes it). Check: extract the script and run `selftest`.
   Traps: the script is a block scalar in a ConfigMap; no `str(exception)` of a request (it can contain the URL).
2. factory-gitops `docs/security-alerts.md`, `docs/job-health-watchdog.md`: replace the "create an OpenObserve alert in the UI" step with the webhook behaviour. Check: read.
3. Owner (not an agent step): create the Secret, run the tabletop, file the record.

## Tests

`python3 .github/scripts/extract_embedded_script.py apps/job-watchdog/manifests/manifests.yaml watchdog.py /tmp/wd.py && python3 /tmp/wd.py selftest` prints `selftest OK`.

## Rollback

Revert the commit; the Secret is optional, so the env var disappears with it.
