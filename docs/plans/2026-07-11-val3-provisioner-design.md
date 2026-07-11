# VAL-3 Disposable-Target Provisioner — Design

> Status: Proposed | Created: 2026-07-11 | Issue: Factory #251 (under GTM hardening epic #241)
> Extends: RFC-0006 (VAL levels), RFC-0007 (access classes), RFC-0013 (deploy lane)
> Impl target: TFactory `apps/backend/` (agents + tools/runners)

## 1. Problem and current state

RFC-0006 defines VAL-3 as "it works applied against a disposable prod-like
target" with a mandatory cost guard and auto-teardown. The mechanism for this
is already fully built and wired in TFactory — but no concrete backend is
registered, so VAL-3 is honestly `not_run` on every run today.

What exists (all shipped, all tested):

| Piece | Where | Role |
|---|---|---|
| `DisposableTarget` protocol | `agents/disposable_target.py` | `.name`, `.run(cmd) -> (ok, output)`, idempotent `.teardown()` |
| Gate | `should_provision_val3()` | opens only when the profile declares effectful VAL-3 commands AND a backend is selected AND RFC-0007 access is provisioned AND target is not prod |
| Backend selection | `select_backend()` | env-driven: `local-vm` (`TFACTORY_VAL3_LOCAL_VM=1`) or `sandbox-cloud` (`TFACTORY_VAL3_CLOUD=<name>`), else None |
| Teardown guarantee | `disposable_target()` ctx manager | `finally` always calls `teardown()`, teardown never masks the body's exception |
| Orchestration | `attempt_val3()` / `record_val3()` | gate -> provision -> run commands -> teardown -> `findings/val3_outcome.json` |
| Call site | `agents/triager.py` (~line 1325) | called ONCE per verify run, best-effort, before the verification block is read |
| Honest reporting | `agents/val_block.py` | `Val3Outcome(ran=True)` flips VAL-3 to passed/failed; anything else stays `not_run` with reason; `DEFAULT_TARGET_LEVEL = "VAL-2"` |

The single gap: `_PROVISIONERS` is empty at runtime. `register_provisioner()`
is called only from `tests/test_disposable_target.py`. `select_backend()` can
return a name, but `_PROVISIONERS.get(backend)` is `None`, so the context
manager yields `None` and the caller keeps VAL-3 `not_run`. This document
designs the missing provisioner.

## 2. Design decision — a `k8s-job` backend first

The two backend names RFC-0006 anticipated do not fit the deployed reality:

- `local-vm` (QEMU/libvirt) cannot run inside the TFactory pod — k3d pods have
  no nested virtualization and no container runtime.
- `sandbox-cloud` means real spend and real credentials; it is the right
  second step, not the first.

The factory cluster itself IS a disposable prod-like target for the dominant
VAL-3 artifact class (`kubernetes` profile: "apply to ephemeral cluster +
assert ready", credential class C per RFC-0007). And TFactory already has a
proven ephemeral-k8s-Job substrate: `tools/runners/kube_sandbox.py`
(`KubeJobSandbox`, `build_job_manifest()`), which does create -> watch ->
logs -> delete on the Nix runner image with worktree co-mount.

So: add a third backend, `k8s-job`, selected by `TFACTORY_VAL3_K8S=1`, and
implement it as a thin adapter over `KubeJobSandbox`. `local-vm` and
`sandbox-cloud` remain valid names for later backends; the registry design
means adding them is a `register_provisioner()` call each.

Selection order in `select_backend()` becomes: `local-vm` > `k8s-job` >
`sandbox-cloud` > None (prefer-local per RFC-0006 section 4; `k8s-job` is
"local" for an in-cluster TFactory).

## 3. Provisioning flow

```
triager (once per verify run)
  record_val3(spec_dir, profile, access)
    should_provision_val3()          -- gate: commands + backend + access + not-prod
    disposable_target(spec)          -- ctx manager
      K8sJobTarget provisioner:
        1. derive run id: val3-<uuid8>
        2. create ephemeral namespace "val3-<uuid8>" (labels: app=tfactory-val3,
           tfactory/run=<spec-id>, tfactory/created=<ts>)
        3. return K8sJobTarget(name="k8s-job/val3-<uuid8>")
      for cmd in profile.levels.VAL-3.commands:
        target.run(cmd)              -- one KubeJobSandbox Job per command,
                                        namespace=val3-<uuid8>, worktree co-mounted
                                        rw at /work, nix develop toolchain
        stop on first failure
    finally: target.teardown()       -- delete namespace (cascades Jobs/pods/
                                        services/PVC-less resources); idempotent;
                                        never raises
  write findings/val3_outcome.json   -- {ran, passed, reason}
val_block.read_verification_block()  -- VAL-3 passed/failed/not_run, never overclaimed
```

`K8sJobTarget` sketch (the whole deliverable is roughly this):

```python
class K8sJobTarget:
    name: str  # "k8s-job/val3-ab12cd34"

    def run(self, command, *, timeout=600.0):
        res = self._sandbox.run([command], workdir=self._workdir,
                                timeout=int(timeout))
        return res.ok, res.output

    def teardown(self):  # idempotent, never raises
        delete_namespace(self._namespace)  # best-effort, swallow + log
```

Why namespace-per-run rather than labeled resources in `factory`:

- teardown is ONE call with cascade semantics — nothing enumerable to miss;
- a leaked run is visible as a whole namespace (`kubectl get ns -l
  app=tfactory-val3`), trivially sweepable;
- the applied artifact (the thing under test) cannot collide with factory
  services or a concurrent VAL-3 run.

## 4. Teardown guarantees (layered)

1. **Context manager `finally`** (exists): `disposable_target()` always calls
   `teardown()`, even when a command raises; teardown exceptions are logged,
   never propagated.
2. **Per-Job `ttlSecondsAfterFinished` + `activeDeadlineSeconds`** (exists in
   `build_job_manifest()`): even if TFactory dies mid-run, each Job self-limits
   and self-GCs.
3. **Namespace deletion cascade** (new): everything the VAL-3 commands created
   inside the namespace dies with it — including resources the commands applied
   that TFactory never knew about (the reason labeled-cleanup is not enough).
4. **Orphan sweeper** (new, small): TFactory pod restart between provision and
   teardown leaks a namespace. A sweep at backend startup (and/or a CronJob)
   deletes any `app=tfactory-val3` namespace older than
   `TFACTORY_VAL3_MAX_AGE_SECONDS` (default 1800). This is the same pattern as
   `ttlSecondsAfterFinished`, one level up.

Rule carried from run-aws-demo: teardown is unconditional and ordered; a
failed VAL-3 run still tears down, and a failed teardown is loud (error log +
sweeper backstop), never silent.

## 5. Cost guards

Phase 1 (`k8s-job`, local cluster) has no cloud spend; the guards bound
cluster resource burn:

- **Wall clock**: per-command timeout (the protocol's `timeout` param, default
  600s) enforced as the Job's `activeDeadlineSeconds`; plus a total budget
  `TFACTORY_VAL3_BUDGET_SECONDS` (default 1200) across all commands — when
  exceeded, remaining commands are skipped and the outcome is
  `ran=True, passed=False, reason="VAL-3 budget exhausted"`.
- **Compute**: requests == limits on every Job (exists in
  `build_job_manifest()`; default 2 CPU / 4Gi) — a guaranteed, capped
  reservation, no oversubscription.
- **Concurrency**: `record_val3()` runs once per verify run by construction;
  namespace-per-run isolates concurrent runs. Optional
  `TFACTORY_VAL3_MAX_CONCURRENT` (default 1) refuses the gate when N runs are
  already live (count of `app=tfactory-val3` namespaces).
- **Blast radius**: the Job pod has `automountServiceAccountToken: false`;
  the RBAC the provisioner itself needs (create/delete namespace, create Job)
  is granted to the TFactory service account, scoped by a label-selector-free
  but name-prefix-conventioned policy (see open question 3).

Phase 2 (`sandbox-cloud`) inherits the run-aws-demo pattern: dedicated sandbox
account only, everything tagged with the run id, teardown in dependency order,
a hard budget ceiling checked before provision, and refusal (honest `not_run`)
when the budget or credentials are absent. Out of scope for this design's
first implementation.

## 6. Integration seams

- **Registration**: `register_provisioner("k8s-job", provision_k8s_job_target)`
  at TFactory backend startup (app factory / lifespan), gated on
  `TFACTORY_VAL3_K8S=1`. No registration -> behavior is exactly today's
  honest `not_run`. Rollout is an env flip in the Helm values, no code path
  change for anyone not opted in.
- **Contract (RFC-0002 / hub `scripts/verification_profiles.py`)**: the
  profile reaches `record_val3()` via the run's source metadata
  (`_load_source_meta(spec_dir)["verification"]`). No contract change needed;
  the `kubernetes` profile's VAL-3 entry (`requires: ["sandbox_cluster"]`) is
  satisfiable the moment the backend registers. Placeholder commands (e.g.
  ansible's `<sandbox-inventory>`) need concretization — open question 4.
- **Access (RFC-0007)**: `k8s-job` on the local cluster is Class C
  (ephemeral target the pipeline owns) — no external credential, which is why
  it is the right first backend. External clusters would ride the existing
  `sandbox_credentials.py` kubeconfig materialization (0600, read-only mount,
  wiped after run); not needed for phase 1.
- **Deploy lane (RFC-0013)**: unchanged and complementary. The deploy lane is
  DRY-RUN by design (`assert_dry_run` hard-errors on effectful tokens) and maps
  to VAL-0/VAL-2. VAL-3 is the step above it: a REAL apply, but only inside the
  disposable namespace this provisioner owns. The deploy lane's production
  guard is not weakened — the effectful commands run only through
  `disposable_target()`, never through `run_deploy_lane()`.
- **Reporting (RFC-0006)**: zero changes. `val_block.py` already renders a
  genuine `Val3Outcome(ran=True)`; CFactory already surfaces
  `achieved_level` + gaps. The first green run flips the tile from
  "VAL-2, VAL-3 not_run (no disposable sandbox target)" to "VAL-3 passed"
  with no consumer work.
- **Substrate reuse**: `KubeJobSandbox` is used as-is except one addition —
  `namespace` is already a constructor arg; the provisioner passes the
  ephemeral one. Worktree co-mount uses the existing `repo_pvc`/`pvc_subpath`
  mechanics (single-node caveat below).

## 7. Phasing

1. **`K8sJobTarget` + provisioner + registration** (TFactory): adapter class,
   namespace lifecycle, `select_backend()` learns `k8s-job`, startup
   registration behind `TFACTORY_VAL3_K8S`, budget guard, startup sweeper.
   Unit tests: manifest/namespace purity, teardown idempotence, budget
   exhaustion, sweeper age math. Effort: M.
2. **Live proof**: one effectful `kubernetes`-profile contract (apply a
   Deployment + assert ready) reaching `achieved_level="VAL-3"` on the factory
   cluster, namespace verified gone afterwards; assert `val3_outcome.json` and
   the CFactory tile. Effort: S.
3. **Profile concretization**: define how VAL-3 command placeholders are
   resolved per artifact type (kubernetes first; ansible inventory generation
   later). Effort: S-M.
4. **`sandbox-cloud` backend** (deferred): run-aws-demo cost-guard pattern,
   RFC-0007 Class A credentials. Separate design when demanded.

## 8. Open questions

1. **Multi-node worktree co-mount.** `KubeJobSandbox`'s repo co-mount relies on
   the Job landing on the node holding the RWO workspaces PVC (true on
   single-node k3d; known blocker Factory #190 for packed multi-node). VAL-3
   Jobs inherit this. Acceptable for phase 1; the MinIO repack fix designed for
   packed-path output propagation is the eventual shared answer.
2. **Namespace creation RBAC.** Namespace-scoped Roles cannot grant namespace
   creation; TFactory's service account needs a small ClusterRole
   (create/delete namespaces + create Jobs in them). Is cluster-admin-adjacent
   RBAC acceptable on the factory cluster, or should a tiny privileged
   "val3-provisioner" controller own it instead? Proposed: direct ClusterRole,
   name-prefix `val3-` enforced in code, revisit if the cluster is ever shared.
3. **Assert-ready semantics.** "apply + assert healthy" needs a convention:
   proposed `kubectl rollout status` + optional profile-declared assert
   commands, all running inside the same namespace-scoped Job. Does the
   contract need an explicit `asserts` list next to `commands`, or are trailing
   commands enough? Proposed: trailing commands are enough; no schema change.
4. **Placeholder commands.** Profiles carry human-shaped VAL-3 commands
   (`ansible-playbook -i <sandbox-inventory>`). Who concretizes them — the
   planner (PFactory, at contract time, per RFC-0006 section 6) or the
   provisioner (TFactory, from the target it just built)? Proposed: the
   provisioner exposes target facts (namespace, kubeconfig context, inventory
   path) as env vars to the Job; the planner writes commands against those
   documented names.
5. **Failed-teardown escalation.** Today a failed teardown is an error log +
   sweeper backstop. Should it also flag the run (a `finding`) so a leak is
   user-visible in the cockpit? Proposed: yes, cheap and honest — but not
   blocking for phase 1.
6. **`local-vm` backend.** QEMU/libvirt is infeasible in-pod; it would only
   ever run in a host-mode TFactory deployment. Keep the name reserved, build
   nothing until such a deployment exists.

## 9. What this design deliberately does not do

- No cloud spend, no external credentials, no MFA surface (all Class C).
- No contract/schema changes; no CFactory changes; no val_block changes.
- No weakening of the RFC-0013 production guard — VAL-4 remains never-run.
- No speculative multi-backend framework beyond the registry that already
  exists: one backend, registered behind one env flag.
