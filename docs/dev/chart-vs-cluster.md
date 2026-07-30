# Two deployment engines: the service charts and the reference cluster

- **Issue:** Factory#499
- **Applies to:** `AIFactory/charts/aifactory`, `TFactory/charts/tfactory`, `PFactory/charts/pfactory`, `CFactory/charts/cfactory`, and `factory-gitops/apps/*/manifests/`
- **Measured:** 2026-07-30, against the charts at each service's `dev` and gitops at `main`

## The rule

**A change to a service Helm chart does not reach the reference cluster.**

The four services each ship a Helm chart. None of them deploys anything here. The ArgoCD
Application for each service points at `factory-gitops/apps/<svc>/manifests`, a
hand-written plain-manifest directory, so `charts/` is never rendered against this
cluster. The charts are the self-host install path and are exercised only by their own
CI.

Both directions are silent. A chart can gain a control the cluster does not have, and
the gitops manifests can gain one the chart does not, and nothing compares them.

If you are adding a hardening control, you must decide which engine you are targeting,
and say so in the PR. If it must apply here, it goes in `factory-gitops`. If it is for
self-hosters, it goes in the chart — and the issue that closes must not claim the
cluster got it.

## Why the charts are not simply dead code

They are tested, shipped artifacts with a real audience:

- AIFactory: `tests/helm/` holds 15 toggle suites plus a kind-based `helm (P4 acceptance)`
  CI job that renders the chart and asserts against it.
- TFactory and PFactory: `helm` is installed in `ci.yml` and the chart is rendered there.
- The product docs ship a Helm install guide and an upgrade runbook.

So "delete the templates" would destroy a working install path to fix a labelling
problem. The charts are honest for their own audience. What was dishonest is the
fleet-facing reading: PRs and closing issues that describe a chart change as though the
cluster received it.

## Inventory: what the charts have that the cluster does not

Method: `helm template <chart> --namespace factory` with default values, versus
`apps/<svc>/manifests/*.yaml` at gitops `main`, cross-checked against the live cluster
with `kubectl --context factory -n factory`.

### Resource-set differences

| Resource | Chart (default values) | gitops / live cluster |
|---|---|---|
| `ConfigMap <svc>-config` | all four charts | **absent** — env is inlined into the Deployment |
| `ServiceAccount <svc>` | all four charts | **absent** — only `aifactory-sandbox`, `tfactory-sandbox`, `tfactory-deploy-dryrun` exist |
| `PodDisruptionBudget <svc>` | aifactory, tfactory, pfactory | **absent** — `get pdb` returns nothing in the namespace |
| `NetworkPolicy <svc>` (control plane) | aifactory, tfactory, pfactory | **absent** |
| `NetworkPolicy aifactory-tasks` | aifactory (default-on) | **absent** — see below |
| `NetworkPolicy tfactory-job-pods` | tfactory (default-on) | **absent** — see below |
| `Role`/`RoleBinding <svc>-sandbox` | tfactory only | present for aifactory **and** tfactory |
| `PersistentVolumeClaim <svc>-data` | absent at default values | present for all four |
| `Deployment`, `Service` | all four | all four |

Default-off chart templates, listed for completeness — dead here *and* opt-in there, so
lower risk, but still not a deployment path: `hpa.yaml`, `servicemonitor.yaml`,
`ingress.yaml`, `externalsecret.yaml`, `postgres-bundled.yaml`, `workspaces-pvc.yaml`
(all four charts); `cronjob-audit-anchor.yaml`, `grafana-dashboard-configmap.yaml`,
`teardown-cron.yaml`, `pre-install-cni-probe.yaml`, `rbac/tenant-reconciler-rbac.yaml`
and the four `gatekeeper/` constraints (aifactory); `regression-cronjob.yaml`,
`sandbox-rbac.yaml` (tfactory).

Autoscaling is the one case where the cluster has *more*: the charts' `hpa.yaml` is
default-off and unused, while the cluster scales via KEDA `ScaledObject`s
(`get scaledobject` shows aifactory/pfactory/tfactory), which no chart models.

### Field-level differences on the shared `Deployment`

This is the larger gap, and it is invisible to any resource-name comparison. Identical in
all four services:

| Field | Chart | gitops / live |
|---|---|---|
| pod `securityContext` | `fsGroup`, `runAsUser: 65532`, `runAsGroup: 65532`, `runAsNonRoot: true`, `seccompProfile: RuntimeDefault` | `fsGroup: 65532` **only** |
| app container `securityContext` | `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `readOnlyRootFilesystem: true`, `runAsNonRoot: true`, `runAsUser: 65532`, `seccompProfile: RuntimeDefault` | **null — no securityContext at all** |
| env | `envFrom` the `<svc>-config` ConfigMap (3-5 vars) | 15-57 inline `env` entries, no `envFrom` |
| credential plumbing | none | `seed-creds` initContainer, `cred-sync` sidecar, and the `cc-claude`/`cc-codex`/`cc-gemini`/`cc-config`/`cli-creds` volumes |
| rollout | `maxSurge: 0, maxUnavailable: 1` (or `Recreate` for cfactory) | `maxSurge: 1, maxUnavailable: 0` |
| serviceAccountName | `<svc>` | `<svc>-sandbox`, or unset for pfactory/cfactory |

Verified live:

```
$ kubectl --context factory -n factory get pod -l app=aifactory \
    -o jsonpath='{.items[0].spec.securityContext}{"\n"}{range .items[0].spec.containers[*]}{.name}{" -> "}{.securityContext}{"\n"}{end}'
{"fsGroup":65532}
cred-sync -> {"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}}
aifactory ->
```

The control-plane pods run with no container `securityContext` while every chart claims
a fully hardened one. Tracked in Factory#503.

**This one is not caused by the two-engine split, and it is worth saying so.** The obvious
reading — "charts are never rendered, so the hardening never arrived" — does not survive
checking. Every CronJob in the same namespace, deployed by the same GitOps engine from the
same kind of hand-written plain manifest, carries the full set:

```
$ kubectl --context factory -n factory get cronjob argocd-drift -o jsonpath='...'
{"runAsNonRoot":true,"runAsUser":65532,"seccompProfile":{"type":"RuntimeDefault"}}
drift -> {"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true}
```

Same for `audit-anchor-alert`, `audit-siem-forward`, `endpoint-guard`, `cred-broker`,
`evidence-collector`. Plain manifests carry hardening perfectly well. The CronJob manifests
were authored hardened and the four service Deployment manifests never were — an older,
separate gap that #499 did not cause and that fixing #499 will not close. Do not cite the
two-engine split as its remediation.

The general point: a real divergence and a plausible cause for it are two findings, not
one. This document is about a failure to check, so the standard applies to it too — and it
had to be applied twice while this document was being written, once to a stale source read
reported as live fact, and once to the causal claim above. Both times a plausible story ran
ahead of a verification, on adjacent halves of the same problem, hours apart. That is a
property of this kind of work, not of whoever happened to make the error, which is why the
gate in #504 is worth more than either correction.

The `cred-sync` sidecar and the 57 inline env vars are also why "point ArgoCD at the
chart" is not a small change: the chart models none of that, so rendering it would remove
the credential plumbing the whole fleet runs on.

### The NetworkPolicy case, in full

The two per-task policies are the reason #499 was filed, and they are the clearest
example of the failure mode.

- `AIFactory charts/aifactory/templates/networkpolicy-tasks.yaml` — `networkPolicy.enabled: true`
  and `networkPolicy.tasks.enabled: true`, both default. Selects `factory.io/kind: task`.
- `TFactory charts/tfactory/templates/networkpolicy-jobs.yaml` — `networkPolicy.enabled: true`
  and `networkPolicy.jobPods.enabled: true`, both default. Selects `app: tfactory-sandbox`.

Both cite real issues (TFactory#651, AIFactory#812, Factory#274), both are well reasoned,
and both closed hardening issues that read as though the cluster was covered. Neither has
ever been evaluated here.

Independent evidence that they had never been rendered against this cluster: both allow
`443/tcp` on `0.0.0.0/0` with `except: [10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16]`,
while the fleet-wide `OPENAI_COMPATIBLE_BASE_URL` is `http://host.k3d.internal:11434` —
`172.18.0.1`, plain HTTP, non-443, inside the excluded range. Applying either as written
would have failed the self-host model path closed on the first task. Nobody noticed,
because nobody ever applied them. (The policy that gitops *did* apply under Factory#462
carries an explicit `172.18.0.1/32:11434` rule — that lesson was learned the second time,
against the engine that actually runs.)

Note for self-hosters: `networkPolicy.tasks.egress.extraRules` (AIFactory) and
`networkPolicy.jobPods.extraEgressRules` (TFactory) are the supported escape hatch for a
model endpoint on a private address or a non-443 port. The default rule does not cover it.

## Why not the three options as filed

**1. Render the charts via an ArgoCD Helm source.** Not viable as the charts stand. The
live Deployments carry a `seed-creds` initContainer, a `cred-sync` sidecar, five
credential volumes and 15-57 inline env vars; the charts model none of it. Switching the
source would delete the credential plumbing the fleet depends on. This is the honest
end-state, but it is a migration, not a fix.

**2. Delete the superseded templates.** Wrong target. The templates are not superseded —
they are the self-host path, they are CI-tested, and they are documented in the product
install guide. Deleting them removes a working artifact and loses the reasoning in it.

**3. Add a chart-vs-manifests drift gate.** A gate that diffs the full resource set would
be red on day one and stay red, because the two engines legitimately differ (the table
above). A gate comparing a defined *control subset* — securityContext, NetworkPolicy
coverage, PDB — would be useful, but it needs that subset agreed first. Filed as
Factory#504.

**What was done instead:** state the rule once, here; correct the compliance evidence
that cited chart templates as deployed controls; and file the substantive gaps the
inventory exposed rather than paper over them.

## Open issues from this inventory

| Issue | Gap |
|---|---|
| Factory#502 | Two of four per-task lanes are matched by no live NetworkPolicy. The applied policy enumerates `app in (aifactory-sandbox, tfactory-sandbox)`; the two `job_dispatch.py` lanes label their pods `<svc>-task` via `task_pod_labels()`'s default `role="task"` and are uncovered. `factory.io/kind: task` is the durable selector — all four builders set it via the shared `task_pod_labels()`, and image ancestry confirms it is in the deployed images. `factory-gitops#102` applies both selectors as two policies, since a podSelector cannot OR across label keys. |
| Factory#503 | Control-plane pods run with no container `securityContext`; charts claim a hardened one. Found via this inventory but **not caused by it** — the CronJob plain manifests are hardened, so the Deployment manifests were simply never written that way |
| Factory#504 | No gate compares the chart control subset against the gitops manifests |
| Factory#462 | This CNI enforces NetworkPolicy ingress, not egress; every egress rule here is documentation of intent |

The same disease on other axes, for reference: Factory#434 (the shared standard vendored to some services and gated in fewer), Factory#483 (services hand-restating a shared contract instead of vendoring it), Factory#512, Factory#513.

## How to check this yourself

```
helm template aifactory AIFactory/charts/aifactory --namespace factory \
  | yq -r 'select(. != null) | [.kind, .metadata.name] | @tsv' | sort -u
yq -r 'select(. != null) | [.kind, .metadata.name] | @tsv' \
  factory-gitops/apps/aifactory/manifests/*.yaml | sort -u
kubectl --context factory -n factory get networkpolicy,pdb,sa,cm
```
