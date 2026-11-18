---
status: draft
issue: olafkfreund/AIFactory#2126
author: olafkfreund
---

# Intent: agent Jobs get their own ServiceAccount

## Problem

After the isolation work (AIFactory#1930-#1932, #2095) the build, spec and
apply-correction (#2116) Jobs still run as the `aifactory-sandbox`
ServiceAccount, the identity the control plane runs as. That SA is bound to a
Role that can create and delete Jobs and read pods and logs. Spec and
apply-correction Jobs do not mount the token, but the identity and its
binding are shared (the build Job mounts it when it dispatches gate Jobs), so any future change that mounts a token, or any API-side
audit rule, treats untrusted agent code and the control plane alike. The uid
(65532) is shared too.

## Proposed outcome

Two new SAs in factory-gitops, so no agent Job runs as the control plane:

- `aifactory-agent-job` for the spec and apply-correction Jobs: no Role, no
  RoleBinding, no token mount. These Jobs need no API access.
- `aifactory-build-job` for the build Job. The build Job is the one exception
  (Codex review): when sandbox gates run as Jobs (`AIFACTORY_SANDBOX_GATES`,
  backend `nixjob`, as deployed) it mounts a token and creates the gate Jobs
  itself (build_backend.py `_gates_dispatch_jobs`, kube_sandbox.py). So it gets
  its own SA with exactly the dispatch Role the control plane SA has today, no
  more. Making builds tokenless would need a different gate-dispatch design and
  is out of scope.

The control plane keeps `aifactory-sandbox`. Until the SAs exist and the env is
flipped nothing changes: AIFactory defaults to the current SA.

## Affected users and systems

factory-gitops `apps/aifactory` (new SAs and Role, env on the Deployment) and
`apps/kyverno-policies` tests; AIFactory Job builders (one new env `AIFACTORY_JOB_SA`, tests).

## Constraints

- Merge order: SA in gitops first, then the AIFactory change, then the env flip.
  Flipping the env before the SA exists would fail every Job at admission.
- Do not break workspace writes: a different runAsUser is out of scope unless
  the PVC ownership allows it.
- No live-cluster action in this work; Argo CD syncs the merged manifests.

## Open questions

None. Decision taken under the owner's delegation: keep the existing
`AIFACTORY_BUILD_SA` for builds, add `AIFACTORY_JOB_SA` for tokenless Jobs;
defer a distinct uid (workspace files are owned by 65532).
