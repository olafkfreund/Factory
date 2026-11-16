---
status: draft
issue: 3689
author: olafkfreund
---

# Intent: trusted-plan keys expire, and live signing moves to a kid key

## Problem

Risk R-013 (open at 8). AIFactory (`apps/backend/trusted_plan.py`) and PFactory
(`apps/backend/plan/emit/signing.py`) already support a key id (`kid`) and a
retired-kid list. Two gaps remain. The live Deployments set only the legacy
unkeyed `AIFACTORY_TRUSTED_PLAN_KEY_PFACTORY`, so no envelope carries a `kid`
and nothing can be retired. And no key has an expiry: a forgotten key is valid
forever.

## Proposed outcome

- AIFactory can refuse a key after a date the operator sets (`not_after`),
  for keyed and legacy keys alike. Unset means no expiry, as today.
- A rotation runbook states the interval and the exact commands.
- The owner moves live signing to a kid key using those commands (out of scope
  for the agent: it needs secret material and the live Deployments).

## Affected users and systems

AIFactory verifier and its merge gate; the compliance rotation doc; the
owner's factory-gitops secrets. PFactory's signer needs no code change.

## Constraints

- Backwards compatible: the signed bytes and envelope are unchanged, so no
  contract version bump and no PFactory change.
- Default off. No key material is handled by the agent.
- No change to factory-gitops or the live cluster.

## Open questions

Rotation interval: this proposes 90 days with a 14-day overlap. The owner may
change the number; the code does not depend on it.
