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

- On the first refresh rejected with `invalid_grant`, a GitHub issue exists with
  `last-outcome`, `access-expires-at` and the exact re-seed steps in its body.
- On any other failing refresh while `access-expires-at` is within N hours, the
  same issue is raised.
- No duplicate issues; the job-watchdog adopts the same issue.
- The doc says `--context k3d-factory`.

## Affected users and systems

factory-gitops `apps/cred-broker` (script + CronJob env), `docs/secrets-management.md`,
the owner (receives the issue). `factory-secrets/GITHUB_TOKEN` is read, not changed.

## Constraints

- Must not change the credential flow, touch `factory-cli-creds`, or re-seed.
- Must never print or put token material in the issue.
- Must stay inert (log only) when no GitHub token is available; alerting must
  never change the broker's exit code.
- cred-broker RBAC stays limited to the one Secret.

## Open questions

- N hours: proposed 12 (two failed 4h runs of margin on an 8h token). Approve or change.
