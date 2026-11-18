---
status: draft
issue: 1959
spec: spec/2026-11-18-1959-gateway-gitops-wiring.md
coders:
  1: codex   # small tricky logic (policy validation, object-form emit) contained in one script and its test
  2: lead    # manifest edits: image, env, one NetworkPolicy
  3: codex   # jq assertions and negative mutations, contained in one test script
  4: lead    # docs
reviewers:
  - codex    # review of each draft and `codex review --base origin/main` on factory-gitops
---

# Plan: wire the 3.17.0 gateway features into factory-gitops, all off

Repo factory-gitops (base `main`, branch `feat/1959-gateway-gitops-wiring`), worktree only. Approved spec decisions
(`spec/2026-11-18-1959-gateway-gitops-wiring.md`, this hub) carried over:

- Image `sha-24184c6-gateway` to `sha-800eb3e-gateway` (cosign verified, deploy.yml identity). Immutable tag, not tag@digest.
- Env: `GATEWAY_METRICS` literal `"off"`; `GATEWAY_OTLP_ENDPOINT`, `GATEWAY_OTLP_HEADERS`, `GATEWAY_UPSTREAM2_API_KEY`
  all `secretKeyRef` `model-gateway-secrets`, same-named key, `optional: true`, block style (the `secrets` CI scan does
  not see flow style). No literal OTLP URL. `GATEWAY_COOLDOWN_S` not set.
- Routes: optional `apps/model-gateway/route-policy.json` (`{}` committed) -> object route `{model, quota?, upstreams?}`
  from `gen-model-routes.py`; `key_env` only `GATEWAY_UPSTREAM_API_KEY` or `GATEWAY_UPSTREAM2_API_KEY`; with `{}` the
  ConfigMap is byte-identical to today.
- NetworkPolicy `allow-otlp-egress` (ns `gateway`, `app=model-gateway`): egress to ns `factory` + pod `app=observe` in
  ONE peer, TCP 5080 only. No ServiceMonitor (no CRD). Ingress unchanged.
- Docs: metrics check by port-forward and summing pods, OTLP finding (v0.90.3 accepts JSON at
  `/api/{org}/v1/traces`; endpoint `http://observe.factory.svc.cluster.local:5080/api/default`; unverified live),
  restart after Secret changes, per-pod quota (token quota is an admission threshold, can overshoot >2x), AC-3 conditions.
- Do not create secrets, do not touch the cluster beyond read-only `get`, do not tick any acceptance box.

## Steps

1. `scripts/gen-model-routes.py`, `scripts/test-gen-model-routes.sh`, `apps/model-gateway/route-policy.json` (new, `{}`):
   read optional `route-policy.json` (missing file = `{}`); validate (top-level object, keys in CLASSES, value object with
   only `quota` and/or `upstreams`; `quota` object with `window_s` default 60 and `requests` and/or `tokens`, all
   positive non-bool numbers; `upstreams` non-empty list of objects with `url` http(s)+host, `key_env` in the two allowed
   names (optional), `model` non-empty string (optional)); invalid -> `parser.error` exit 2. For a class in the policy,
   emit `{"model": <selected or override model>, "quota"?: ..., "upstreams"?: [...]}` (upstream `url` as given minus
   trailing slash); a policy class with no resolvable model is an error. Unlisted classes unchanged strings.
   Test additions: positive fixture (quota + two ordered upstreams, primary first), the rejection cases (non-positive
   quota, no requests/tokens, non-http URL, `key_env` `GATEWAY_UPSTREAM99_API_KEY` and `PATH`, unknown class, unknown
   field), empty policy output identical to no policy file. Check: `bash scripts/test-gen-model-routes.sh` and the
   pinned-catalog `--check` from the existing plan (output unchanged).
   Traps: stdlib only; keep script executable; fixtures use example hostnames and no keys; the committed ConfigMap must not change.
2. `apps/model-gateway/manifests/manifests.yaml`: image tag; the four env entries after `GATEWAY_ROUTES_PATH` with a
   comment on activation + restart; new `allow-otlp-egress` NetworkPolicy after `allow-provider-egress`. Check:
   `kustomize build apps/model-gateway/manifests >/dev/null`, `git diff` shows only these.
   Traps: Kyverno `aifactory:*` glob needs a tag, not tag@digest; `readOnlyRootFilesystem` stays; no `value:` for secrets.
3. `scripts/test-gateway-wiring.sh`: add a gateway section rendering `apps/model-gateway/manifests` with the existing
   `render` helper. Failures (one line each) for: `GATEWAY_METRICS` not literal `off`; any of
   `GATEWAY_OTLP_ENDPOINT|GATEWAY_OTLP_HEADERS|GATEWAY_UPSTREAM2_API_KEY` missing, duplicated, with a literal `value`, or
   not an optional `model-gateway-secrets` ref with key equal to its name; any `*_API_KEY|*TOKEN` env on the container
   that is not optional; a route in `model-routes` `routes.json` that is an object (default must be strings only; the
   test sets `ALLOW_ROUTE_POLICY=1` is NOT supported: this guard is for the committed default); `allow-otlp-egress` not
   exactly one egress rule with one peer (namespace `factory` AND pod `app=observe`) on TCP 5080 only. Negative mutations
   for each rule (reuse the existing `mutate` pattern, run against a separate rendered gateway JSON). Check:
   `bash scripts/test-gateway-wiring.sh` prints all `pass` lines and `gateway wiring tests passed`; `shellcheck`.
   Traps: existing client-Deployment checks and mutations stay unchanged; needs kustomize, yq, jq (already in CI).
4. `docs/model-gateway.md`: new section "Gateway features (3.17.0)": what is wired and off, enabling checklist for the
   owner (seed three keys with the exact `kubectl create secret ... --from-file` shape only if it fits the existing
   Secret procedure; flip metrics via PR; restart), `/metrics` check (port-forward per pod, token from a file, sum),
   quota per pod and AC-3 conditions, route-policy example and the regenerate command, OTLP finding with the unverified
   status, and update the "Not done yet" list. Check: `grep` for no secret values; mkdocs nav unchanged.
   Traps: examples contain placeholders only; never print a token.

## Tests

`bash scripts/test-gen-model-routes.sh`, `bash scripts/test-gateway-wiring.sh`, drift `--check` against the pinned
catalog (unchanged), `kustomize build apps/model-gateway/manifests`, `shellcheck` on both scripts; PR checks
(manifest-validate, kubeconform, secrets scan, model-gateway-tools) green on the head SHA.

## Rollback

Revert the PR: image back to `sha-24184c6-gateway` (one roll), env and NetworkPolicy removed by Argo prune. Nothing
owner-side changed.
