---
status: draft
issue: 3701
spec: spec/2026-11-16-3701-ephemeral-live-check-and-audit-docs.md
coders:
  1: you
  2: you
reviewers:
  - codex
---

# Plan: Ephemeral-container check and Audit-era docs

Decisions carried from the spec: edit the doc in place (historical labels, no rewrite), add one auto-discovered CLI test with `values.subresources`, put the live `kubectl debug` procedure in the doc and in the owner actions. No live changes by an agent.

## Steps

1. factory-gitops `docs/image-signature-admission.md`: fix stale passages, add "Live check: kubectl debug" → verify by reading against `kubectl get clusterpolicies`.
   Traps: none
2. factory-gitops `apps/kyverno-policies/tests/kyverno-test-ephemeralcontainers-subresource.yaml`: policy `../manifests/require-first-party-signature-coverage.yaml`, resources reuse the three existing `*-uncovered-in-ephemeralcontainer` Pods in `resources.yaml`, inline `values.subresources` mapping `pods/ephemeralcontainers` (kind Pod, v1) to parent `pods` → verify by `kyverno test apps/kyverno-policies/tests -f kyverno-test-ephemeralcontainers-subresource.yaml` (3 pass).
   Traps: the gate fails a case whose rule yields no verdict; keep expected `fail` cases that evaluate.

## Tests

`kyverno test apps/kyverno-policies/tests -f kyverno-test-ephemeralcontainers-subresource.yaml`; PR checks on factory-gitops.

Owner action (not an agent step): run the "Live check: kubectl debug" section of the doc. Acceptance: each of the factory, gateway and fides `kubectl debug` requests is denied with the named coverage rule in the message and the Pod's `spec.ephemeralContainers` stays empty; keep the three denial messages as evidence. An unrelated error (RBAC, image pull) does not count.

## Rollback

Revert the factory-gitops PR.
