---
status: draft
issue: 1959
intent: intent/2026-11-18-1959-gateway-routes-gitops.md
---

# Spec: model-routes ConfigMap, verifiers and bench checklist (factory-gitops)

All code lands in olafkfreund/factory-gitops (base `main`); artifacts live here.

## Design

1. **Routes file format** (AIFactory `gateway.py:62-80`, `tests/model_gateway/test_gateway.py:150`):
   flat JSON `{"<class>": "<model>"}`, classes `local|cheap|balanced|frontier`, re-read on each
   request; a missing class, empty value or unreadable file leaves the request unchanged.
2. **Generator** `scripts/gen-model-routes.py` (stdlib python). Inputs: a catalog file
   (`--catalog`), the pinned hub SHA read from `apps/model-gateway/hub-catalog.sha`, optional
   `apps/model-gateway/route-overrides.json` (flat `{class: model}`, committed as `{}`). Rule per
   class: candidates are catalog models with `provider == "claude"` (the concrete full ids; the
   other entries are CLI-login providers or `<placeholders>` the gateway cannot serve),
   `price.mode == "metered"` and no `<` in the id; pick the lowest `in_per_mtok + out_per_mtok`,
   ties broken by larger `caps.context` then id. `local` has no concrete candidate and is omitted.
   Overrides win per class and must be a known class with a non-empty string. Output:
   `apps/model-gateway/manifests/model-routes.yaml` (added to that directory's `kustomization.yaml`; the test asserts it), ConfigMap `model-routes` (namespace
   `gateway`, fixed name, no hash suffix), key `routes.json`, a header comment naming the catalog
   SHA. Today: `cheap=claude-haiku-4-5-20251001`, `balanced=claude-sonnet-5`,
   `frontier=claude-opus-4-8`. `--check` renders to memory and exits 1 on any difference
   with the committed file. The rule is written into `docs/model-gateway.md`.
   Deviation from the task's recommendation (which allowed subscription models): subscription
   entries (`codex`, `github-models`, `ollama-cloud:<model>`) are login-file or placeholder
   providers, and the cheapest "metered or subscription" pick would be a price-0 CLI id such as
   `codex`; `gemini` (metered, cheapest balanced) is shorthand for a CLI, not a model id. The
   `claude` full ids are the only concrete model ids in the catalog.
3. **Drift CI** `.github/workflows/model-gateway-tools.yml` (no `paths:` filter, like the other
   required checks; pinned action SHAs copied from `cred-sync-test.yml`). Job `routes-drift`: validate
   the SHA file is 40 hex, `curl -fsSL` `https://raw.githubusercontent.com/olafkfreund/Factory/<sha>/apis/model-catalog.json`
   (constant owner/repo, so a PR cannot point it at a fork; the file is parsed, never executed; a
   fetch failure fails the job), run `gen-model-routes.py --check`. Job `shell-tests`: the three
   cluster-free tests. A catalog change reaches the gateway by bumping the SHA and re-running the
   generator in one PR.
4. **Deployment** (`manifests.yaml`): image `sha-1c4cc96-gateway` to `sha-24184c6-gateway`
   (prerequisite: the live image has no route code); env `GATEWAY_ROUTES_PATH=/etc/model-routes/routes.json`;
   volume `model-routes` = `configMap {name: model-routes, optional: true}` mounted read-only at
   `/etc/model-routes` as a directory (no `subPath`). `AIFACTORY_PHASE_ROUTES`/`AIFACTORY_RUNTIMES`
   not touched. Replicas, probes, NetworkPolicies, securityContext unchanged. The pod template
   change rolls the two replicas once (PDB `minAvailable: 1`).
5. **`scripts/verify-no-provider-keys.sh`** (AC-1; bash + `kubectl --context ${KUBE_CONTEXT:-k3d-factory}` + `jq`, read-only; no
   Secret object is ever read, only workload specs). Targets: Deployments `aifactory pfactory tfactory cfactory`
   (namespace `factory`) and EVERY Job carrying a `factory.io/kind` label (build, task, verify) in that namespace.
   For each pod template: (a) env var names matching the model-provider key list (`OPENAI_API_KEY
   OPENAI_COMPATIBLE_API_KEY GEMINI_API_KEY GOOGLE_API_KEY OLLAMA_API_KEY ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN
   CLAUDE_CODE_OAUTH_TOKEN`) are classified: a `secretKeyRef` to key `MODEL_GATEWAY_CLIENT_TOKEN` or
   `model-gateway-token` is `GATEWAY-REF` (the gateway integration deliberately puts the client token in
   `OPENAI_COMPATIBLE_API_KEY`); any other `secretKeyRef`/`configMapKeyRef` is `VIOLATION`; a literal value equal to the token in
   `--gateway-token-file` (compared in memory, never printed) is `GATEWAY-REF`; any other literal is `VIOLATION`; a literal
   when no token file was given is `UNVERIFIED`; (b) any `envFrom` entry is `UNVERIFIED` (names only); (c) volumes
   whose secret is `factory-cli-creds` or matches `cli-creds` are `VIOLATION`, or `ACCEPTED` when named with
   `--accept-volume NAME` (Plane C residual, 2026-11-16 decision). Output is `<CLASS> <workload> <container|volume> <name>`, names only, never values.
   Exit 0 by default (reports current state); `--strict` exits 1 on any VIOLATION or UNVERIFIED, and on any inspection that
   could not run (kubectl or jq missing, kubectl error, malformed JSON, a Deployment missing, zero Jobs found): a gate that cannot run fails.
   The gateway's own upstream key and third-party keys (LANGCHAIN, RAPIDAPI) are out of scope.
6. **`scripts/verify-route-hot-reload.sh`** (AC-2). `record <state>` stores, per gateway pod (label `app=model-gateway`, namespace
   `gateway`): name, UID, container restart count, and the routes file as the pod sees it
   (`kubectl exec ... -- python3 -c 'print(open(path).read())'`; read-only). An exec failure fails the run: there is no
   fallback to ConfigMap data, since that would prove API state, not propagation. The owner then changes
   `route-overrides.json` or the catalog pin in a PR and Argo syncs (never `kubectl edit`: selfHeal reverts it).
   `check <state> [timeout]` polls (default 180 s; kubelet projection takes up to about 90 s) until EVERY recorded pod shows the
   same content, equal to the live ConfigMap `routes.json` and different from the recorded content; then requires every recorded pod to
   still exist with the same UID and the same restart count, and prints old vs new route per class. Fails on a
   missing pod, divergent pods, no change within the timeout, a changed UID or restart count (a restart would fake hot reload), or any exec failure.
   `X-Model-Route` is not used: it carries the class, not the model.
7. **Tests** (cluster-free; a fake `kubectl` first in `PATH` that serves canned JSON for the exact expected argument vectors and exits 97 on
   anything else, so a wrong selector or JSON path cannot pass silently; same style as `test-verify-model-gateway.sh`).
   `scripts/test-gen-model-routes.sh`: rule, tie-break, local omitted, override wins, bad override rejected, `--check` fails on drift,
   the kustomization lists `model-routes.yaml` and `kustomize build` output (if kustomize is present; CI always has it) contains `name: model-routes`.
   `test-verify-no-provider-keys.sh`: clean fixture passes `--strict`; env key, secretKeyRef, `envFrom`, volume, Job violations; gateway-ref by
   secretKeyRef and by literal+token-file under the SAME variable name; accept-volume; default mode exits 0; `--strict` fails on zero Jobs,
   kubectl failure, malformed JSON, missing Deployment, missing jq; no value printed. `test-verify-route-hot-reload.sh`: all pods converge
   with same UIDs passes; same content times out; ConfigMap changed but exec fails never passes; divergent pods, missing pod, changed UID and
   restart-count change each fail.
8. **Docs** `docs/model-gateway.md`: routes section (rule, overrides, residual that Claude ids do not run
   against the Ollama Cloud upstream until overrides pin concrete ids), AC-1/AC-2 usage, and the Plane B
   bench test as an owner checklist (throwaway `HOME`, token from a file via `claude setup-token`, a loopback
   listener printing only request line and header names, `ANTHROPIC_BASE_URL=http://127.0.0.1:<port> claude -p hi`,
   what a hit and a miss mean, the provider-terms question with the pages to read and where to record the
   answer). Not run by us.

## Alternatives rejected

- Kustomize `configMapGenerator`: adds a hash suffix, which forces a pod roll on every route change and defeats hot reload.
- Fetching the catalog at runtime or from `main`: unpinned; a hub change would turn this repo red or change routes silently.
- Mounting with `subPath`: Kubernetes never updates subPath mounts.
- `X-Model-Route` as the AC-2 proof: it reports the class.
- `kubectl edit configmap` for AC-2: selfHeal reverts it; the real path is Git + Argo.
- Including subscription/shorthand catalog entries: see design 2.
- Reading `factory-cli-creds` to list its keys: that reads secret values; the volume definition is enough.

## Risks

- Rolling the gateway: 2 replicas, `minAvailable: 1`; chat is already 503 until the Secret exists, so no live traffic is lost.
- The new image tag must be signed (Kyverno): same `aifactory:*` glob and build workflow as the old tag; checked by `manifest-validate` and the Argo sync.
- Class requests before overrides pin Ollama-servable ids would forward a Claude id upstream and fail: nothing sends a class until the owner sets `AIFACTORY_PHASE_ROUTES`; documented as an owner step.
- Kubelet ConfigMap propagation latency is unmeasured on this cluster: AC-2 `check` measures it and the doc says to record it.

## Verification

`python3 scripts/gen-model-routes.py --check --catalog <pinned catalog>`; the three `scripts/test-*.sh`; `kustomize build apps/model-gateway/manifests` + kubeconform (as `manifest-validate`); CI green on the PR head SHA; read-only `kubectl` observation of the live gateway (no apply). Live AC-1 run output is pasted in the PR as current violations.
