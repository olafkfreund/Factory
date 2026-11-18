---
status: draft
issue: 1959
spec: spec/2026-11-18-1959-gateway-features.md
coders:
  2: codex   # contained, self-contained exporter class plus its tests (small tricky logic)
  # steps 1 and 3: lead (cross-cutting do_POST rewrite; Dockerfile and docs)
reviewers:
  - codex    # read-only review of each draft and of the final diff
---

# Plan: gateway quota, spend attribution, failover and telemetry

Approved decisions (spec): all in AIFactory `apps/model-gateway/gateway.py`, stdlib only,
default off. Env: `GATEWAY_METRICS=on`, `GATEWAY_CATALOG_PATH` (default
`model-catalog.json` beside the script), `GATEWAY_COOLDOWN_S` (30), `GATEWAY_OTLP_ENDPOINT`,
`GATEWAY_OTLP_HEADERS`. Routes file value: string (as today) or object
`{model, quota:{window_s,requests,tokens}, upstreams:[{url,key_env,model}]}`, validated as a
whole; an invalid reload keeps the last valid config; none ever valid means today's
behaviour. One lock for quota/counters/labels/health, never held across upstream I/O.
Quota: fixed window per class route, 429 `route quota exceeded` plus `Retry-After`;
concrete models exempt but metered; tokens charged at completion; missing usage counts
`gateway_usage_missing_total`. Usage from buffered JSON or SSE (add
`stream_options.include_usage` when metrics on and streaming); cost from catalog `metered`
price, else `gateway_unpriced_total`. `/metrics` (404 off, bearer auth): requests,
tokens, cost_usd, failovers, usage_missing, unpriced, `gateway_upstream_up{host[:port]}`.
Service label from `X-Caller-Service` (`[a-z0-9._-]{1,64}` else `unknown`, 32 distinct then
`other`). Failover on 5xx/timeout/connection error (not 4xx), cooldown, next request is the
probe, per-entry `key_env` (global key only to the default upstream),
`X-Model-Failover-From`. Telemetry: stdlib OTLP/HTTP JSON, queue plus daemon thread,
no-redirect opener, `factory.genai.*` and `gen_ai.*`, no prompt text, no logging knob.
Also: a changed `window_s` starts a new window; tokens go to the window current at
completion; only the answering attempt is accounted; upstream gauge series exist only for
upstreams in the current valid config; the self-test needs request, token and cost counters
all non-zero against a priced fake model. `--self-test`. Keep the CR/LF header strip and the no-redirect opener.

Worktree: AIFactory, branch `feat/1959-gateway-features` off `origin/dev`. Run
`python -m pytest tests/model_gateway -q` and `ruff check apps/model-gateway tests/model_gateway`
plus `ruff format --check` on the same paths.

## Steps

1. `apps/model-gateway/gateway.py`, `tests/model_gateway/test_gateway_features.py` (lead):
   config fields, `_load_routes` validation and last-valid cache, `_State` (lock, quota,
   counters, labels, health), usage/cost extraction, `/metrics`, multi-upstream failover loop
   in `do_POST`, `--self-test`, and a no-op `_Telemetry` with `emit(attrs, start_ns, end_ns,
ok)` called once per request, built as `_Telemetry(endpoint, headers_str)` in `make_server`
   (disabled and no thread when endpoint is empty; thread starts at construction). Attrs dict
   passed to `emit`: keys exactly `factory.genai.route|caller_service|resolved_model|provider|
   prompt_tokens|completion_tokens|cost_usd|latency_ms|outcome|failover_from` and
   `gen_ai.operation.name|request.model|response.model|usage.input_tokens|usage.output_tokens`
   (omit absent values). Tests in step 1: concurrent admission never exceeds the limit,
   invalid reload keeps last valid quota, fake-clock rollover and `window_s` change,
   Retry-After, request+token quota, JSON and SSE usage, cost and unpriced, `/metrics`,
   self-test, label caps, each failover trigger (5xx, timeout, connection error), no retry on
   4xx, fail-over then recover after cooldown (fake clock), key not sent to another host,
   unchanged behaviour with no new config. → `pytest tests/model_gateway -q` (old tests unchanged).
   Traps: ruff "as" alias rule (plain names); never log keys or bodies; CR/LF strip on new
   headers; upstream I/O outside the lock.
2. `apps/model-gateway/gateway.py` (`_Telemetry` only), `tests/model_gateway/test_telemetry.py`
   (codex): implement `_Telemetry` per spec (OTLP JSON `/v1/traces`, headers from
   `GATEWAY_OTLP_HEADERS` as `k=v,k2=v2`, bounded queue, daemon thread, no-redirect opener,
   drop on full, swallow errors, attribute types) and test it against a fake collector, also
   that a redirect is not followed. Touch nothing else. Lead adds the gateway-request integration test (one populated span reaches a fake collector) after review. → pytest and ruff as above.
3. `Dockerfile` gateway stage: `COPY --chmod=0644 apps/backend/core/model-catalog.json
   /app/model-catalog.json`; docstring of gateway.py lists the new env; `CHANGELOG.md` line
   (lead). → `docker` not run; check `git diff`, and that `.dockerignore` does not exclude it.

## Tests

`pytest tests/model_gateway -q` all green; `python apps/model-gateway/gateway.py --self-test`
exit 0; ruff clean. Existing tests must pass unmodified.

## Rollback

Revert the PR and roll the image back together. Before rolling the image back, restore any object route values in `model-routes` to plain strings (the old image forwards the class name unresolved for object values) and drop quota/upstreams.
