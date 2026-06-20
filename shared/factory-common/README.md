# factory-common (deduped hub utility layer)

Single source of truth for small, stdlib-only cross-cutting primitives the
Factory fleet repeatedly re-implements. Established by the Phase-1 deduplication
work in the code-quality program (epic Factory#154, issue Factory#161).

## What lives here

| Module | Role |
| --- | --- |
| `factory_common/http.py` | Cloudflare-friendly typed urllib JSON client: Mozilla User-Agent, pluggable auth (bearer / basic / GitLab private-token), timeout, and a bounded retry on 5xx / network error. |
| `factory_common/secrets.py` | Canonical secret-pattern table plus `scan()` (leak detection) and `redact()` (safe logging). |

Both are **stdlib-only** so they import anywhere (CI, a coder pod, a one-off
script) with no third-party dependency, matching the rest of the deduped hub
layer (`shared/factory-github/`).

## Why these two

The June-2026 audit found the *same* two helpers about to be duplicated four
ways across the fleet:

- **The HTTP helper.** Every factory talks to authenticated APIs behind
  Cloudflare (the PARR services, GitHub/GitLab/Azure DevOps). The exact urllib
  request/parse/retry code — including the lesson that Cloudflare 403s the
  default `Python-urllib` User-Agent — was being re-written per caller.
- **The secret-scan/redaction table.** The audit's recurring credential-leak
  class (a token printed in argv, an error string, a log line) was being
  patched with an ad-hoc regex each time, so the pattern table itself was about
  to diverge.

## Proof of consumption (hub-internal)

The hub already duplicated the HTTP helper twice. Both copies now consume this
module, so the extraction is exercised, not just shipped:

- `scripts/parr_regression.py::_call` — the live-fleet seam probe (bearer auth).
- `scripts/sync_labels.py::_http_json` — the cross-tracker label sync (GitLab
  `PRIVATE-TOKEN` / Azure `Basic` auth).

Both refactors are **behaviour-preserving** and locked by
`tests/test_shared_http_consumption.py`.

## Usage

```python
from factory_common.http import HttpClient, bearer_auth
from factory_common.secrets import redact

client = HttpClient(base_url="https://api.example", auth=bearer_auth(token))
resp = client.get("/health")            # -> HttpResponse(status, json)

log.info(redact(f"calling with {token}"))   # -> "calling with ***REDACTED***"
```

## Consumption model

Like `shared/factory-github/`, this is the hub copy / source of truth. The hub's
own `scripts/` consume it directly via a `sys.path` insert (the hub's `scripts/`
is a flat dir, not an installed package). Publishing `factory-common` as an
installable package and having the four service repos consume it (replacing
their own copies) is a tracked cross-repo follow-on, deferred here because it is
a behaviour-affecting change across repos that deserves its own staged PRs.

## Tests

```
pytest shared/factory-common/tests/        # http + secrets unit tests
pytest tests/test_shared_http_consumption.py   # hub-consumer behaviour lock
```
