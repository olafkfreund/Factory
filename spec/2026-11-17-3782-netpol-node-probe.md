---
status: approved
issue: 3782
intent: intent/2026-11-17-3782-netpol-node-probe.md
---

# Spec: per-node NetworkPolicy enforcement probe and k3d restart runbook

## Design

New app `apps/netpol-node-probe` in factory-gitops (Argo auto-discovers
`apps/**/application.yaml`, same layout as `host-k3d-internal-probe`).

- Two CronJobs, one per node (`k3d-factory-server-0`, `k3d-factory-agent-0`),
  both `*/10 * * * *` (job-watchdog's schedule estimator reads stagger syntax
  such as `5-59/10` as hourly, so no stagger). Each pod is pinned with
  `nodeSelector: kubernetes.io/hostname` (not `nodeName`, which would bypass
  the scheduler's resource, cordon and taint checks), has explicit requests
  and limits, and carries `factory.io/kind=task`, so
  `factory-sandbox-jobs-egress` selects it exactly like a real task pod.
- The container runs the gate's own two-leg check (busybox, same pinned
  digest): ALLOW `10.43.0.1:443` must connect and DENY `$HOST_IP:10250`
  (the node's kubelet, from `status.hostIP`) must be refused. Both legs are
  sampled twice, polled up to 30 s to ride out the pod-start race. Result
  names the node and says which leg failed, with a pointer to the runbook.
- Non-zero exit on failure. `apps/job-watchdog` reads CronJobs cluster-wide,
  counts consecutive failures (threshold 2) and files/closes a GitHub issue,
  so no new alert code. Worst case about 50 minutes, same as
  host-k3d-internal-probe. Retention matches that probe (3 successful, 10
  failed Jobs, no TTL) so two failures survive until the watchdog reads them.
  Job `activeDeadlineSeconds: 420` covers pod start, the injected gate (up to
  60 polls) and the main check, and makes a NotReady node (pod never starts)
  fail too; `backoffLimit: 0`.
- The Kyverno gate also injects its init container into these pods (webhook
  `failurePolicy: Fail`). Outcomes: gate fails -> the pod fails, diagnostics
  are in the `netpol-gate` init container log; Kyverno down -> admission
  rejects the pod, the Job fails with no pod (UNKNOWN: the runbook says to
  check Kyverno first); gate passes -> the main container re-checks and
  prints the node and failed leg. Every failure mode fails the Job.
- Hardening: no service account token, runAsNonRoot 65534, read-only root,
  drop ALL, RuntimeDefault seccomp, no hostNetwork, no RBAC objects.
- Runbook `docs/runbooks/k3d-restart.md` (no runbook dir or k3d restart doc
  existed; `docs/operating.md` only covers p510 reboot): server first,
  `K3D_FIX_DNS=0 k3d cluster start`, re-adding hosts entries from
  `docker inspect` IPs, and the kube-router per-pod rule count check. Linked
  from `docs/operating.md` and the mkdocs nav.

## Limits (stated, not hidden)

This is a per-node EGRESS sentinel for fresh task pods. It does not prove
ingress default-deny or rules for other pods. Its deny leg is "kubelet
:10250 refused", so a kubelet unreachable for another reason would read as
enforced; the gate has the same ceiling and the policy file records the
unselected-control measurement that shows the leg is live. The runbook's
iptables rule count check is the broader, human-run proof.

## Alternatives rejected

- Probe pod created by one CronJob via the API: needs a ServiceAccount with
  pods create/delete, and the node pinning is the only thing it adds.
- Reusing only the Kyverno gate by labelling a pod: no named node/leg in the
  failure and depends on Kyverno.
- DaemonSet with hostNetwork reading iptables: privileged, rejected by the
  constraints.
- New notification path: job-watchdog already exists and is proven.

## Risks

- Node names are hard-coded; a rebuilt cluster with other names leaves the
  pods Pending, the Jobs fail on deadline and alert, which is the right
  signal. Runbook says to update them.
- Probe pods count against the namespace like any task pod; ten minutes and
  `ttlSecondsAfterFinished` keep it small.
- A kube-api rule that no longer matches would also fail the probe
  (UNKNOWN case); the message says so, as the gate does.

## Verification

- `kustomize build apps/netpol-node-probe/manifests | kubeconform` (CI
  manifest-validate).
- Script logic run locally with a stubbed `nc` for: enforced (pass),
  unenforced (fail, names leg), no datapath (fail).
- Read-only: after Argo syncs, `kubectl get cronjob,job -n factory` shows both
  CronJobs and a passing Job per node. Owner restarts nothing.
