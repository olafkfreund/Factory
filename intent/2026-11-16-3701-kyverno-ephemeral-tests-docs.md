---
status: draft
issue: 3701
author: olafkfreund
---

# Intent: Pin ephemeral-container coverage for all rules; fix Audit-era docs

## Problem

Issue #3701, follow-up to #3665. In factory-gitops the Kyverno rule
`require-first-party-signature-coverage` has three rules (factory, gateway,
fides). Only the factory rule has a test that an uncovered first-party image in
`ephemeralContainers` (`kubectl debug`) fails. The gateway and fides rules carry
the same jmesPath but nothing pins it. `docs/image-signature-admission.md` still
describes the Audit era although both policies are `Enforce`.

## Proposed outcome

- Kyverno CLI tests fail if the `ephemeralContainers` term is dropped from the
  gateway or fides rule.
- The doc header, "audit-mode policy" section, the dry-run "comes back clean" and
  "neither channel" passages, the "about 140" figure, and the three "nothing
  offline catches a narrowed glob" passages match Enforce and
  `assert-signature-lists-agree.py`.

## Affected users and systems

factory-gitops: `apps/kyverno-policies/tests/` and one doc. No policy manifest,
nothing Argo CD syncs to the cluster changes.

## Constraints

Do not change policy manifests. No live cluster access. Out of scope, for the
owner: (1) whether to add a catch-all namespace rule; (2a) running `kubectl
debug` against the live cluster. The stale `skip` rows in the gateway
PolicyReports are noted, not acted on.

## Open questions

None.
