---
status: approved
issue: 3554
spec: spec/2026-10-14-3554-httpclient-read-timeout.md
---

# Plan: a read timeout crashes HttpClient callers instead of returning status 0

## Approved decisions (carried from the spec)

- `HttpClient.request` treats `TimeoutError` and `ConnectionError` as network
  failures, the same as `urllib.error.URLError`: retry with the existing backoff,
  then return `HttpResponse(0, {"error": str(exc)})`. No new options, and 4xx/5xx
  (`HTTPError`) handling does not change.
- Do not catch bare `OSError`. It is too broad for a shared client.
- Fix the hub only. PFactory, TFactory and CFactory each get a follow-up issue
  for their vendored copy.
- `parr_regression.py` does not change. It already treats status 0 as a failed seam.
- #3554 closes when the PR merges.

## Steps

1. `shared/factory-common/tests/test_http.py`: add one test after
   `test_network_error_returns_status_zero` (currently around line 154):

   ```python
   def test_read_timeout_and_reset_return_status_zero(monkeypatch: pytest.MonkeyPatch) -> None:
       transport = _Transport(
           [TimeoutError("The read operation timed out"), ConnectionResetError("reset")]
       )
       _install(monkeypatch, transport)
       client = http.HttpClient(base_url="http://t", max_attempts=2, _sleep=lambda _s: None)
       resp = client.get("/slow")
       assert resp.status == 0
       assert len(transport.requests) == 2
       assert "reset" in resp.json["error"]
   ```

   → verify by `uvx --with pytest pytest -q shared/factory-common/tests/test_http.py`:
   the new test FAILS with an escaping `TimeoutError` and the other 19 pass.
   Traps: use the existing `_Transport`/`_install` helpers, not a new fake. No
   real network. `last_error` holds the last exception, so assert "reset", not
   "timed out".

2. `shared/factory-common/factory_common/http.py:224`: change
   `except urllib.error.URLError as exc:` to
   `except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:`.
   Leave the body unchanged. Add one comment line above it giving the reason:
   a timeout while reading the response is raised bare, not wrapped in
   `URLError` (#3554).
   → verify by the same pytest command: 20 passed.
   Traps: the `HTTPError` clause must stay above this one (`HTTPError`
   subclasses `URLError`). Do not touch the docstring contract, which already
   promises status 0 on a network failure.

3. Open three follow-up issues, one each in olafkfreund/PFactory
   (`apps/web-server/factory_common/http.py`), olafkfreund/TFactory (same path)
   and olafkfreund/CFactory (`apps/backend/factory_common/http.py`), linking
   this PR and asking for the same one-line change.
   → verify by `gh issue view` on each.
   Traps: none. The session does this; it is not a coder step.

## Tests

```bash
uvx --with pytest pytest -q shared/factory-common/tests/test_http.py   # 20 passed
ruff check --config standards/ruff.toml shared/factory-common
ruff format --check shared/factory-common
```

CI: `contracts.yml` runs `shared/factory-common/tests/`.

## Rollback

Revert the squash-merge commit. Nothing is deployed, and no data or config
changes.

## Execution

Step 1 is handed to agy and step 2 to Codex, as the user asked. A fresh Opus
agent reviews the result against this plan and `git diff`.

Deviation: agy did step 1. The Codex handoff for step 2 stalled for about 12
minutes without editing a file, so the session stopped it and made the step 2
change itself, exactly as written above.
