---
status: draft
issue: olafkfreund/AIFactory#2126
spec: spec/2026-11-18-2126-agent-job-serviceaccount.md
coders:
  1: lead    # gitops manifests, I run the validators
  2: lead    # kyverno fixtures: tied to step 1 checks
  3: codex   # contained Python edit plus tests in AIFactory: small tricky logic
  4: lead    # env flip in its own PR, merged last
reviewers:
  - codex    # read-only review of each draft and of each final diff
---

# Plan: agent Jobs get their own ServiceAccount

Approved decisions (spec): SA `aifactory-agent-job` (token-less, no Role) for
spec / apply-correction / PR-review / clarification Jobs; SA `aifactory-build-job`
with a copy of the three `aifactory-sandbox` Role rules for the build Job (it
creates gate Jobs); control plane keeps `aifactory-sandbox`. New env
`AIFACTORY_JOB_SA` (fallback `AIFACTORY_BUILD_SA`, then `aifactory-sandbox`);
default-compatible. NetworkPolicy and Kyverno gate select on the label, no
policy change. Distinct runAsUser deferred (PVC files owned by 65532).
Merge order: PR A (steps 1-2, factory-gitops), PR B (step 3, AIFactory),
PR C (step 4, factory-gitops env flip). Artifacts: PR D in Factory.

## Steps

1. factory-gitops `apps/aifactory/manifests/manifests.yaml`, after the
   `aifactory-sandbox` RoleBinding (~line 900): add SA `aifactory-agent-job`
   (`automountServiceAccountToken: false`), SA `aifactory-build-job`, Role and
   RoleBinding `aifactory-build-job` with the same rules as `aifactory-sandbox`.
   → verify: kustomize build apps/aifactory/manifests | kubeconform -strict
   -ignore-missing-schemas, and the automount gate script in manifest-validate.yml.
   Traps: no pod references the new SAs yet; keep labels consistent.
2. factory-gitops `apps/kyverno-policies/tests/`: add pod `task-agent-job-sa`
   (label factory.io/kind: task, serviceAccountName aifactory-agent-job) to
   `resources-gate-task-pods-on-network-policy.yaml`, its gated twin to
   `patched-gate-task-pods-on-network-policy.yaml`, and it to the `inject-netpol-gate`
   pass list and `ensure-init-containers-array` pass list in
   `kyverno-test-gate-task-pods-on-network-policy.yaml`.
   → verify: kyverno test apps/kyverno-policies/tests -f kyverno-test-gate-task-pods-on-network-policy.yaml
   The CLI has no local install and v1.18.2 panics on the policy's
   `webhookConfiguration.matchConditions`: CI strips that field from a copy
   (manifest-validate.yml ~995-1083) before running; the committed policy is not
   edited. The CI job is the authority for this step.
   Traps: patched file must be byte-identical in the gate body to the other patched pods.
3. AIFactory `apps/web-server/server/services/build_backend.py` (near
   `_ENV_SERVICE_ACCOUNT`, ~169/202): add `_ENV_JOB_SERVICE_ACCOUNT =
   "AIFACTORY_JOB_SA"` and `_job_service_account()` (JOB_SA, else BUILD_SA, else
   default; strip, blank = unset). `spec_job_backend.py` (~82) and
   `agent_job_backend.py` (~75): call it instead of the inline BUILD_SA read.
   Build Job path unchanged. Tests in `tests/test_build_backend_kubejob.py` (and
   `tests/test_spec_job_backend.py` and `apps/web-server/tests/test_agent_job_backend.py`): BUILD_SA only -> all three use it;
   JOB_SA set -> spec/agent use it, build keeps BUILD_SA; nothing set ->
   `aifactory-sandbox`; spec/agent pod `automountServiceAccountToken is False`.
   Docs: row for `AIFACTORY_JOB_SA` in `docs/docs/environment-reference.md` and a
   comment line in `apps/web-server/.env.example`.
   → verify: pytest on those three files in the project venv (the web-server
   test dir needs `-o asyncio_mode=auto`, as ci.yml:218), ruff check/format --check,
   and `python3 scripts/cq_ratchet.py --base origin/dev --ruff <ruff> --config
   standards/ruff.toml --paths 'apps/backend/*.py' 'apps/web-server/*.py' 'scripts/*.py'`.
   Traps: ruff and standards/ruff.toml disagree on "as" aliases in parenthesised
   imports: use plain names. Do not touch vendored job_dispatch.py (byte-checked).
4. factory-gitops (new branch off main, PR C): on the aifactory Deployment env
   add `AIFACTORY_BUILD_SA=aifactory-build-job` and
   `AIFACTORY_JOB_SA=aifactory-agent-job` next to `AIFACTORY_SANDBOX_REPO_PVC`
   (~line 465), commented with the merge-order requirement.
   → verify: same validators as step 1.
   Traps: merge only after PR A is synced and PR B is released; flipping early
   fails every Job create.

## Tests

- AIFactory: pytest of the touched test files; `python3 apps/backend/core/job_dispatch.py` (selftest, must still pass).
- factory-gitops: kustomize + kubeconform, kyverno test with `-f` for the gate suite.
- Final: `codex review --base origin/<base>` per repo.

## Rollback

Unset the two env vars (or revert PR C); Jobs return to `aifactory-sandbox`,
which is unchanged. The new SAs are harmless unreferenced; revert PR A to remove.
