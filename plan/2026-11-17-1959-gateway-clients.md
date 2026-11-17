---
status: draft
issue: 1959
spec: spec/2026-11-17-1959-gateway-clients.md
coders:
  1: codex   # three mechanical, near-identical env insertions in three manifests
  2: lead    # one NetworkPolicy rule, security-sensitive
  3: lead    # shell script with secrecy requirements and its self-test
reviewers:
  - codex
---

# Plan: wire the gateway clients as optional, default-off env

Repo for all edits: olafkfreund/factory-gitops, worktree off `origin/main`, branch `feat/1959-gateway-client-env`. These Factory files are the artifacts only.

Approved decisions: env `<SVC>_MODEL_GATEWAY_URL` from `factory-secrets/MODEL_GATEWAY_URL` and `<SVC>_MODEL_GATEWAY_TOKEN` from `factory-secrets/MODEL_GATEWAY_CLIENT_TOKEN`, both `optional: true`, block style, URL value `http://model-gateway.gateway.svc.cluster.local:8080` (origin, no `/v1`); direct provider env untouched; no CFactory release (promotion already shipped, live images carry the flags); one Job egress rule to gateway pods on 8080; a read-only verifier script; item 3 of #1958 assessed, not coded.

## Steps

1. Manifests, prefix `CFACTORY`, `TFACTORY`, `AIFACTORY` (block-style entries, each with a one-line comment: off until the keys exist; seed the token first):
   - `apps/cfactory/manifests/manifests.yaml`: container `cfactory` env, after the `OLLAMA_API_KEY` entry (~l.119).
   - `apps/tfactory/manifests/manifests.yaml`: Deployment `tfactory` env, after `OPENAI_COMPATIBLE_API_KEY` (~l.736).
   - `apps/aifactory/manifests/manifests.yaml`: Deployment `aifactory` env, after `OPENAI_COMPATIBLE_API_KEY` (~l.766).
   Check: `kustomize build apps/<svc>/manifests` for the three; `git diff` shows only added env entries, each `optional: true`, no `value:` for the token.
   Traps: the Secret is `factory-secrets` in namespace `factory`; do not touch image tags (CI bumps them); no flow style for new secret refs.
2. `apps/factory-namespace/manifests/networkpolicy-sandbox-jobs.yaml`: add egress rule 6 after rule 5: one `to` peer with `namespaceSelector` `kubernetes.io/metadata.name: gateway` AND `podSelector` `app: model-gateway`, TCP 8080, with a comment naming Factory#1959. Check: `kustomize build apps/factory-namespace/manifests` and the CI kubeconform step; confirm the selectors against `apps/model-gateway/manifests/manifests.yaml` (Deployment label `app: model-gateway`, namespace `gateway`).
   Traps: both selectors in the same peer (separate peers would allow any pod in the namespace or any `app=model-gateway` pod anywhere).
3. `scripts/verify-model-gateway.sh` (new, executable) as specified in spec design 3, plus `scripts/test-verify-model-gateway.sh` (stub HTTP server on a random local port, the cases listed in the spec verification); `docs/model-gateway.md`: replace "Not done yet" with the activation order (spec design 4: seed Secret, seed token, run the script through a port-forward, seed URL, per-service `rollout restart`; CFactory also needs the copilot provider switched to `ollama`) and the Plane B / rotation owner steps that remain. Check: `bash -n`, the self-test exits 0, `shellcheck` if present.
   Traps: never print or log the token; no `set -x`; the token file is read once; the self-test uses throwaway values only.
4. Issue comments (lead): Decision comment on #1959 (no release needed, wiring, owner activation order), assessment comment on #1958 item 3 with gaps (a)-(d). Epics and #1959 stay open for the owner steps.

## Tests

In the gitops worktree: `kustomize build` for `apps/cfactory/manifests`, `apps/tfactory/manifests`, `apps/aifactory/manifests`, `apps/factory-namespace/manifests`; `bash scripts/test-verify-model-gateway.sh`; the PR's CI (`manifest validation (blocking)`, secret scan, gitleaks) green on the head SHA. Read-only after sync: `kubectl -n factory get deploy cfactory tfactory aifactory` Ready, `-o yaml` shows the env entries.

## Rollback

Revert the gitops PR; the env entries and the rule disappear on the next sync. Nothing else changes because nothing is activated.

## Follow-ups (owner repos, not in this plan)

For #1958 item 3: PFactory captures and persists `model_route` and `change_id`, prints `controls` and `agent_identity` in `governance_cli`, and a join from image SHA bump to plan slug is designed; re-check the live registry for schema-2 rows after the next emit.
