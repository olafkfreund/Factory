---
status: approved
issue: 3554
intent: intent/2026-10-14-3554-httpclient-read-timeout.md
---

# Spec: a read timeout crashes HttpClient callers instead of returning status 0

## Design

In `HttpClient.request` (`shared/factory-common/factory_common/http.py`,
around line 224), widen the network-failure clause from

    except urllib.error.URLError as exc:

to

    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:

The body stays the same: record `str(exc)`, back off, retry, and return
`HttpResponse(0, {"error": last_error})` after the last attempt.

- `TimeoutError` (the same class as `socket.timeout` since 3.10) is what
  `http.client` raises when the response read times out. That is the #3554 crash.
- `ConnectionError` covers a reset or broken pipe in the middle of a response,
  which escapes in the same way and is the same kind of transient failure.
- `HTTPError` subclasses `URLError` but is caught by the clause above it, so
  4xx and 5xx handling does not change.

Add one test to `shared/factory-common/tests/test_http.py`, next to
`test_network_error_returns_status_zero`. It uses the same fake transport, which
raises `TimeoutError("The read operation timed out")` and then
`ConnectionResetError`, and asserts `status == 0`, two attempts, and the error
text in `resp.json["error"]`.

`parr_regression.py` needs no change. It already treats status 0 as a failed seam.

Decisions on the intent's open questions:

- **Vendored copies.** PFactory (`apps/web-server/factory_common/http.py`),
  TFactory (same path) and CFactory (`apps/backend/factory_common/http.py`)
  carry hand-edited copies with no drift gate. This change fixes the hub only.
  One follow-up issue per repo asks for the same one-line change. Re-vendoring
  is out of scope.
- **Closing #3554.** Close it when the PR merges. If the nightly fails again, it
  opens a new issue.

## Alternatives rejected

- **Catch `OSError`**, as `gate_evidence.py` does. That is too broad for a
  shared client: it would also turn local faults, such as an SSL configuration
  error or a bad file descriptor, into "status 0, try again later".
- **Catch the timeout in `parr_regression._call`.** That fixes one caller of six
  and leaves the client's documented contract broken.
- **Raise the 20s timeout for the CFactory seam.** The run would still crash on
  the next slow response, and it hides a real latency signal.

## Risks

- A caller that relied on `TimeoutError` escaping would now get status 0
  instead. The 3 non-test `HttpClient` users (`parr_regression.py`, `sync_labels.py`,
  `benchmarks/run_pipeline_task.py`; the intent's count of 6 included a stale
  `.claude/worktrees` copy) have no handler catching
  it around an `HttpClient` call.
- Worst-case latency rises to 3 attempts × the timeout plus backoff, as it
  already does for connect failures. For the CFactory seam that is about 75s,
  within the job's limits.
- No host or deploy is affected.

## Verification

- `pytest shared/factory-common/tests/test_http.py`: the new test fails before
  the change (TimeoutError escapes) and passes after it. All existing tests pass.
- The repo's lint and type checks pass on the two files.
- After merge, the next PARR nightly run either passes or reports a slow
  CFactory as a failed seam with an error, never a traceback.
