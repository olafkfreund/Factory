---
status: draft
issue: 3688
intent: intent/2026-11-16-3688-paging-webhook-job-watchdog.md
---

# Spec: Page critical job-watchdog findings through the optional webhook

## Design

`job-watchdog`'s `notify()` already decides one action per record: open, reopen, escalate, renotify, close. After the action, a new `page()` POSTs `{"text", "dedup_key"}` (the issue marker as key) when the severity is critical and the action is open, reopen, escalate or renotify. `ALERT_WEBHOOK_URL` comes from the optional Secret. `page()` also fires on every later run while a critical issue stays open, with the same `dedup_key`, so a failed POST is retried by the next run without extra state (the pager must de-duplicate by `dedup_key`, the same contract as `security-alerts`). `page()` never raises and never prints the URL or exception text; a failure is appended to `PAGE_FAILS` and `main()` returns 7 after the heartbeat, so the heartbeat still proves the watchdog ran while the CronJob goes red.

## Alternatives rejected

- OpenObserve Alert plus Destination: imperative API state that lives outside git (the reason `job-watchdog` was built, per its header).
- Paging once per state change only: a failed POST would then be lost until the 24 h renotify, since the issue already exists. Paging only critical findings, every run while open, with a stable `dedup_key`, is retried for free.
- Persisting a pending-page marker (label or ConfigMap): more state for a problem the stable key already solves.
- A new Slack/ntfy/Matrix integration: no such endpoint exists in the fleet, and a placeholder that drops messages is the original defect.
- Paging warnings: noise; the severity split exists for this.

## Risks

A webhook that accepts but drops messages is invisible: the owner should test it once. A pager that does not de-duplicate on `dedup_key` repeats every 30 minutes per critical finding. An external URL needs `factory` egress (documented). Exit 7 makes `job-watchdog` fail its own check when the pager is down, which is intended.

## Verification

The embedded selftest (`python3 .github/scripts/extract_embedded_script.py ...; selftest`, CI `job-watchdog selftest`) covers: no URL means no POST, a POST for a critical open with the marker as `dedup_key`, again on the next run while it stays open, none for a warning or a healthy fleet, and a failing POST is counted without printing the URL and then succeeds on the next run.
