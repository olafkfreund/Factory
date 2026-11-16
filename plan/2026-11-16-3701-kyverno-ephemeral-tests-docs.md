---
status: draft
issue: 3701
spec: spec/2026-11-16-3701-kyverno-ephemeral-tests-docs.md
coders:
  1: lead
  2: lead
  3: lead
reviewers:
  - codex
  - agy
---

# Plan: Pin ephemeral-container coverage for all rules; fix Audit-era docs

Approved design: add two ephemeral-only test Pods (gateway, fides), list them as
`fail` results, and correct the Audit-era doc text. No policy manifest changes.
Repo: olafkfreund/factory-gitops, base main. Each step is small and the lead does
it (reason: three tiny edits, a handoff costs more than it saves).

## Steps

1. `apps/kyverno-policies/tests/resources.yaml` (append): two Pods as in the spec
   → verify by `kyverno test apps/kyverno-policies/tests/`.
   Traps: use the same Kyverno major as the cluster where possible.
2. `apps/kyverno-policies/tests/kyverno-test.yaml`: add both names to the gateway
   and fides `fail` result lists → same command, 30 passed.
   Traps: results are matched by rule name.
3. `docs/image-signature-admission.md`: title, status block, "The policy" section,
   ephemeral paragraph, skip-row count, Factory#574 limitation (mark historical),
   three narrowed-glob passages → verify by reading the diff and grep for
   "audit mode" / "comes back clean".
   Traps: keep phase-1 history intact.

## Tests

- `kyverno test apps/kyverno-policies/tests/` → all pass.
- Mutation: remove `ephemeralContainers` from the gateway rule → one new case fails; restore.
- `python3 apps/kyverno-policies/assert-signature-lists-agree.py` → ok.

## Rollback

Revert the factory-gitops PR; no cluster state is touched.
