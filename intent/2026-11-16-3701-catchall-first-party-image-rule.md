---
status: draft
issue: 3701
author: olafkfreund
---

# Intent: catch-all first-party image rule for namespaces with no coverage group (Factory#3701 item 1)

## Problem

`require-first-party-signature-coverage` and `verify-factory-image-signatures`
name four namespaces (`factory`, `gateway`, `fides`, `fides-reporter`). A
`ghcr.io/olafkfreund/*` image in any other namespace is admitted with no
signature check and no report row. Nothing says "this namespace has no group".

Checked live on 2026-11-16 (read-only `kubectl get pods -A`): the only
namespaces running `ghcr.io/olafkfreund/*` images are the four covered ones.
The others (`argocd`, `default`, `keda`, `kube-*`, `kyverno`, `tailscale`) run
none, so today's gap is empty. It reopens the day someone deploys a first-party
image into a fifth namespace.

## Proposed outcome

A new Audit-only rule reports (never blocks) any Pod that carries a
`ghcr.io/olafkfreund/*` image in a namespace outside the four covered ones and
the three Kubernetes system namespaces (`kube-system`, `kube-public`, `kube-node-lease`; Kyverno already filters them, and first-party images there would stay unchecked, which is acceptable because the cluster, not the repo, owns them). A PolicyReport `fail` row appears for it.
Kyverno CLI tests pin the behaviour. `docs/image-signature-admission.md`
explains how and when to flip it to Enforce. Enforce stays off.

## Affected users and systems

factory-gitops `apps/kyverno-policies` (new policy, new test suite), the
signature doc. Argo CD syncs the policy to the live cluster. No workload is
denied: Audit, `failurePolicy: Ignore`.

## Constraints

- Audit only; flipping to Enforce is the owner's decision after a clean week
  of PolicyReports.
- Must not change the existing four-namespace coverage rules or break
  `assert-signature-lists-agree.py` (it reads only the existing policy).
- No live-cluster change beyond what Argo CD syncs from the merged PR.
- Kyverno CLI v1.18.2, same as the cluster and CI.
- Same detection guarantees as the sibling policy: containers, initContainers
  and ephemeralContainers; `background: true` so existing Pods get a standing
  row; no registry access.

## Open questions

None. Items 2 and 3 of #3701 (ephemeral tests, Audit-era docs) merged in
factory-gitops#336; only the live ephemeral-container check remains and is out
of scope here.
