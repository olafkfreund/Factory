---
status: draft
issue: 1959
intent: intent/2026-11-18-1959-gateway-features.md
---

# Spec: gateway quota, spend attribution, failover and telemetry

## Design

All in `apps/model-gateway/gateway.py` (AIFactory), stdlib only, one file (the image
stage copies one file; the Dockerfile also copies the vendored catalog
`apps/backend/core/model-catalog.json` to `/app/model-catalog.json`).

**Config.** New env, all default off: `GATEWAY_METRICS=on` (accounting plus
`/metrics`), `GATEWAY_CATALOG_PATH` (default `model-catalog.json` beside the script,
price source; missing file means cost 0), `GATEWAY_COOLDOWN_S` (default 30),
`GATEWAY_OTLP_ENDPOINT` and `GATEWAY_OTLP_HEADERS` (telemetry off when unset). Routes
file: a class value may stay a string, or become an object
`{"model": id, "quota": {"window_s": 60, "requests": n, "tokens": n},
"upstreams": [{"url", "key_env", "model"}]}`. `key_env` names an env var; no key is
ever in the ConfigMap. The file is re-read per request, so every field is hot-reload.

**Quota.** Fixed window per class route (state survives reloads, window length read
from config). Admission increments the request count; over the request or token limit
answers 429 `{"error":"route quota exceeded"}` with `Retry-After` (seconds to window
end, minimum 1). Tokens are added after the response from upstream usage. Decisions:
concrete-model (non-class) requests are metered but exempt from quota; concurrent
in-flight requests may overshoot a token limit by their own size; missing usage adds
zero tokens and increments `gateway_usage_missing_total`.

**Accounting.** Token usage is read from the buffered body: JSON `usage`, or the last
`usage` in an SSE stream (when metrics are on and the request streams, the gateway adds
`stream_options.include_usage` if absent). Cost = tokens times catalog `price`
(`metered` only). Counters, Prometheus text on `GET /metrics` (404 unless enabled,
bearer-authenticated): `gateway_requests_total{route,service,outcome}`,
`gateway_tokens_total{route,service,kind}`, `gateway_cost_usd_total{route,service}`,
`gateway_failovers_total{route}`, `gateway_usage_missing_total{route}`,
`gateway_upstream_up{upstream}`. Route is the class or `direct`. Service is the
self-declared `X-Caller-Service` header (`[a-z0-9._-]{1,64}`, else `unknown`; at most
32 distinct values, the rest `other`): attribution is advisory because all callers
share one client token. `python gateway.py --self-test` runs a loopback fake upstream
through the gateway and exits non-zero unless the scraped counters are non-zero; this
is the "assert non-zero count" check for AC-3.

**Failover.** Per route an ordered upstream list; the default list is the single
`GATEWAY_UPSTREAM_URL`. An attempt fails over on 5xx, timeout or connection error,
never on 4xx. A failed upstream is cooled down for `GATEWAY_COOLDOWN_S`; ordering puts
healthy upstreams first in configured order, cooled ones last. After the cooldown the
primary is first again and the next real request is the recovery probe (success marks
it up, failure restarts the cooldown); there is no background prober. The last
attempt's response is returned as today (5xx passthrough, 502 when unreachable). A
failover adds `X-Model-Failover-From: <host>`. Duplicate execution after a timeout is
accepted; only the answering attempt is accounted.

**Telemetry.** One span per request, exported by a stdlib OTLP/HTTP JSON client on a
bounded queue and a daemon thread (drops when full, swallows errors). Attributes:
`factory.genai.{route,caller_service,resolved_model,provider,prompt_tokens,
completion_tokens,cost_usd,latency_ms,outcome,failover_from}` and `gen_ai.{operation.name,
request.model,response.model,usage.input_tokens,usage.output_tokens}`. No prompt or
completion text is read into a span or a log; there is no logging knob at all.

## Alternatives rejected

- `opentelemetry-sdk`: a dependency tree in a stdlib-only signed image.
- Background health prober: more threads for no gain while traffic is the probe.
- True streaming: out of scope, buffering stays; failover after bytes reached the
  caller would otherwise need a rule.
- Authenticated per-service tokens: a secret-minting step that is the owner's.
- Quota on concrete models: would need a quota key per model id.

## Risks

Quota and counters are per pod and in memory (two replicas double the effective quota,
counters reset on restart); fixed windows allow a burst at a boundary; self-declared
service labels can be spoofed by a holder of the client token; the OTLP JSON format must
be accepted by OpenObserve (unverified live). All inert until the owner sets config.

## Verification

`pytest tests/model_gateway` with fake upstreams: quota 429 and Retry-After and window
reset (fake clock), hot reload of a quota, token quota; usage and cost from JSON and SSE,
`/metrics` text, self-test; failover on 5xx, timeout and connection error, no failover on
4xx, recover after cooldown, both directions; OTLP span to a fake collector; unchanged
behaviour with no new config (existing tests); `ruff check`. Live proof (pod UID, live
failover, keys removed) stays with the owner.
