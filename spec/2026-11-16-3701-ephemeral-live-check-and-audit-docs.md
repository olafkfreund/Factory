---
status: draft
issue: 3701
intent: intent/2026-11-16-3701-ephemeral-live-check-and-audit-docs.md
---

# Spec: Ephemeral-container check and Audit-era docs

## Design

1. factory-gitops: edit `docs/image-signature-admission.md` for the stale passages (verified against live `kubectl get clusterpolicies`: verify and coverage are Enforce, the catch-all is Audit by design) and add a "Live check: kubectl debug" section.
2. Add `tests/kyverno-test-ephemeralcontainers-subresource.yaml` (auto-discovered by the CI gate) that declares `pods/ephemeralcontainers` under `values.subresources` and expects `fail` for the factory, gateway and fides ephemeral cases.

## Alternatives rejected

- Running `kubectl debug` live: owner's call, changes a running Pod.
- Rewriting the doc's history sections: they are marked historical; only labels are added.

## Risks

The CLI scores the case the same without the subresource declaration, so the test pins evaluation with the subresource, not webhook routing. The doc says so; the live check covers routing.

## Verification

`kyverno test apps/kyverno-policies/tests -f kyverno-test-ephemeralcontainers-subresource.yaml` (v1.18.2 CLI; the `-f` is needed, the default run misses non-default filenames) passes, and the CI gate discovers it; the repo's manifest-validate gate is green; owner runs the live procedure.
