---
status: approved
issue: 3687
author: olafkfreund
---

# Intent: setup-token as the default Claude credential flow

Follow-up to the approved early-alert work (`intent/2026-11-16-3687-cred-broker-early-alert.md`).
Code lands in olafkfreund/factory-gitops; artifacts live here because this repo owns the issue.

## Problem

The root cause of #3676/#3687 is now confirmed: a `claude auth login` refresh-token
lineage has a fixed lifetime (about 30 days) from the interactive login, and rotation
does not extend it. The live Secret's `claudeAiOauth.refreshTokenExpiresAt` was
2026-11-05T17:14:31Z, between the last good refresh (16:00Z) and the first
`invalid_grant` (20:00Z); the login was about 2026-10-06. The issue's "about 14 days
from the Secret's creation" is wrong, and three of the five incidents were cluster
rebuilds or outages, not expiries. Yet `docs/secrets-management.md` still says to
re-seed with `claude auth login`, `apps/cred-broker/application.yaml` says "no human
re-login is needed while the broker runs", and the broker never reads
`refreshTokenExpiresAt`, so the next expiry would again arrive without warning.

## Proposed outcome

- The doc makes `claude setup-token` (about 1 year, no refresh token) the default flow
  and gives the owner procedure end to end; `auth login` stays as the documented
  alternative with its roughly 30-day re-login.
- For a refreshable credential the broker reads `refreshTokenExpiresAt` and raises the
  existing early-alert issue when it is within 7 days or already past, with the date in
  the body.
- The wrong comment in `application.yaml` is corrected.
- Factory#3687 carries the corrected cause.

## Affected users and systems

The owner (re-seeding), cred-broker CronJob, `factory-cli-creds` and `factory-secrets`
(read only here), AIFactory/PFactory/TFactory consumers.

## Constraints

- Never read or print secret values; do not touch live Secrets or re-seed: that is the
  owner's job. No cluster changes.
- Subscription login only, never an API key.
- The broker's `not-applicable:long-lived-credential` handling of a setup-token stays.

## Open questions

None. The owner has chosen setup-token.
