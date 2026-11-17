---
status: approved
issue: 3688
author: olafkfreund
---

# Intent: Page critical job-watchdog findings through the optional webhook

## Problem

R-009 (detection and response) still has no paging destination. The parts an agent can build are done: `security-alerts` (auth-failure and egress rules, factory-gitops#345) can POST to an optional webhook Secret, and the IR tabletop template is `docs/compliance/ir-tabletop.md`. But `job-watchdog`, which raises every `job_health` failure (failed or silent CronJobs, Argo stalls, killed pods), reaches a human only through a GitHub issue. The issue asks that `job_health` failures be routed to the paging destination.

## Proposed outcome

- Critical `job-watchdog` findings also POST to the same optional webhook (Secret `security-alert-webhook`, key `url`) used by `security-alerts`. Off while the Secret does not exist.
- A dead pager is visible: a failed POST turns the CronJob red.
- Recorded decision: the destination type is the path the fleet already has (a GitHub issue per finding, via `job-watchdog`) plus one generic JSON webhook. No Slack, SMTP, ntfy or Matrix endpoint exists in gitops, so none is invented.

## Affected users and systems

factory-gitops `apps/job-watchdog` (CronJob in `factory`), `docs/security-alerts.md`, `docs/job-health-watchdog.md`. The owner supplies the webhook URL.

## Constraints

Default off. No URL or token in git, never printed. GitHub issues stay the primary channel. One POST per critical state change, not per run. Warnings and recovery are not paged.

## Open questions

None for the agent. Owner actions: who is paged and by which channel, the webhook URL Secret (`kubectl -n factory create secret generic security-alert-webhook --from-file=url=<file>`), egress for an external URL, and running the tabletop.
