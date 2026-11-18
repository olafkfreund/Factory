---
status: draft
issue: 1959
intent: intent/2026-11-18-1959-gateway-gitops-wiring.md
---

# Spec: wire the 3.17.0 gateway features into factory-gitops, all off

Repo factory-gitops (base `main`), branch `feat/1959-gateway-gitops-wiring`. Decisions are taken under the owner
delegation of 2026-11-18 and will be recorded on Factory#1959 as "Decision (owner delegation 2026-11-18)".

## Design

1. **Image.** `apps/model-gateway/manifests/manifests.yaml`: `sha-24184c6-gateway` to `sha-800eb3e-gateway`. 800eb3e is
   the dev commit tagged v3.17.0 and contains AIFactory#2138 (60928367). Same CD-built, deploy.yml-signed tag shape as
   today's (a `v3.17.0-gateway` tag exists but is signed by release.yml and has a different digest; the Kyverno policy
   and the earlier bump use the immutable `sha-<short>-gateway` tag). Read-only check done: `cosign verify` with
   identity `.../AIFactory/.github/workflows/deploy.yml@refs/heads/main` passes for the new tag. Rolls the 2 pods once.
2. **Deployment env, all off or optional.**
   - `GATEWAY_METRICS` literal `"off"` (the gateway enables only on `on|1|true`).
   - `GATEWAY_OTLP_ENDPOINT` and `GATEWAY_OTLP_HEADERS`: `secretKeyRef` `model-gateway-secrets`, same-named keys,
     `optional: true`. Unset means no exporter thread. The endpoint is in the Secret rather than a literal because a
     literal would turn the exporter on; the Secret already holds the gateway token, so its editor gains nothing new.
   - `GATEWAY_UPSTREAM2_API_KEY`: optional `secretKeyRef` for a failover upstream; used only if a route's `upstreams`
     names it in `key_env`.
   - `GATEWAY_COOLDOWN_S` left at the gateway default (30).
3. **Routes.** `scripts/gen-model-routes.py` reads an optional `apps/model-gateway/route-policy.json`
   (`{class: {"quota": {...}, "upstreams": [{"url", "key_env", "model"?}, ...]}}`, committed as `{}`). For a class
   with a policy the route becomes the object form `{model, quota?, upstreams?}` that `gateway.py` already parses;
   other classes stay strings, so with `{}` the rendered ConfigMap is byte-identical to today (the CI drift check
   proves it). The generator validates what the gateway validates (known class, positive quota numbers, http(s) upstream
   URL, non-empty strings) plus: `key_env` must be exactly `GATEWAY_UPSTREAM_API_KEY` or `GATEWAY_UPSTREAM2_API_KEY`, the two names the Deployment
   defines, so a policy can never name an arbitrary env var (`PATH`, a provider key, an undefined name that the gateway
   would silently read as an empty key).
   `upstreams` order is failover order; first is primary. A class with `quota` but no upstreams uses the
   `GATEWAY_UPSTREAM_URL` upstream.
4. **Network.** New NetworkPolicy `allow-otlp-egress` in `gateway`: egress from `app=model-gateway` to namespace
   `factory`, pods `app=observe`, TCP 5080 only. Needed because `allow-provider-egress` excludes 10.0.0.0/8, so the
   in-cluster OpenObserve is otherwise unreachable. Additive; inert until an endpoint is set. Ingress is unchanged:
   `/metrics` is reached with `kubectl port-forward`, no scraper exists.
5. **Activation needs a restart.** Secret-backed env is read at container start. After seeding or changing
   `GATEWAY_OTLP_*` or `GATEWAY_UPSTREAM2_API_KEY`, or flipping `GATEWAY_METRICS`, the owner runs
   `kubectl -n gateway rollout restart deploy/model-gateway` (the doc says so). Route policy changes hot-reload, no restart.
6. **Metrics access, no ServiceMonitor.** The cluster has no Prometheus Operator CRDs (read-only `get crd`), so a
   ServiceMonitor would fail Argo and kubeconform. docs/model-gateway.md gets a documented check: port-forward each
   pod, `curl -H "Authorization: Bearer $(cat TOKENFILE)"` from a token file the owner supplies, read the counters and
   sum them over pods.
7. **OpenObserve OTLP (read-only finding, recorded in the doc).** From the v0.90.3 source (the version pinned in
   `apps/observe`): `POST /api/{org}/v1/traces` accepts `Content-Type: application/json` (`traces::otlp_json`, parsed
   as an OTLP `ExportTraceServiceRequest`) and `application/x-protobuf`; auth is Basic. The gateway posts JSON to
   `<endpoint>/v1/traces` and sets that content type, so the endpoint to seed is
   `http://observe.factory.svc.cluster.local:5080/api/default` and `GATEWAY_OTLP_HEADERS` is
   `Authorization=Basic <base64 user:password>`. OpenObserve's usage extractor reads `gen_ai.usage.input_tokens` and
   `output_tokens`, which the gateway sets. This is source evidence only: acceptance is **unverified live** (posting a
   span writes to OpenObserve and needs credentials, so it is an owner step after seeding). No exporter change is
   indicated, so no AIFactory issue is filed; if the live check fails, the doc says to file one.
8. **Per pod, and AC-3.** Quota windows and counters live in each pod's memory (2 replicas, no session affinity,
   restart resets them). A request quota is enforced per pod, so the fleet total is up to 2x the configured limit; set
   the per-pod limit to half the intended total. A token quota is only an admission threshold: tokens are charged after a
   response completes, so concurrent requests can overshoot it by more than 2x. It is not a fleet cap. AC-3 (grouped cost over a PARR run) must sum `/metrics` from both pods before and after the run, and
   a pod restart during the run invalidates the proof. The sum is spend evidence only if `GATEWAY_METRICS` is on, the
   exercised models are priced in the catalog, and neither `gateway_usage_missing_total` nor `gateway_unpriced_total`
   rose during the run (both add zero cost silently). Written into docs/model-gateway.md.
9. **Cluster-free guard.** Extend `scripts/test-gateway-wiring.sh` (already run by `model-gateway-tools.yml`) to render
   `apps/model-gateway/manifests` and fail when: `GATEWAY_METRICS` is not literal `off`; an OTLP or upstream-key env is
   not an optional `model-gateway-secrets` ref or has a literal value; any route in `model-routes` has `quota` or
   `upstreams` (default must be strings only); a `key_env` named in a route is not a defined optional env;
   `allow-otlp-egress` is not exactly observe:5080/TCP. Each rule has a negative mutation test. The generator test adds a positive fixture (quota plus two ordered upstreams
   emitted as the object form, primary first) and rejections (malformed or non-positive quota, non-http URL, `key_env`
   outside the two names including a regex-like `GATEWAY_UPSTREAM99_API_KEY`, unknown class), so a generator that
   ignores policy fails.

## Alternatives rejected

- ServiceMonitor or PodMonitor: no CRD in the cluster.
- Literal `GATEWAY_METRICS: "on"` now: not off by default; the owner flips it in a PR after the Secret exists.
- A new ConfigMap for quota and upstreams: the gateway reads one routes file, and #375 already generates it.
- `key_env` free-form: lets a policy make the gateway read any env var as an upstream key.
- Filing an AIFactory exporter issue now: source shows JSON is accepted; without a live failure it would be noise.
- Shared quota or counters across pods (Redis, sidecar): out of scope and a larger change; documented as a limit.

## Risks

- Image bump rolls both gateway pods once (no traffic today: no Secret, chat answers 503). Rollback is a revert.
- The 3.17.0 image reads the routes file with object entries; existing string entries are the legacy form it still
  accepts (AIFactory#2138 tests).
- `allow-otlp-egress` widens egress from the gateway to one pod label in `factory`; any pod labelled `app=observe`
  there is reachable. Accepted: `factory` is the owner's namespace, and the port is OpenObserve's.
- OTLP acceptance unverified live (above).

## Verification

`bash scripts/test-gen-model-routes.sh` and `bash scripts/test-gateway-wiring.sh` pass, including the new mutations;
the drift check against the pinned catalog passes with the unchanged ConfigMap; `kustomize build
apps/model-gateway/manifests` is valid; shellcheck clean; PR checks (manifest-validate, kubeconform, gitleaks,
model-gateway-tools) green on the head SHA. Read-only live: `kubectl get` confirms the 2 pods Running on the new image
only after the coordinator merges, which is outside this PR.
