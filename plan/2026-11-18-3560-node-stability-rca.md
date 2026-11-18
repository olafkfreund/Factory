---
status: approved
issue: 3560
spec: spec/2026-11-18-3560-node-stability-rca.md
coders:
  1: coder    # one 15-line kustomize patch in one file; a handoff costs more than it saves
reviewers:
  - codex     # read-only review of the final diff; agy is off by owner decision
---

# Plan: node stability RCA

## Approved decisions (from the spec)

- Verdict: lease loss confirmed for virt-template-controller and keda-operator (16:26:40-47)
  and by signature for the three Kyverno controllers and the reports controller; shared
  trigger suspected to be apiserver datastore (k3s SQLite/kine) stalls on a 83-87% full SATA
  SSD (`/mnt/img_pool`); `runtime_lost` (15:36:04) is the k3s server container restarting
  (exit 1 at 15:35:58, trigger unproven). virt-template-controller is not a separate defect.
- Repo change: keda-operator leader-election env vars only (60s / 40s / 5s). Kyverno and
  virt-template have no timing knobs; nothing else in the repo is changed.
- Everything else is an owner host step (below). No live change by agents.

## Steps

1. factory-gitops `apps/keda/manifests/kustomization.yaml`: append a `patches:` entry
   targeting `Deployment/keda-operator` (ns keda) that adds env
   `KEDA_OPERATOR_LEADER_ELECTION_LEASE_DURATION=60s`, `..._RENEW_DEADLINE=40s`,
   `..._RETRY_PERIOD=5s` to container 0, with a comment citing Factory#3407 and the spec.
   Use a strategic-merge patch (env merges by name; no index dependence). Verify by
   `kustomize build apps/keda/manifests` (three vars present, diff against `main` build is
   only those vars) and the repo's pre-commit / schema checks.
   Traps: the file's header says keda.yaml is a Helm re-render, so patch, never edit
   keda.yaml; keep the `images:` digest pins untouched.
2. Factory: commit the three artifacts (done on this branch), open the Factory PR, comment
   the verdict and owner steps on #3560, #3823, #3437, #3434, #3430, #3429, #3407. Do not
   close any issue. Verify by `gh issue view` showing each comment.
3. Final review: `codex review --base origin/main` in each worktree; read the diff against
   this plan.

## Verdict comment wording (step 2)

Each comment states: lease loss confirmed (or matched by signature, for Kyverno) at the
instants in the spec; datastore stall on the shared SSD is SUSPECTED, not proven;
verdict is "partial repo mitigation", not "fixed"; for keda the accepted tradeoff is a
slower lease reclaim (up to 60 s) if the operator truly hangs; the other controllers may
keep restarting and whether freeing the disk stops that is a hypothesis; the owner steps
below; the 34 versus 29 container count is unresolved. The watchdog closes the issue.

## Owner steps (host; not performed by agents)

On p620, as the owner. Measure first, change second.
```
# 1. what is on the shared disk (read-only)
docker system df; df -h /mnt/img_pool
# 2. free build cache. Default scope is dangling cache only; --all removes every unused
#    build cache record (the 90 GB figure). Running containers and images are untouched;
#    removed cache is rebuilt on the next build (slower first build).
docker builder prune -f            # try first
docker builder prune -f --all      # if still above 70% used
df -h /mnt/img_pool                # target: under 70% used. If not, free images:
                                   #   docker image prune -a --filter until=168h
# 3. during a stall (a keda/kyverno restart in the watchdog), capture disk latency
iostat -x 1 30 | grep -E 'Device|sdd'      # r_await/w_await, %util for sdd
# 4. confirm kine stalls match (read-only)
docker logs k3d-factory-server-0 --since 30m 2>&1 | grep -c 'Slow SQL'
```
Cluster recreate window (owner decision; destroys nothing if the data directory is kept):
move the k3s datastore to nvme. Check `df -h /` has room first (the SQLite file is about
50 MB plus WAL), create `/nvme/k3d/server` (any directory on `/`, owned root), and add
`--volume /nvme/k3d/server:/var/lib/rancher/k3s/server@server:0` to the k3d create command
that the host's k3d-bootstrap runs (nixos_config; not edited by this plan). Existing state:
stop the cluster, copy `state.db*` from `/mnt/img_pool/docker/volumes/<server volume>` or
`docker cp k3d-factory-server-0:/var/lib/rancher/k3s/server /nvme/k3d/server`, then start.
Afterwards verify the mount moved the writes: `docker exec k3d-factory-server-0 df
/var/lib/rancher/k3s/server` shows the nvme device and `docker logs ... | grep -c
'Slow SQL'` drops. Do not run image builds or `just razer` while a rollout is syncing.
p620 `/` (82%) and the kubelet image GC threshold stay with the owner.

## Tests

- `kustomize build apps/keda/manifests | grep -A1 LEADER_ELECTION` shows the three vars.
- `kustomize build` for the other app dirs is unchanged (only keda touched).
- Post-sync, run by the coordinator or owner (read-only):
  `kubectl -n keda get deploy keda-operator -o jsonpath='{.spec.template.spec.containers[0].env}'`
  shows the vars; `kubectl -n keda logs deploy/keda-operator | grep -i leader` shows
  acquisition and no exit 1 at start. Effect: find a minute where
  `docker logs k3d-factory-server-0 | grep 'Slow SQL'` bursts AND a lease `PUT` exceeds
  5 s (apiserver_request_duration_seconds, leases, PUT, le 5 vs +Inf); the evidence is
  keda showing no `leader election lost` across that window. No burst proves nothing.
- Verdict comments: `gh issue view <n> --repo olafkfreund/Factory --comments` shows the
  text for #3560, #3823, #3437, #3434, #3430, #3429, #3407.

## Rollback

Revert the factory-gitops PR (removes the env); Argo CD restores the previous Deployment.
