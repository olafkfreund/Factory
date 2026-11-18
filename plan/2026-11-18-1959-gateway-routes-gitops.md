---
status: approved
issue: 1959
spec: spec/2026-11-18-1959-gateway-routes-gitops.md
coders:
  1: codex   # small tricky logic (selection rule, tie-break, drift check), contained in new files
  2: lead    # three small edits to one manifest
  3: codex   # jq/bash classification logic plus a fake-kubectl test, contained in new files
  4: codex   # polling/convergence logic plus a fake-kubectl test, contained in new files
  5: lead    # workflow and docs, wiring everything together
reviewers:
  - codex    # final `codex review --base origin/main` on factory-gitops, and a review of each draft
---

# Plan: model-routes ConfigMap, verifiers and bench checklist

Repo factory-gitops (base `main`, branch `feat/1959-gateway-routes-gitops`). Work in the worktree only. Everything
is in the approved spec `spec/2026-11-18-1959-gateway-routes-gitops.md` (this repo's Factory hub); decisions carried over:

- Routes file = flat JSON `{class: model}`, classes `local|cheap|balanced|frontier`, ConfigMap `model-routes` (ns `gateway`), key `routes.json`, fixed name, directory mount `/etc/model-routes` without `subPath`, optional volume, `GATEWAY_ROUTES_PATH=/etc/model-routes/routes.json`.
- Image `sha-1c4cc96-gateway` is bumped to `sha-24184c6-gateway` (the old one has no route code).
- Rule: provider `claude`, `price.mode == metered`, id without `<`; lowest `in_per_mtok + out_per_mtok`, tie: larger `caps.context`, then id. `local` omitted. `apps/model-gateway/route-overrides.json` (`{}`) overrides per class. Catalog pin in `apps/model-gateway/hub-catalog.sha` = `92d2508e057524c054c6842b0170168ff7213c25`.
- Do NOT set `AIFACTORY_PHASE_ROUTES` or `AIFACTORY_RUNTIMES`. NetworkPolicies, replicas, probes, securityContext unchanged.
- Verifiers are read-only, print names never values, read tokens only from files, and fail rather than pass when they cannot inspect.

## Steps

1. `scripts/gen-model-routes.py` (new, stdlib python 3.12), `scripts/test-gen-model-routes.sh` (new), `apps/model-gateway/hub-catalog.sha` (new), `apps/model-gateway/route-overrides.json` (new, `{}`), `apps/model-gateway/manifests/model-routes.yaml` (generated), `apps/model-gateway/manifests/kustomization.yaml` (add `- model-routes.yaml`). CLI: `gen-model-routes.py --catalog FILE [--check]`, reads the SHA file (must be 40 hex) only to write the header comment `# generated from Factory apis/model-catalog.json @ <sha>; do not edit`; writes the ConfigMap or with `--check` compares to the committed file and exits 1 with a unified diff. JSON value is `json.dumps(routes, sort_keys=True, indent=2) + "\n"`. Test: fixture catalogs in a temp dir cover the rule, tie-break, placeholder/subscription/other-provider exclusion, local omitted, override wins, unknown class or empty override rejected (exit 2), `--check` drift, kustomization lists `model-routes.yaml`, and the rendered build (`kustomize build` to a temp file, which must be non-empty, then grep) contains `name: model-routes`; the build assertion is skipped locally when `kustomize` is absent unless `REQUIRE_KUSTOMIZE=1`, which CI sets. Check: `bash scripts/test-gen-model-routes.sh`, and `curl -fsSL https://raw.githubusercontent.com/olafkfreund/Factory/92d2508e057524c054c6842b0170168ff7213c25/apis/model-catalog.json -o /tmp/cat.json && python3 scripts/gen-model-routes.py --catalog /tmp/cat.json --check`.
   Traps: public repo, no secrets in fixtures; `.pre-commit`/gitleaks scan the tree; keep script executable.
2. `apps/model-gateway/manifests/manifests.yaml` Deployment: image to `sha-24184c6-gateway`; env `GATEWAY_ROUTES_PATH` literal; `volumeMounts` (`model-routes`, `/etc/model-routes`, `readOnly: true`); `volumes` `model-routes` configMap `{name: model-routes, optional: true}`; update the header comment of the file. Check: `kustomize build apps/model-gateway/manifests > /tmp/gw.yaml && test -s /tmp/gw.yaml` (kubeconform runs in `manifest-validate`) and `git diff` shows no other change.
   Traps: no `subPath`; Kyverno image glob `aifactory:*` with an immutable tag, not tag@digest (see the existing comment); `readOnlyRootFilesystem` stays true.
3. `scripts/verify-no-provider-keys.sh` + `scripts/test-verify-no-provider-keys.sh` (new, bash + jq). Behaviour, in full:
   - Usage `verify-no-provider-keys.sh [--strict] [--accept-volume NAME]... [--gateway-token-file FILE]`; `KUBE_CONTEXT` default `k3d-factory`; namespace `factory`.
   - Fetch with `kubectl --context C -n factory get deploy aifactory pfactory tfactory cfactory -o json` (each missing one is an inspection failure) and `kubectl --context C -n factory get jobs -l factory.io/kind -o json` (zero items is an inspection failure). Never `get secret`.
   - For every pod template (Deployment, Job) and every container and initContainer: env names in `OPENAI_API_KEY OPENAI_COMPATIBLE_API_KEY GEMINI_API_KEY GOOGLE_API_KEY OLLAMA_API_KEY ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_OAUTH_TOKEN`: `secretKeyRef` to Secret `factory-secrets` key `MODEL_GATEWAY_CLIENT_TOKEN` is `GATEWAY-REF` (same key under any other Secret name is `VIOLATION`); any other `secretKeyRef` or `configMapKeyRef` is `VIOLATION`; a literal value equal to the first line of `--gateway-token-file` (compared in memory, never printed) is `GATEWAY-REF`; any other literal is `VIOLATION`, except that with no token file given a literal is `UNVERIFIED`. Any `envFrom` entry is `UNVERIFIED` (print only the source name). Volumes whose `secret.secretName` is `factory-cli-creds` or contains `cli-creds` (also inside `projected` sources) are `VIOLATION`, or `ACCEPTED` when that name was given with `--accept-volume`.
   - Output one line per finding `<CLASS> <workload> <container-or-volume> <name>`, never a value; a final summary line with counts and how many Deployments and Jobs were inspected.
   - Exit 0 by default. `--strict` exits 1 when any `VIOLATION` or `UNVERIFIED` exists or any inspection failed (kubectl or jq missing, kubectl non-zero, malformed JSON, missing Deployment, zero Jobs). Usage errors exit 2. `set +x`.
   - Test: fake `kubectl` first in `PATH` that serves canned JSON only for the exact argv above and exits 97 otherwise. Cases: clean passes `--strict`; env secretKeyRef; env literal; `envFrom`; volume; Job violation; `GATEWAY-REF` by `factory-secrets/MODEL_GATEWAY_CLIENT_TOKEN`; same key under another Secret name is `VIOLATION`; literal equal to the token file is `GATEWAY-REF` under the SAME variable name `OPENAI_COMPATIBLE_API_KEY`; `--accept-volume`; default exit 0 with violations; `--strict` fails on zero Jobs, kubectl failure, malformed JSON, a missing Deployment, jq missing (empty `PATH` dir for jq); the throwaway token and any literal value never appear in output. Check: `bash scripts/test-verify-no-provider-keys.sh`, `shellcheck` on both.
   Traps: `set +x`; token file read with `IFS= read -r`; public repo, throwaway fixture values only.
4. `scripts/verify-route-hot-reload.sh` + `scripts/test-verify-route-hot-reload.sh` (new, bash + jq). Behaviour, in full:
   - Usage `verify-route-hot-reload.sh record STATE_FILE` and `verify-route-hot-reload.sh check STATE_FILE [TIMEOUT_SECONDS=180]`; env `KUBE_CONTEXT` (default `k3d-factory`), `POLL_SECONDS` (default 10, tests set 0), namespace `gateway`, label `app=model-gateway`, path `/etc/model-routes/routes.json`.
   - `record`: `kubectl get pods -n gateway -l app=model-gateway -o json`; require at least one Running pod; for each pod store name, UID, the first container's restartCount and the file content from `kubectl exec -n gateway POD -c model-gateway -- python3 -c 'import sys;sys.stdout.write(open("/etc/model-routes/routes.json").read())'` into STATE_FILE as JSON. Any failure (including exec) exits 1 and writes nothing; there is NO fallback to ConfigMap data. Print the recorded routes and instruct the owner to change `apps/model-gateway/route-overrides.json` in a PR and let Argo sync (never `kubectl edit`).
   - `check`: loop until the timeout: re-list pods and re-read each file; success only when every recorded pod still exists (same name AND UID AND restartCount), every pod's content is identical, equals `kubectl get configmap model-routes -n gateway -o json` `.data["routes.json"]`, and differs from the recorded content; then print per-class old to new model and exit 0. Exit 1 with a reason for: no change within the timeout, divergent pods, a missing pod, a changed UID or restartCount (say a restart fakes a hot reload), any exec or kubectl failure. Exit 2 on usage errors.
   - Test: fake `kubectl` as in step 3, state-driven (a counter file changes what pods report on successive calls). Cases: all pods converge, UIDs and restart counts unchanged, passes; content never changes, times out and fails; ConfigMap changed while exec fails never passes; divergent pods fail; a recorded pod missing fails; same UID but restartCount+1 fails; a changed UID fails; `record` with exec failing exits 1 and writes no state file. Check: `bash scripts/test-verify-route-hot-reload.sh`, `shellcheck` on both.
   Traps: path is a literal in the script; the pods' own content is the proof, the ConfigMap is only the expected value.
5. `.github/workflows/model-gateway-tools.yml` (new; header comment; no `paths:`; actions pinned as in `cred-sync-test.yml`; jobs `routes-drift` and `shell-tests`), and `docs/model-gateway.md`: Routes section (rule, overrides, SHA bump procedure, the Claude-id-vs-Ollama-Cloud residual), AC-1 and AC-2 usage with exact commands, and the Plane B bench test checklist (throwaway `HOME`, token file from `claude setup-token`, loopback listener that prints only the request line and header names, `ANTHROPIC_BASE_URL=http://127.0.0.1:<port> claude -p hi`, hit/miss meaning, ToS question with where to record). Update the "Not done yet" list. The workflow installs the same pinned kustomize as `manifest-validate` in `shell-tests` and sets `REQUIRE_KUSTOMIZE=1`. Pre-merge, read-only: `cosign verify` the new image tag (done: signed). Check: `python3 -c 'import yaml;yaml.safe_load(open(".github/workflows/model-gateway-tools.yml"))'`; run each workflow step's command locally; mkdocs nav unchanged.
   Traps: the owner runs the bench test, we only document it; no secret value in any example command.

## Tests

`bash scripts/test-gen-model-routes.sh scripts/test-verify-no-provider-keys.sh scripts/test-verify-route-hot-reload.sh` (each separately) all pass; drift check against the pinned catalog passes; `kustomize build` for `apps/model-gateway/manifests` is non-empty and passes kubeconform in `manifest-validate`; PR checks green on the head SHA. Read-only: `kubectl --context k3d-factory get` to record the live AC-1 report in the PR.

## Rollback

Revert the PR: the Deployment returns to `sha-1c4cc96-gateway` without the volume (one roll, 2 replicas), the ConfigMap is pruned by Argo. Nothing owner-side changed.
