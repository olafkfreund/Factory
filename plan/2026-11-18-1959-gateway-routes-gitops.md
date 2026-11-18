---
status: draft
issue: 1959
spec: spec/2026-11-18-1959-gateway-routes-gitops.md
coders:
  1: codex   # small tricky logic (selection rule, tie-break, drift check), contained in two new files
  2: lead    # three small edits to one manifest
  3: codex   # jq/bash classification logic plus a fake-kubectl test, contained in two new files
  4: codex   # polling/convergence logic plus a fake-kubectl test, contained in two new files
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

1. `scripts/gen-model-routes.py` (new, stdlib python 3.12), `scripts/test-gen-model-routes.sh` (new), `apps/model-gateway/hub-catalog.sha` (new), `apps/model-gateway/route-overrides.json` (new, `{}`), `apps/model-gateway/manifests/model-routes.yaml` (generated), `apps/model-gateway/manifests/kustomization.yaml` (add `- model-routes.yaml`). CLI: `gen-model-routes.py --catalog FILE [--check]`, reads the SHA file (must be 40 hex) only to write the header comment `# generated from Factory apis/model-catalog.json @ <sha>; do not edit`; writes the ConfigMap or with `--check` compares to the committed file and exits 1 with a unified diff. JSON value is `json.dumps(routes, sort_keys=True, indent=2) + "\n"`. Test: fixture catalogs in a temp dir cover the rule, tie-break, placeholder/subscription/other-provider exclusion, local omitted, override wins, unknown class or empty override rejected (exit 2), `--check` drift, kustomization lists `model-routes.yaml`, and (when `kustomize` exists) the build contains `name: model-routes`. Check: `bash scripts/test-gen-model-routes.sh`, and `curl -fsSL https://raw.githubusercontent.com/olafkfreund/Factory/92d2508e057524c054c6842b0170168ff7213c25/apis/model-catalog.json -o /tmp/cat.json && python3 scripts/gen-model-routes.py --catalog /tmp/cat.json --check`.
   Traps: public repo, no secrets in fixtures; `.pre-commit`/gitleaks scan the tree; keep script executable.
2. `apps/model-gateway/manifests/manifests.yaml` Deployment: image to `sha-24184c6-gateway`; env `GATEWAY_ROUTES_PATH` literal; `volumeMounts` (`model-routes`, `/etc/model-routes`, `readOnly: true`); `volumes` `model-routes` configMap `{name: model-routes, optional: true}`; update the header comment of the file. Check: `kustomize build apps/model-gateway/manifests | kubeconform -strict -ignore-missing-schemas` and `git diff` shows no other change.
   Traps: no `subPath`; Kyverno image glob `aifactory:*` with an immutable tag, not tag@digest (see the existing comment); `readOnlyRootFilesystem` stays true.
3. `scripts/verify-no-provider-keys.sh` + `scripts/test-verify-no-provider-keys.sh` (new, bash). Implement spec design 5 exactly (classes `VIOLATION|UNVERIFIED|GATEWAY-REF|ACCEPTED`, `--strict`, `--accept-volume NAME` repeatable, `--gateway-token-file FILE`, `KUBE_CONTEXT`). Test uses a fake `kubectl` that accepts only the exact expected argv and exits 97 otherwise, with fixtures for every case in spec design 7. Check: `bash scripts/test-verify-no-provider-keys.sh` (all pass), `shellcheck` on both.
   Traps: `set +x`; never echo env values or the token; token file read with `IFS= read -r`; do not call `kubectl get secret`.
4. `scripts/verify-route-hot-reload.sh` + `scripts/test-verify-route-hot-reload.sh` (new, bash). Implement spec design 6 exactly (`record STATE`, `check STATE [TIMEOUT]`, `KUBE_CONTEXT`, `POLL_SECONDS` env for tests). Fake `kubectl` as in step 3 with every case in spec design 7. Check: `bash scripts/test-verify-route-hot-reload.sh`, `shellcheck`.
   Traps: exec uses a fixed argv (`python3 -c` with the path as a literal in the script, not interpolated user input); no fallback on exec failure.
5. `.github/workflows/model-gateway-tools.yml` (new; header comment; no `paths:`; actions pinned as in `cred-sync-test.yml`; jobs `routes-drift` and `shell-tests`), and `docs/model-gateway.md`: Routes section (rule, overrides, SHA bump procedure, the Claude-id-vs-Ollama-Cloud residual), AC-1 and AC-2 usage with exact commands, and the Plane B bench test checklist (throwaway `HOME`, token file from `claude setup-token`, loopback listener that prints only the request line and header names, `ANTHROPIC_BASE_URL=http://127.0.0.1:<port> claude -p hi`, hit/miss meaning, ToS question with where to record). Update the "Not done yet" list. Check: `python3 -c 'import yaml;yaml.safe_load(open(".github/workflows/model-gateway-tools.yml"))'`; run each workflow step's command locally; mkdocs nav unchanged.
   Traps: the owner runs the bench test, we only document it; no secret value in any example command.

## Tests

`bash scripts/test-gen-model-routes.sh scripts/test-verify-no-provider-keys.sh scripts/test-verify-route-hot-reload.sh` (each separately) all pass; drift check against the pinned catalog passes; `kustomize build` for `apps/model-gateway/manifests` + kubeconform passes (also in `manifest-validate`); PR checks green on the head SHA. Read-only: `kubectl --context k3d-factory get` to record the live AC-1 report in the PR.

## Rollback

Revert the PR: the Deployment returns to `sha-1c4cc96-gateway` without the volume (one roll, 2 replicas), the ConfigMap is pruned by Argo. Nothing owner-side changed.
