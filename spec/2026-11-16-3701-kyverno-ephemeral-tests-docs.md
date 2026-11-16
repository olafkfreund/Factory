---
status: approved
issue: 3701
intent: intent/2026-11-16-3701-kyverno-ephemeral-tests-docs.md
---

# Spec: Pin ephemeral-container coverage for all rules; fix Audit-era docs

## Design

In olafkfreund/factory-gitops:

1. `apps/kyverno-policies/tests/resources.yaml`: add Pods
   `gateway-uncovered-in-ephemeralcontainer` (ns `gateway`) and
   `fides-uncovered-in-ephemeralcontainer` (ns `fides`). Each has a covered
   regular container and an uncovered first-party image only in
   `ephemeralContainers`, so only the ephemeral term can make it fail.
2. `apps/kyverno-policies/tests/kyverno-test.yaml`: list them under the existing
   `fail` results of the gateway and fides rules.
3. `docs/image-signature-admission.md`: rewrite the passages listed in the intent.
   Phase-1 history stays, labelled as history.

## Alternatives rejected

- Chainsaw tests: need a cluster; the Kyverno CLI test suite already runs offline in CI.
- A new test file: the existing one already has the rule results.
- Rewriting the whole doc: only stale statements are in scope.

## Risks

Offline tests prove the rule logic, not that the live webhook routes
`pods/ephemeralcontainers`; that stays an owner action. Test engine is the
Kyverno CLI, cluster runs v1.18.2.

## Verification

`kyverno test apps/kyverno-policies/tests/` passes; dropping `ephemeralContainers`
from the gateway rule makes the new case fail (mutation check, done by hand);
`python3 apps/kyverno-policies/assert-signature-lists-agree.py` still passes.
