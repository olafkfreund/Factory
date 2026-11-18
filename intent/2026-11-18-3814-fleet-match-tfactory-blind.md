---
status: approved
issue: 3814
author: olafkfreund
---

# Intent: fleet-match reports a blind spot when one GitHub read blips

## Problem

Factory#3814 said `tfactory` "cannot be verified against main": the deploy-run
history for `olafkfreund/TFactory` "could not be read". The manifest and pods
already ran main's sha. Ten minutes later the next run matched and closed the
issue itself. The same single-run blind spot opened and closed for cfactory
(#3685, #3686, #3662), tfactory (#3660, #3618), aifactory and pfactory
(2026-10-22). Checked live on 2026-11-18: the TFactory `deploy.yml` runs read
fine (30 runs, newest a success on ea68416), so the workflow name, the token
scope and the branch filter are all correct. The most likely cause is a transient transport failure (parse errors also map to
`runs=None`, so this is a hypothesis until the log line below exists), and the
checker has no retry: one slow or failed GitHub call (timeout, 5xx, secondary
rate limit) becomes a warning issue. The error that caused it is logged as
`repr(e)` in a Job pod that is garbage-collected, so each time the cause is lost.

## Proposed outcome

- A transient GitHub read failure is retried a few times before the checker
  gives up.
- A read that still fails after the retries is still reported as "cannot
  verify" (a blind spot, never a pass).
- The log line for a failed read names the HTTP status and a short body, so the
  next occurrence is diagnosable.

## Affected users and systems

`apps/fleet-match` in factory-gitops (CronJob every 10 minutes, Python in a
ConfigMap). Issues are raised on olafkfreund/Factory.

## Constraints

- Keep "blind spot, not a pass": exhausted retries must still yield `unevaluable`.
- No token scope change is needed; nothing is owner-only.
- A retry must not push the 10-minute CronJob past its own period.
- Do not log the token or auth headers.

## Open questions

None. Decision (owner delegation 2026-11-18): retry in `gh()` rather than add
hysteresis (suppress the first blind cycle), because hysteresis would also delay
real blind spots and change what the alert means.
