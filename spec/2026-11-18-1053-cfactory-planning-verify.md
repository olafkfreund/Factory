---
status: approved
issue: 1053
intent: intent/2026-11-18-1053-cfactory-planning-verify.md
---

# Spec: verify CFactory to PFactory planning

## Design
No code change. Release v0.8.5 already contains `f8dfbd59` (#1065) and runs live as image `sha-5672b01`, so no new release or gitops bump is needed. Verify with a hard card (`cfactory_plan_card`), process the session, then read the registry with `plan.governance_cli` in the pod.

## Alternatives rejected
Cutting v0.8.6: nothing to ship. Approving the plan as the owner to force a signature: that is an owner signature, not an agent act.

## Risks
The test card FCT-10 and its session stay on the board.

## Verification
HTTP 200 with `source_channel: cfactory`; session processed; registry counts reported.
