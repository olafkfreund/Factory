---
status: draft
issue: 1959
intent: intent/2026-11-17-1959-gateway-clients.md
---

# Spec: wire the gateway clients (CFactory, TFactory, AIFactory) as optional, default-off env

Code lands in olafkfreund/factory-gitops (main); these artifacts live in Factory because the issue does.

## Design

1. **Env, three manifests** (`apps/{cfactory,tfactory,aifactory}/manifests/manifests.yaml`, block style, next to the existing provider env): `<SVC>_MODEL_GATEWAY_URL` from Secret `factory-secrets` key `MODEL_GATEWAY_URL`, and `<SVC>_MODEL_GATEWAY_TOKEN` from the same Secret key `MODEL_GATEWAY_CLIENT_TOKEN`, both `optional: true`. Missing keys leave the variables unset, which is the clients' off state. `OLLAMA_API_KEY`, `OPENAI_*` and the other direct env are untouched (stage 6, removal, is later and the owner's). The URL value is the in-cluster origin `http://model-gateway.gateway.svc.cluster.local:8080` (no `/v1`); it is a Secret key only to give the owner one switch; it is not secret.
   Behaviour matrix (from the clients' code): URL absent: unchanged. URL present, token absent: CFactory chat on `ollama|openai|openai_compatible` fails with "model gateway token is not configured"; TFactory and AIFactory Jobs get a rejecting placeholder token and no direct keys, so seed the token first. Token present, URL absent: unchanged.
   TFactory only: `TFACTORY_VERIFY_PROVIDER_SECRET_NAME` (not set in the manifest) would make Jobs require a `model-gateway-token` key in that Secret; the manifest does not set it, so the plain env path is used.
2. **Job egress** (`apps/factory-namespace/manifests/networkpolicy-sandbox-jobs.yaml`): one more egress rule to `namespaceSelector kubernetes.io/metadata.name=gateway` and `podSelector app=model-gateway` in the same peer, TCP 8080. The gateway's own ingress already allows the `factory` namespace on 8080. Control-plane pods (cfactory, tfactory, aifactory) are not selected by this policy and need nothing.
3. **Verifier** `scripts/verify-model-gateway.sh <base-url> <token-file>`: `GET /healthz` expects 200; `POST /v1/chat/completions` without a token expects 401; with the token from the file expects 200. The token is passed to curl through a config on stdin (never in argv), the body is one tiny chat message with `max_tokens` 1 and the model from `GATEWAY_PROBE_MODEL` (required), responses are discarded, only status codes are printed, exit 1 on any mismatch. It sends no write to the cluster; the 200 case costs one upstream token. `docs/model-gateway.md` replaces "Not done yet" with the activation order and a pointer to the script.
4. **Owner activation order** (documented): seed `model-gateway-secrets` (existing steps), seed `MODEL_GATEWAY_CLIENT_TOKEN` in `factory-secrets`, prove 401/200 with the script through a port-forward, then seed `MODEL_GATEWAY_URL` and roll the clients: `kubectl -n factory rollout restart deploy/<cfactory|tfactory|aifactory>` (env from a Secret is read at container start); for CFactory also switch the copilot provider to `ollama` in Settings.
5. **#1958 acceptance item 3 assessment (no code)**: the data exists on the plan side. A PFactory schema-2 signature records `controls[]`, `originator`, `agent_identity`, `autonomy_tier`, `approved_by`, `approved_at`, `model_route`, and `python -m plan.governance_cli --root <docs> [--control X] [--tier T] [--json]` queries them offline. Gaps, recorded in the plan as steps for the owning repos, not done here: (a) the live registry has no schema-2 row until a plan is emitted after the deploy, (b) `model_route` stays null until a client uses the gateway, (c) nothing joins a production change (image SHA bumped in factory-gitops, merge commit) to the plan slug that produced it, so the question "for this production change" is answerable per plan, not per deploy. The item stays unticked.

## Alternatives rejected

- Manifest literal URL: switches the clients on with no token and breaks the copilot (see matrix).
- A ConfigMap for the URL: a second object the owner must create; the Secret key is already part of the seed step.
- Cutting a CFactory release/tag: none exists by design; promotion is the release and is done.
- A new evidence report for item 3: the CLI already answers per plan; a deploy join needs a design in PFactory/AIFactory and is a gap, not a script.
- Wiring Plane B or removing provider keys: stage 5 and 6, blocked on the owner's bench test and rotation.

## Risks

- A rollout after the key is seeded restarts the service (single replicas: brief unavailability); do it per service, not all at once.
- The egress rule widens Job reach by one in-cluster destination; the gateway still requires its client token.
- The 200 probe spends one upstream token.
- Kyverno: no image changes here, nothing to admit.

## Verification

`kustomize build` of the three apps and the namespace app (CI `manifest validation (blocking)`), `kubectl --dry-run=client`/schema as CI does, gitleaks and the secrets scan green; `rendered env` check by grep that each new var is `optional: true` and there is no `value:` literal for the token. Script: `bash -n`, `shellcheck` if CI has it, and a local self-test against a stub HTTP server (python `http.server`) covering 401 without, 200 with, mismatch exits 1, token never in output. Live: read-only `kubectl get` of the rendered Deployments after sync shows the env entries and Pods still Ready.
