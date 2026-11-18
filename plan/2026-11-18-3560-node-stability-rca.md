---
status: draft
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

## Owner steps (host; not performed by agents)

Run on p620 as the owner, in this order. Measure first, change second.
```
# 1. what is on the shared disk (read-only)
docker system df
df -h /mnt/img_pool
# 2. free the build cache (about 90 GB reclaimable; running containers are unaffected)
docker builder prune -f
# 3. confirm headroom, target under 70% used
df -h /mnt/img_pool
# 4. while a stall is happening, capture disk latency (read-only)
iostat -x 1 30 | grep -E 'Device|sdd'
```
Then, at the next cluster recreate window: place the k3d server datastore
(`/var/lib/rancher/k3s/server`, the SQLite `state.db`) and the Docker build cache on nvme
instead of `/mnt/img_pool`, for example by mounting an nvme directory over that path in the
k3d config (`--volume /nvme/k3d/server:/var/lib/rancher/k3s/server@server:0`) and pointing
`builder` data at nvme. Do not run image builds or `just razer` while a rollout is syncing.
p620 `/` (82%) and the image GC threshold are separate and remain the owner's.

## Tests

- `kustomize build apps/keda/manifests | grep -A1 LEADER_ELECTION` shows the three vars.
- `kustomize build` for the other app dirs unchanged (only keda touched).
- After merge and sync: keda-operator pod starts and logs leader acquisition; compare
  restarts across a later Slow SQL burst as in the spec.

## Rollback

Revert the factory-gitops PR (removes the env); Argo CD restores the previous Deployment.
