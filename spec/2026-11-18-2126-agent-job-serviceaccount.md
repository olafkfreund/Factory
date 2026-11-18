---
status: draft
issue: olafkfreund/AIFactory#2126
intent: intent/2026-11-18-2126-agent-job-serviceaccount.md
---

# Spec: agent Jobs get their own ServiceAccount

## Design

factory-gitops (`apps/aifactory/manifests/manifests.yaml`, next to the existing
`aifactory-sandbox` SA/Role/RoleBinding):

- SA `aifactory-agent-job`: `automountServiceAccountToken: false`, no Role, no
  RoleBinding. Used by the spec and apply-correction Jobs.
- SA `aifactory-build-job` with a Role and RoleBinding copying the three rules
  of `aifactory-sandbox` (jobs create/get/list/watch/delete, pods
  get/list/watch, pods/log get). The build Job dispatches gate Jobs through the
  API; this keeps that working under its own identity. The rules are copied, not
  narrowed. Codex read of kube_sandbox.py shows the gate path uses only jobs
  create/get/delete, pods list and pods/log get (watch unused), but other
  code in the build pod was not audited; narrowing is a recorded follow-up.
- Phase 2 (separate PR, merged last): on the aifactory Deployment set
  `AIFACTORY_BUILD_SA=aifactory-build-job` and `AIFACTORY_JOB_SA=aifactory-agent-job`.

AIFactory (`apps/web-server/server/services`):

- `build_backend._job_service_account()` returns `AIFACTORY_JOB_SA` if set, else
  `AIFACTORY_BUILD_SA`, else `aifactory-sandbox`. `spec_job_backend` and
  `agent_job_backend` (apply-correction, PR-review and clarification Jobs) call it instead of reading `AIFACTORY_BUILD_SA`. The build
  Job keeps reading `AIFACTORY_BUILD_SA`. Both Jobs keep their token behaviour
  (spec and agent Jobs: `automount_service_account_token=False` already; the
  build Job: mounted only when gates dispatch Jobs).
- Default-compatible: with neither new env set every Job gets today's SA.
- Tests: SA override and fallback for the three builders; automount false on
  spec and agent Jobs; default unchanged. Docs: environment-reference row.

Admission: the sandbox NetworkPolicy and the `gate-task-pods-on-network-policy`
Kyverno policy match the label `factory.io/kind: task`, not the SA, so neither
policy changes. A Kyverno CLI test case with a pod using the new SA pins that
the gate is still injected.

Deferred, documented follow-up: a distinct `runAsUser` for Jobs. Workspace and
worktree files on the shared PVC are created by the control plane as 65532 and
Jobs write them, so changing the Job uid would break workspace writes.

## Alternatives rejected

- One new SA for all three Jobs, tokenless: breaks gate dispatch from builds
  (found in Codex review of the intent).
- Narrowing the build Role now: only the gate path is audited; a wrong guess breaks every build.
- A new setting that replaces `AIFACTORY_BUILD_SA`: breaks anyone using it.
- Selecting Kyverno/NetworkPolicy by SA: they are label-based on purpose
  (Factory#502).

## Risks

- Env flipped before the SAs sync: Job creation fails ("serviceaccount not
  found"). Mitigated by merge order and a separate env PR.
- Role copy drifts from `aifactory-sandbox`: accepted; follow-up to narrow.
- Existing deployments that set `AIFACTORY_BUILD_SA` to a custom SA now also
  apply it to spec/agent Jobs (unchanged behaviour via the fallback).

## Verification

- AIFactory: pytest for the three builders (new tests in
  `tests/test_build_backend_kubejob.py` and siblings), `job_dispatch` selftest.
- factory-gitops: `kyverno test apps/kyverno-policies/tests -f kyverno-test-gate-task-pods-on-network-policy.yaml`
  (input pod, expected patched pod and result entry for the new SA), kustomize build +
  kubeconform as in `manifest-validate.yml`, the automount expected-value gate.
- After deploy (owner or coordinator, not in this change): a spec Job's pod has
  `serviceAccountName: aifactory-agent-job` and no token volume.
