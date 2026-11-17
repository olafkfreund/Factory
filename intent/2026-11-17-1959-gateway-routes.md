---
status: draft
issue: 1959
author: olafkfreund
---

# Intent: routes in the task contract, and the route in the evidence trail

## Problem

Epic #1959 stage 3 is "routes replace model ids in the contract". Today `execution.phase_models` in `apis/task-contract.schema.json` carries concrete model ids, so a route change means re-vendoring the catalog and redeploying. The RFC-0014 capability class (`local < cheap < balanced < frontier`, `apis/model-catalog.json`) already exists but is not in the contract.

Epic #1958 acceptance item 3 asks that a production change's evidence trail answers control objectives, agent or human author, autonomy tier and approver. The 2026-11-17 assessment (Factory#3787) found three PFactory gaps that code can close now:

- (b) `plan/emit/docs/render.py` writes `model_route` (and `change_id`) as constant null, so even a gateway-routed run records no route.
- (c) `plan.governance_cli` projects a fixed field list and omits `controls`, `agent_identity` and `model_route`.
- (d) nothing joins a production change (merge commit, image-SHA bump) to the plan that produced it. No commit in the four repos carries a plan key today (checked: no `Plan-Slug` trailer anywhere), so the answer is per plan, not per deploy.
(a), that the live registry had no schema-2 row, is an observation to re-check after the next emit, not code.

## Proposed outcome

- The hub task-contract schema accepts additive `execution.route` and `execution.phase_routes`, values from the existing class vocabulary. `phase_models` is unchanged and still honoured.
- PFactory emits `phase_routes` beside `phase_models` (class of each picked model) and, when a gateway is configured, a consumer prefers the route; otherwise behaviour is exactly today's.
- A PFactory schema-2 signature records the route used: the gateway-reported route when a run went through the gateway, else the cost router's planning route, else null.
- `governance_cli --json` and the text output show `controls`, `agent_identity` and `model_route`; `--control` and `--tier` filtering is regression-tested.
- The smallest deploy-to-plan join is designed; its reader is built if it needs no secret or service.

## Affected users and systems

Factory (schema, artifacts), PFactory (`render.py`, `usage.py`, `cost_router.py`, `phase_config.py`, `aifactory_handoff.py`, `governance_cli.py`, vendored schema). AIFactory (build consumer) and the writer side of the join are out of this round.

## Constraints

- Additive and default-off: no existing contract, consumer or signature breaks; no new vocabulary, no secret, no service, no live-cluster change.
- Hub first: schema in Factory main, vendored copy and its pinned drift SHA in PFactory only after the hub commit exists on main.
- Out of scope, owner-only: gateway Secret, token seeding, egress, Plane B bench test, key rotation. #1959 and #1958 stay open.

## Open questions

None. Decisions (owner delegation 2026-11-17): route values reuse the catalog classes verbatim (the epic forbids a new `tier-*` vocabulary); the route in the signature is taken from the gateway response header when present because that is what actually ran, with the cost-router decision as fallback; the join reader ships, the writer (a trailer on AIFactory commits) is a follow-up issue because it lives in AIFactory.
