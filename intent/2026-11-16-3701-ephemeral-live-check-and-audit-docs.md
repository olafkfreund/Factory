---
status: draft
issue: 3701
author: olafkfreund
---

# Intent: Ephemeral-container check and Audit-era docs (Factory#3701 items 2, 3)

## Problem

`docs/image-signature-admission.md` in factory-gitops still carries text from the Audit era, and says the `pods/ephemeralcontainers` path has "no catch-all rule yet" and has "not been exercised". No test pins that the coverage rules evaluate a `pods/ephemeralcontainers` request, and no procedure exists for the live check.

## Proposed outcome

The doc matches the live Enforce state. A Kyverno CLI test covers the three coverage rules with the `pods/ephemeralcontainers` subresource. The owner has an exact live procedure for `kubectl debug`.

## Affected users and systems

factory-gitops `docs/` and `apps/kyverno-policies/tests/`; the owner (live run).

## Constraints

No ephemeral containers on the live cluster by an agent. Item 1 is done (factory-gitops#342). Keep the diff small.

## Open questions

None.
