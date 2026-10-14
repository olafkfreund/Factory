---
status: draft
issue: 3554
author: olafkfreund
---

# Intent: a read timeout crashes HttpClient callers instead of returning status 0

## Problem

The 2026-10-13 PARR nightly regression (#3554, run 38341463267) did not find a
regressed seam. `scripts/parr_regression.py` crashed: CFactory accepted the
connection for `check_cfactory_threading`, then did not answer within 20s, and
`http.client` raised `TimeoutError: The read operation timed out`.

`HttpClient.request` (`shared/factory-common/factory_common/http.py`) says it
retries network errors and returns status 0 when they persist. It only catches
`urllib.error.URLError`. A timeout during the connect phase is wrapped in a
`URLError`, but a timeout while reading the response is not, so it skips the
retry and escapes to the caller. The run died with a traceback, the seams after
CFactory never ran, and the issue title blamed a cross-service boundary.

The 10-12 and 10-14 runs passed, so the trigger was one slow CFactory response.
The defect is that one slow response turns into a crash.

## Proposed outcome

A read timeout, or a connection reset mid-response, is retried like any other
network failure. If it persists, `HttpClient` returns `HttpResponse(0, {"error": ...})`.
The regression then reports that seam as failed with the error and still runs
every other seam.

## Affected users and systems

- `shared/factory-common` `HttpClient`, used by 6 non-test modules here,
  including `parr_regression.py`.
- The PARR nightly regression and the issues it opens.
- No host, cluster or deploy change.

## Constraints

- Keep the `(status, json)` contract and the existing retry and backoff policy.
  No new options.
- Must not swallow `HTTPError`. 4xx and 5xx handling stays as it is.
- Two other scripts already catch `(URLError, TimeoutError, OSError)` themselves
  (`gate_evidence.py:112`, `check_cli_freshness.py:157`). Fixing this once in
  the shared client is the root-cause fix.

## Open questions

- Is `factory_common` vendored into other repos (AIFactory, PFactory)? If so,
  do they need the same fix re-vendored, or is that follow-up work?
- Should #3554 stay open until a nightly run passes on the fix, or close when
  the PR merges?
