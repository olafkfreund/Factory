---
status: draft
issue: 3782
spec: spec/2026-11-17-3782-netpol-node-probe.md
coders:
  1: you
  2: you
reviewers:
  - codex
---

# Plan: per-node NetworkPolicy enforcement probe and k3d restart runbook

All work is in factory-gitops (branch `feat/3782-netpol-node-probe`); these
artifacts live in Factory (PR to main). Decisions carried from the spec: two
node-pinned (nodeSelector hostname) CronJobs, both `*/10 * * * *`, requests/limits set, Job deadline 420s, history 3/10, no TTL, labelled `factory.io/kind=task`, the gate's two-leg
check, exit non-zero and let job-watchdog alert, no RBAC/token/hostNetwork,
runbook at `docs/runbooks/k3d-restart.md`. Steps are small and tricky, so
the lead does them (no handoff); Codex reviews the artifacts and the diff.

## Steps

1. `apps/netpol-node-probe/{application.yaml,manifests/kustomization.yaml,manifests/manifests.yaml}`:
   ConfigMap `probe.sh` plus two CronJobs (server-0, agent-0), pattern of
   `apps/host-k3d-internal-probe` → verify by `kustomize build`, kubeconform,
   and the stubbed-`nc` script test.
   Traps: Kyverno rejects a dollar-paren in the injected gate only, not in
   this pod; keep image digest pinned to the gate's busybox; do not add
   RBAC; `factory.io/kind=task` label is required.
2. `docs/runbooks/k3d-restart.md`, link in `docs/operating.md` and
   `mkdocs.yml` nav → verify by `mkdocs build` if available, else link check
   by grep.
   Traps: no secrets; commands read-only except the documented restart.

## Tests

`kustomize build apps/netpol-node-probe/manifests` succeeds; kubeconform
clean; stub test: enforced exit 0, open deny leg exit 1, both closed exit 1.

## Rollback

Delete `apps/netpol-node-probe/`; Argo prunes the CronJobs. Doc revert is a
plain git revert.
