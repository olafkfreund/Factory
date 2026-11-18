---
status: draft
issue: 1959
intent: intent/2026-11-18-1959-gateway-gitops-proofs.md
---

# Spec: gateway admission proofs, client wiring check, provider-key report in CI

All code is in olafkfreund/factory-gitops (base `main`); artifacts are here in the hub.

## Design

**1. `scripts/verify-gateway-policyreport.sh [--strict]`** (new, same style as `verify-no-provider-keys.sh`:
`set +x`, context `${KUBE_CONTEXT:-k3d-factory}`, names and counts only).
Reads `kubectl -n gateway get deploy model-gateway -o json` (the image) and
`kubectl -n gateway get policyreport -o json`. For every result row it prints
`<RESULT> <policy>/<rule> <resource-kind>/<name> <UTC time from results[].timestamp.seconds>` and ends with
`SUMMARY image=<ref> pass=N fail=N error=N image_pass=0|1 inspection_failed=0|1`.
`image_pass=1` only when all hold: the Deployment image is non-empty; the row is `pass` from policy
`verify-factory-image-signatures`; its report's `scope` is `Deployment/model-gateway` with `scope.uid` equal
to the Deployment's `metadata.uid` (the current object, not another resource using the same image); and the
row message contains the image reference as a whole token (followed by end of text or a delimiter, so
`...:sha-24184c6-gateway-other` does not match). Cache-hit rows say "verified from cache", name no image,
and do not count. Fixtures cover a longer tag with the same prefix, a PASS scoped to another resource or UID,
and a missing image. Report mode always exits 0 and prints `INSPECTION-FAIL <why>` when kubectl or jq is
missing or the JSON is not a list. `--strict` exits 1 on inspection failure, on `fail`/`error` rows, or
without `image_pass=1`. Skip rows (the first-party coverage rule, "preconditions not met") are printed, not counted.

**2. Deny and control procedure (docs/model-gateway.md, new section "Admission proofs").** A Pod in
namespace `gateway` whose image is `ghcr.io/olafkfreund/aifactory:<tag>`, applied only with
`kubectl apply --dry-run=server`, never without it. Control: tag `sha-24184c6-gateway` is admitted
("created (server dry run)"). Deny: an existing tag with no cosign signature (`sha-0202033`) is rejected
with `verify-factory-image-signatures ... no signatures found`. A missing tag is also rejected but with
"manifest unknown", which proves less, so the doc names which message counts. Both observed live on
2026-11-18; the doc checks the pod count in `gateway` before and after (unchanged).
Evidence is pasted into #1959; no acceptance box is ticked (the PASS and deny proofs are live, but
acceptance 5 also lists the report timestamps and the epic stays open for owner-only items).

**3. `verify-no-provider-keys.sh --deployments-json FILE`** (small edit). Static mode: Deployments come
from FILE (`{"items":[...]}`), no kubectl, Jobs are not fetched, the "no Jobs" error is skipped, and
the summary ends with `static=1` (live runs print `static=0`). The classification jq is reused unchanged.
A missing, empty or malformed FILE is `INSPECTION-FAIL`. Live behaviour without the flag is unchanged.

**4. CI (`.github/workflows/model-gateway-tools.yml`, existing `shell-tests` job).** Adds the policy-report
test and the static report step. The report step renders `aifactory pfactory tfactory cfactory` with the
already-installed kustomize, keeps the Deployments named in the script's own list (`cfactory-frontend` is
not a model client), converts with `yq -o=json`, runs the script in report mode with
`--accept-volume cli-creds`, prints its SUMMARY, and writes it to `$GITHUB_STEP_SUMMARY`. The step is one
shell block where each stage (render, convert, inspect) is checked: any failure, or `INSPECTION-FAIL` in
the output, emits a `::warning::` plus an "unavailable" line in the step summary and the step still
exits 0, so a failed inspection is never read as a zero count and never blocks. shellcheck covers the new scripts.

**5. Wiring guard `scripts/test-gateway-wiring.sh`** (cluster-free, in the same job). From the rendered
manifests assert: `aifactory`, `tfactory`, `cfactory` each carry `<SVC>_MODEL_GATEWAY_URL` from
`factory-secrets/MODEL_GATEWAY_URL` and `<SVC>_MODEL_GATEWAY_TOKEN` from
`factory-secrets/MODEL_GATEWAY_CLIENT_TOKEN`, both `optional: true` and neither a literal; the
`factory-sandbox-jobs-egress` policy has one egress peer selecting namespace `gateway` AND pod
`app=model-gateway` together, on TCP 8080 only; the Job selector is `factory.io/kind=task`. Live check
already done: all three Deployments have the six env vars, the live policy carries the peer, so no
fix is needed today.

**6. Flip criterion (docs).** CI stays report-only. Flip the static step to `--strict` (and add the live
run `--strict --accept-volume cli-creds --gateway-token-file`) only when the live report shows
`VIOLATION=0 UNVERIFIED=0` after epic stages 1 to 5 are verified through a full PARR run; stage 6
(provider-side rotation) is owner-only and is not a condition for the flip.

## Alternatives rejected

- Give CI cluster credentials to run the live verifiers: widens the blast radius of a public repo's CI.
- Count PASS rows by pod name instead of image: a cache-hit PASS names no image and would pass an
  unrelated image.
- Prove the deny by deploying an unsigned Pod for real: creates a live object; server-side dry-run
  reaches the same Kyverno verification with no object.
- Make the static step blocking now: 18 live violations are expected until the migration is done.

## Risks

- Kyverno dry-run behaviour depends on the webhook honouring dry-run; observed to work live. If a later
  Kyverno upgrade changes that, the procedure fails closed (no output), not open.
- Static count (Deployments only) differs from the live count (Deployments plus Jobs); the `static=1`
  label and the docs say so.
- A signature-cache hit can make a report row carry no image name; strict mode keys on the
  Deployment-scoped row (matched by UID) and the script prints all rows so the gap is visible. After a
  rollout the new Deployment report may take a moment to appear; strict then fails closed.

## Verification

- `bash scripts/test-verify-gateway-policyreport.sh`, `test-verify-no-provider-keys.sh` (new static cases),
  `test-gateway-wiring.sh`, shellcheck, the CI workflow green on the PR head.
- Live read-only: script run in report mode shows `image_pass=1`; dry-run deny and control output pasted
  on #1959 together with the pod count before and after.
