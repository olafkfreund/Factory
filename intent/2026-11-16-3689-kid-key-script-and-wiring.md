---
status: approved
issue: 3689
author: olafkfreund
---

# Intent: Prepare the 2026Q4 trusted-plan kid key: generation script and optional wiring

## Problem

R-013: the live `aifactory` and `pfactory` Deployments hold only the legacy unkeyed `AIFACTORY_TRUSTED_PLAN_KEY_PFACTORY`, so no envelope carries a `kid` and nothing can be retired. Expiry support landed in AIFactory#2069 and the runbook exists, but the owner still has to generate the key and add it to both Deployments.

## Proposed outcome

- A script that generates the key into a mode-600 file only and prints no secret.
- Both Deployments read the 2026Q4 keyed variable from optional Secret keys, so the remaining owner steps are seeding the Secret and rolling the two Deployments in the documented order; nothing changes before then.
- The expiry variable is set in the aifactory manifest.

## Affected users and systems

factory-gitops `apps/aifactory`, `apps/pfactory`, `scripts/`, `docs/secrets-management.md`. The owner runs the script, seeds the Secret through agenix and rolls the Deployments in order.

## Constraints

No key material is handled by the agent. The trusted-plan key is a shared HMAC secret, so there is no public key to print; the script prints the kid, the Secret key names, a short fingerprint and the expiry instead. A keyed variable is optional in both manifests.

## Open questions

None. The issue's wording "prints only the public key and kid" is adapted to the fingerprint because HMAC has no public key (recorded decision).
