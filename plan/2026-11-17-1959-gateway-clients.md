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
   Traps: both selectors in the same peer (separate peers would allow every pod in the `gateway` namespace, and any `app=model-gateway` pod in `factory`).
3. `scripts/verify-model-gateway.sh <base-url> <token-file>` (new, executable) and `scripts/test-verify-model-gateway.sh`; rewrite `docs/model-gateway.md`.
   Script requirements: `set +x` before the token is read (tracing may be inherited); every curl call is `curl -q ...` with `-q` first, `--connect-timeout 5 --max-time 130`, no `--fail`, status from `-w '%{http_code}'`, body discarded. Checks, in order: `GET <base>/healthz` expects 200; `POST <base>/v1/chat/completions` without a token expects 401; the same with the token expects 200. Token: first line of the file, rejected if empty or if it contains a quote, backslash or control character; passed as `header = "Authorization: Bearer <token>"` on a curl config read from stdin (`-K -`), never in argv. Body by `printf`: `{"model":"<M>","messages":[{"role":"user","content":"ping"}],"max_tokens":1}` with `M` from env `GATEWAY_PROBE_MODEL` (required, must match `[A-Za-z0-9._:/-]+`). Output: one line per check with the status code only; status `000` is reported as a transport failure; any mismatch ends with exit 1, all matching exit 0. Usage line printed on a missing argument (exit 2).
   Self-test (`scripts/test-verify-model-gateway.sh`): python `http.server` stub on a random local port that returns 200 on `/healthz`, 401 without the right `Authorization`, 200 with it; cases: all pass exits 0; stub that always 401s exits 1; closed port exits 1 and prints 000; token with a quote is refused; model with a space is refused; a `HOME` containing a `.curlrc` with `verbose` and `trace-ascii` does not put the throwaway token in the output; the throwaway token never appears in stdout/stderr.
   Docs, `docs/model-gateway.md`: rewrite the existing "Owner steps" so the sequence is: create `model-gateway-secrets`, seed `MODEL_GATEWAY_CLIENT_TOKEN` in `factory-secrets` through the agenix bootstrap, restart the gateway, run the verifier through `kubectl -n gateway port-forward svc/model-gateway 8080` BEFORE `shred`-ing the token files (401 without, then the 200 needs the egress policy synced), then seed `MODEL_GATEWAY_URL` (`http://model-gateway.gateway.svc.cluster.local:8080`), then `kubectl -n factory rollout restart deploy/<cfactory|tfactory|aifactory>` one service at a time, for CFactory also switch the copilot provider to `ollama` in Settings; state the order matters (token before URL). Replace "Not done yet" with what remains: the Plane B bench test and rotation/revocation of old provider keys (owner), stage 3/4/5/6 of the epic. Keep the Decisions and Plane B sections.
   Check: `bash -n` on both scripts, `bash scripts/test-verify-model-gateway.sh` exits 0, `shellcheck` if present.
   Traps: never print or log the token; the self-test uses throwaway values only; keep the scripts POSIX-ish bash without extra dependencies beyond curl and python3 for the stub.
4. Issue comments (lead): Decision comment on #1959 (no release needed, wiring, owner activation order), assessment comment on #1958 item 3 with gaps (a)-(d). Epics and #1959 stay open for the owner steps.

## Tests

In the gitops worktree: `kustomize build` for `apps/cfactory/manifests`, `apps/tfactory/manifests`, `apps/aifactory/manifests`, `apps/factory-namespace/manifests`; `bash scripts/test-verify-model-gateway.sh`; the PR's CI (`manifest validation (blocking)`, secret scan, gitleaks) green on the head SHA. Read-only after sync: `kubectl -n factory get deploy cfactory tfactory aifactory` Ready, `-o yaml` shows the env entries.

## Rollback

Revert the gitops PR; the env entries and the rule disappear on the next sync. Nothing else changes because nothing is activated.

## Follow-ups (owner repos, not in this plan)

For #1958 item 3: PFactory captures and persists `model_route` and `change_id`, prints `controls` and `agent_identity` in `governance_cli`, and a join from image SHA bump to plan slug is designed; re-check the live registry for schema-2 rows after the next emit.
