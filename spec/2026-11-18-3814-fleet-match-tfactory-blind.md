---
status: draft
issue: 3814
intent: intent/2026-11-18-3814-fleet-match-tfactory-blind.md
---

# Spec: retry transient GitHub reads in fleet-match

## Design

In `apps/fleet-match/manifests/manifests.yaml` (embedded `match.py`), make
`gh()` retry GET requests only, up to 3 attempts with 2s then 5s waits, on
`URLError`/timeout and HTTP 5xx, 429, and 403 with a rate-limit signal
(`retry-after` header or `x-ratelimit-remaining: 0`). Other 4xx (404, 401,
real 403) fail at once. POST/PATCH are never retried (issue creation is not
idempotent). Worst case added per call is 7s; the job takes ~20s to 90s against
a 600s period.

When a read finally fails, `repo_state()` logs `HTTP <code> <body[:200]>` so
the cause survives in the log. `runs=None` still maps to `unevaluable`.

Selftest additions: (1) a fake `urlopen` that fails twice with 502 then
succeeds returns the data; (2) a persistent 404 is not retried and raises;
(3) `assess(..., runs=None, ...)` for a repo target gives `["unevaluable"]`
and never `matches_main`.

## Alternatives rejected

- Hysteresis (open an issue only after 2 blind cycles): delays real blind spots
  and changes alert semantics.
- Different workflow name, token scope or branch filter: live read of TFactory
  deploy.yml works with the same filters.
- Raising the 30s timeout alone: does not help 5xx or rate limits.

## Risks

A retry storm during a GitHub outage: bounded (3 attempts, ~25 calls per run).
Slower job: bounded as above.

## Verification

`python3 .github/scripts/extract_embedded_script.py apps/fleet-match/manifests/manifests.yaml match.py /tmp/fm.py && python3 /tmp/fm.py selftest`; manifest-validate workflow;
after merge, the next CronJob logs show `MATCHED`/ok for tfactory (read-only
`kubectl logs`).
