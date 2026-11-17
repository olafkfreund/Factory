---
status: draft
issue: 1959
intent: intent/2026-11-17-1959-gateway-routes.md
---

# Spec: routes in the task contract, and the route in the evidence trail

Code lands in olafkfreund/Factory (schema, hub, main) and olafkfreund/PFactory (dev). Artifacts live here.

## Design

1. **Hub schema** (`apis/task-contract.schema.json`, `execution`): add, next to `phase_models`, `route` (string, enum `local|cheap|balanced|frontier`) and `phase_routes` (object, keys open like `phase_models` (`spec|planning|coding|qa|qa_fixer|test_gen` by convention), every value the same enum via `additionalProperties`). The enum is the catalog `class` vocabulary of `apis/model-catalog.json`, not `execution.routing.class` (`economy|standard|premium|governed`, a scorer verdict). `contract_version` stays "2". `scripts/validate_task_contract.py` gains asserts (valid route accepted, `tier-frontier` rejected, absent fields still validate) and a hub pytest `tests/test_task_contract_routes.py` pins the schema enum to the set of `class` values in `apis/model-catalog.json` so the two cannot drift. `factory_contracts` (`shared/factory-contracts`) is generated from the completion-event and status taxonomy only and holds no task-contract model, so it is not touched; the catalog and task contract are vendored by PFactory/AIFactory, not factory_contracts.
2. **PFactory emit** (`plan/emit/cost_router.py`): `apply_cost_routing` also writes `execution.phase_routes` = the catalog `class` of each picked model (`planning`, `coding`, `qa`, `test_gen`), merged over existing keys like `phase_models`. A model missing from the catalog yields no entry. `route` is not set by the router (it is a single run-level override a human or gateway client may add).
3. **PFactory consumer** (`phase_config.py` `get_phase_model`): when the metadata carries `phaseRoutes` for the phase AND `PFACTORY_MODEL_GATEWAY_URL` is set, the model sent is the route class; otherwise the existing `phaseModels` path is unchanged. Default off: with no env var nothing changes. `aifactory_handoff` forwards `phaseRoutes` next to `phaseModels` (None when absent). AIFactory's own phase resolver, which is the actual build path, is a follow-up issue in AIFactory (it needs the same two-line preference); until then the route is carried, not consumed, on the build path.
4. **Route in the signature** (`usage.py`, `render.py`): `PlanUsage` gains `route: str = ""`, folded like `model` (first non-empty), read by `usage_from_obj` from a dict key `route`, and a helper `route_from_headers(headers)` reads the response header `X-Model-Route` (case-insensitive) from whatever the HTTP seam returns. The gateway (`AIFactory/apps/model-gateway/gateway.py`) sets no such header today, so this is the reader half of a contract the gateway must start honouring (follow-up in AIFactory); it is exercised with a stub. `_run_signature` writes `model_route` = `session.usage.route` if set, else `execution.phase_routes["planning"]` from the session's contract, else null. `change_id` stays null here (see 6).
5. **CLI projection** (`governance_cli.py`): `MATCH_KEYS` gains `controls`, `agent_identity`, `model_route`; the text line prints them (control characters scrubbed with the existing `_clean`; `controls` joined by comma). JSON output gains the same keys (additive). Tests: JSON projection contains the three keys with the values written by a real render; `--control` and `--tier` filters, singly and together, return exactly the matching rows and exclude schema-1 rows.
6. **Deploy-to-plan join**, smallest form: a commit trailer `Plan-Slug: <correlation_key>` (the key already in registry and signature). Reader, built now: `governance_cli --repo <git-dir>` adds `commits` (sha list) to each matched row by one `git log --format='%H%x00%(trailers:key=Plan-Slug,valueonly)'` call, comparing the trailer value to the row's `correlation_key` exactly; it shells out to `git` read-only with an argv list, no network, no secret. A repo path that is not a git repo is a clear error (exit 2), never "no commits". Writer, NOT built: AIFactory must stamp the trailer (it already stamps `Agent-Identity`, `Autonomy-Tier`, `Originator` via `core/commit_trailers.py`, but `requirements.json` does not carry the correlation key) and factory-gitops image bumps would need to copy it; both live in other repos and change deploy flow, so they are recorded as follow-up issues. Until the writer lands the join returns empty and says so in the summary line ("0 commits carry a Plan-Slug trailer").
7. **Follow-up issues** (filed, linked in the PR): AIFactory consumer preference for `phase_routes`; gateway emits `X-Model-Route`; AIFactory stamps `Plan-Slug` and gitops bump copies it.

## Alternatives rejected

- New `tier-*` route names: the epic forbids a new vocabulary; the class set already exists and the hub test pins it.
- Replacing `phase_models` by routes: breaks every current consumer; stage 3 is additive.
- Taking `model_route` only from the cost router: that is the plan, not what ran; the header is preferred, the router is the fallback.
- A deploy join by registry lookup of image SHA: needs a service holding SHA to slug; the trailer needs none.
- A `governance_cli trace` subcommand: the CLI is flat today; one flag is smaller.
- Re-vendoring the schema into PFactory now: the pinned `HUB_SHA` must name a commit on hub main, which does not exist until the hub PR merges; the execution object tolerates unknown keys, so PFactory emits correctly before re-vendor. The re-vendor plus HUB_SHA bump is the coordinator's step after the hub merge (owner action).

## Risks

- PFactory emits `phase_routes` before its vendored schema declares it: valid (open object), but the drift gate compares the vendored copy to the pinned hub SHA, so the re-vendor must follow the hub merge or the gate and the schema diverge silently only in documentation.
- `PFACTORY_MODEL_GATEWAY_URL` set while the gateway cannot resolve a class name would send an unknown model; the gateway route aliases are the same class names (epic route design), and the flag is off by default.
- The `X-Model-Route` name is a proposal, not an existing gateway behaviour; absent header falls back to the router route, so nothing misreports.
- `git log` on a large repo is slow; the call is opt-in via `--repo`.

## Verification

Hub: `python scripts/validate_task_contract.py`, `pytest tests/test_task_contract_routes.py`, CI. PFactory: `pytest` for the touched tests (cost router emits `phase_routes`; `get_phase_model` prefers the route only with the env var; a run through a stubbed gateway response with an `X-Model-Route` header fills `model_route` in the written signature, and without the header the planning route fills it; CLI projection and filter tests; `--repo` join against a temp git repo with and without a matching trailer, and a non-repo path), ruff and mypy per the repo's ratchet, CI green.
