---
status: draft
issue: 3687
author: olafkfreund
---

# Intent: cred-broker raises the issue on the first rejected refresh

Scope: option 3 of Factory#3687 only. The owner has not chosen between option 1
(`claude setup-token`) and option 2 (re-seed reminder), so the credential flow,
the `factory-cli-creds` Secret and any re-seeding stay untouched. Code lands in
olafkfreund/factory-gitops; these artifacts live here because this repo owns the issue.

## Problem

In #3676 the first `refresh-rejected:invalid_grant` came at 2026-11-05 20:00Z with
under 4h of access token left. `invalid_grant` cannot succeed on retry, so that
run already knew everything. The alert only arrived 2026-11-06 00:30Z, because
job-watchdog waits for 2 failed runs and ~8.2h of staleness. The issue then
carried no cause and no fix steps, so the owner had to know to read the Secret
annotations. `docs/secrets-management.md` also uses `--context factory`, but the
cluster context is `k3d-factory`.

## Proposed outcome

- On the first refresh rejected with `invalid_grant` while the access token has
  30 days or less left (the case the broker already treats as an incident), a
  GitHub issue exists with `last-outcome`, `access-expires-at` and the exact
  re-seed steps in its body. The existing long-lived (`setup-token`) exemption
  stays: more than 30 days of runway still reports success and raises nothing.
- On any other failed refresh (HTTP error, network error) while
  `access-expires-at` is within N hours, or unknown, the same issue is raised.
- One open issue at a time: a failing run does not open a second one while the
  first is open (the CronJob retries three pods within seconds).
- The issue is the broker's own (own label and marker). It is not adopted by
  job-watchdog, whose recovery logic would close it after one failed run (the
  watchdog needs 2 failures or 8.25h staleness). The watchdog may later open its
  own staleness issue; the broker issue says so.
- The doc says `--context k3d-factory` (the one drifted doc named in the issue;
  other docs with the same flag are listed in the PR, not changed).

## Affected users and systems

factory-gitops `apps/cred-broker` (script + CronJob env), `docs/secrets-management.md`,
the owner (receives the issue). `factory-secrets/GITHUB_TOKEN` is read, not changed.

## Constraints

- Must not change the credential flow, touch `factory-cli-creds`, or re-seed.
- Must never print or put token material in the issue.
- Must stay inert (log only) when no GitHub token is available; alerting must
  never change the broker's exit code.
- cred-broker RBAC stays limited to the one Secret; the token comes from an
  optional `secretKeyRef`, so a missing key cannot stop rotation.
- job-watchdog is not changed.

## Open questions

- N hours: the token lives 8h and the broker runs every 4h, so a first failed run
  sees at most 4h left. Proposed N = 5 (env `ALERT_WITHIN_HOURS`), which alerts on
  the first failed run of a non-`invalid_grant` error. Approve or change.
