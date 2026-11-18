---
status: approved
issue: 1959
spec: spec/2026-11-18-1959-gateway-gitops-proofs.md
coders:
  1: codex   # small tricky jq logic with fixtures, contained in two new files
  2: codex   # small edit of an existing verifier plus new test cases, contained
  3: lead    # bash and jq against rendered manifests, short; I keep it
  4: lead    # CI workflow and docs; I keep builds, commits and docs
reviewers:
  - codex    # read-only review of every draft and the final diff; agy is off by owner decision
---

# Plan: gateway admission proofs, client wiring check, provider-key report in CI

Repo for all edits: olafkfreund/factory-gitops (worktree on branch `feat/1959-gateway-gitops-proofs`, base
`main`). Approved spec decisions carried over, in short:

- New report-mode script `verify-gateway-policyreport.sh [--strict]`; `image_pass=1` only for a `pass` row of
  policy `verify-factory-image-signatures` in the report whose `scope` is `Deployment/model-gateway` with
  `scope.uid` == the Deployment `metadata.uid`, and whose message contains the Deployment image as a whole
  token (not a prefix of a longer tag). Cache-hit rows ("verified from cache") never count.
- `verify-no-provider-keys.sh --deployments-json FILE`: static mode, no kubectl, no Jobs fetch, zero Jobs allowed,
  summary ends `static=1` (live: `static=0`); bad FILE is `INSPECTION-FAIL`; classification untouched.
- CI report-only step prints the static count, always exits 0, warns (never silent zero) on any failure.
- Cluster-free wiring guard for the three client Deployments and the Job egress peer.
- Docs: admission proof procedure (server-side dry-run only, signed control, unsigned existing tag
  `sha-0202033`), flip-to-strict criterion. No Secret, restart, bench test or rotation.

Facts the implementer needs. Live shape (read-only checked): `kubectl -n gateway get policyreport -o json` has
`items[]` with `scope{kind,name,uid}`, `summary`, and `results[]{policy,rule,result,message,timestamp{seconds}}`;
`result` is `pass|fail|warn|error|skip`. The Deployment-scoped report row message is
`verified image signatures for ghcr.io/olafkfreund/aifactory:sha-24184c6-gateway`. The existing test
`scripts/test-verify-no-provider-keys.sh` fakes `kubectl` with a PATH shim keyed on the exact argv string and
generates fixtures with a python heredoc; follow that pattern. Default context `${KUBE_CONTEXT:-k3d-factory}`.

## Steps

1. New `scripts/verify-gateway-policyreport.sh` and `scripts/test-verify-gateway-policyreport.sh`. Script:
   `set +x; set -u`, flag `--strict`, kubectl calls `--context "${KUBE_CONTEXT:-k3d-factory}" -n gateway get deploy
   model-gateway -o json` and `... get policyreport -o json`; print `<RESULT> <policy>/<rule> <kind>/<name> <UTC iso>`
   per row and `SUMMARY image=<ref> pass=N fail=N error=N image_pass=0|1 inspection_failed=0|1`; failures print
   `INSPECTION-FAIL <why>` plus the SUMMARY with `inspection_failed=1`; report mode exits 0, `--strict` exits 1 on
   inspection failure, any fail/error row, or `image_pass=0`. Never print message text beyond the policy/rule.
   Test cases (fixtures from a python heredoc): pass-for-image (strict 0), cache-only pass (strict 1), fail row (1),
   longer tag sharing the prefix (1), pass scoped to another resource and to a wrong UID (1), empty image (1),
   kubectl failure and malformed JSON (report 0 with INSPECTION-FAIL, strict 1), jq missing (as the existing test).
   → verify: `bash scripts/test-verify-gateway-policyreport.sh` and `shellcheck` on both files.
   Traps: names and counts only; no live cluster in the test; `shellcheck` clean; never `set -x`.
2. `scripts/verify-no-provider-keys.sh`: add `--deployments-json FILE` (usage line updated). With it: skip the
   kubectl presence check and both fetches, copy FILE to `$work/deploy.json`, write `{"items":[]}` as jobs, pass
   `--argjson static`, replace the `error("no Jobs")` branch so it triggers only when not static, print
   `static=1|0` at the end of SUMMARY. Missing/unreadable/empty/non-JSON FILE → `inspection_fail`. Extend
   `scripts/test-verify-no-provider-keys.sh`: clean static (exit 0, `static=1`, `jobs=0`), static with a violation (report
   exit 0, strict exit 1), bad FILE, and assert existing live cases still print `static=0`. The existing
   `check` helper expects the pattern `deployments=4 jobs=1` etc.; update those substrings only if the new
   suffix breaks them (it must not, since `static=` is appended after `inspection_failed=`).
   → verify: `bash scripts/test-verify-no-provider-keys.sh`; `shellcheck` on both.
   Traps: do not change classification rules; no secret value in output.
3. New `scripts/test-gateway-wiring.sh` (lead): `kustomize build` the four app dirs and
   `apps/factory-namespace/manifests`, convert with `yq -o=json`, assert with `jq` the spec's wiring facts for
   `aifactory|tfactory|cfactory`: `<SVC>_MODEL_GATEWAY_URL` from secretKeyRef `factory-secrets`/`MODEL_GATEWAY_URL` and
   `<SVC>_MODEL_GATEWAY_TOKEN` from `factory-secrets`/`MODEL_GATEWAY_CLIENT_TOKEN`, both `optional: true`, no literal; and the
   `factory-sandbox-jobs-egress` gateway peer (one peer with namespace+pod selector, TCP 8080 only, policy
   selects `factory.io/kind: task`). Include a negative self-check by mutating the JSON with jq and
   asserting the check fails. → verify: `bash scripts/test-gateway-wiring.sh`.
   Traps: kustomize v5.8.1 pin as in `manifest-validate`; yq is the mikefarah build preinstalled on runners.
4. `.github/workflows/model-gateway-tools.yml` (job `shell-tests`): add steps for the two new tests, the
   report-only static step: render `apps/{aifactory,pfactory,tfactory,cfactory}/manifests` with kustomize, keep
   only Deployments named aifactory, pfactory, tfactory, cfactory (drop `cfactory-frontend`), convert with
   `yq -o=json`, run `bash scripts/verify-no-provider-keys.sh --deployments-json F --accept-volume cli-creds`,
   print the SUMMARY and append it to `$GITHUB_STEP_SUMMARY`; if render, conversion or the script fails, or
   the output has `INSPECTION-FAIL`, emit `::warning::` and write "report unavailable" to the step summary;
   always exit 0; extend the shellcheck line; `docs/model-gateway.md`: section "Admission proofs (acceptance 5)" with
   the verifier, the dry-run deny and control commands, which message counts, and section "CI report and
   the `--strict` flip criterion": flip the static step to `--strict` (and add a live
   `--strict --accept-volume cli-creds --gateway-token-file` run) only when the live report shows
   `VIOLATION=0 UNVERIFIED=0` after stages 1 to 5 are verified through a full PARR run; stage 6 (provider-side
   rotation, owner-only) is not a condition; trim nothing else. → verify: `bash -n`, `actionlint` if available,
   YAML parse, and run the step's shell locally twice: normally, and with `kustomize` replaced by a failing
   shim, asserting the warning and the "unavailable" summary appear and the exit code is 0.
   Traps: no `paths:` filter (required-check rule in the workflow header); never `continue-on-error` hiding a real
   failure of the new tests; shellcheck `-x` not needed.

5. Live evidence (lead, read-only; no object is ever created, every apply is `--dry-run=server`): run
   `scripts/verify-gateway-policyreport.sh` and capture `image_pass=1`; count Pods in `gateway` before and
   after; server-side dry-run a Pod (`gateway` namespace, labels `app=model-gateway`, image
   `ghcr.io/olafkfreund/aifactory:sha-0202033`, expect denial by `verify-factory-image-signatures` "no signatures
   found") and the same spec with `sha-24184c6-gateway` (expect "created (server dry run)"). Post the output
   on #1959 with the PR link; tick no acceptance box. → verify: pod counts equal, outputs as stated.
   Traps: never run an apply without `--dry-run=server`; no Secret, restart, bench test or rotation.

## Tests

`bash scripts/test-verify-gateway-policyreport.sh`, `bash scripts/test-verify-no-provider-keys.sh`,
`bash scripts/test-gateway-wiring.sh`, `REQUIRE_KUSTOMIZE=1 bash scripts/test-gen-model-routes.sh`,
`bash scripts/test-verify-route-hot-reload.sh`, `shellcheck` on every script touched; then on the PR the
`model gateway tools` and `manifest-validate` checks green on the head SHA. Live, read-only: report mode of
the new script prints `image_pass=1`.

## Rollback

Revert the PR: only scripts, one workflow and docs change; nothing is deployed or applied. Argo CD
syncs `apps/` only and no `apps/` file is edited.
