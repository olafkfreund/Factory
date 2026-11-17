---
status: approved
issue: 1959
spec: spec/2026-11-17-1959-gateway-routes.md
coders:
  1: lead   # one schema edit plus a pin test, small
  2: lead   # five small, interlocking edits in PFactory whose checks the lead reruns anyway
  3: lead
  4: lead
  5: lead
  6: lead
reviewers:
  - codex   # final `codex review --base` on each repo
---

# Plan: routes in the task contract, and the route in the evidence trail

Repos: Factory (hub, base `main`, branch `feat/1959-gateway-routes`, artifacts plus step 1) and PFactory (base `dev`, branch `feat/1959-route-evidence`, steps 2-6). Order: hub PR first. Approved decisions (spec): additive `execution.route` / `phase_routes` in the hub schema with the catalog class enum `local|cheap|balanced|frontier` (not `economy|...`), pinned to the catalog by a test; `factory_contracts` untouched (no task-contract model there); PFactory emits `phase_routes`; the consumer preference is DEFERRED (no component resolves a class name to a model, so it would send an unresolvable name); the signature `model_route` is the latest gateway-reported route, else the planning phase route, else null; the CLI projects `controls`, `agent_identity`, `model_route`; a read-only `--repo` join reads a `Plan-Slug` trailer; the trailer writer, the gateway header, route resolution and the AIFactory consumer are follow-up issues. `phase_models` behaviour is unchanged everywhere. The PFactory re-vendor of the schema plus `HUB_SHA` bump waits for the hub merge (owner/coordinator action); PFactory emits correctly meanwhile because `execution` tolerates unknown keys.

## Steps

1. Factory `apis/task-contract.schema.json` (`execution.properties`, after `phase_models`, ~l.141-145): add `route` (string, enum) and `phase_routes` (object, `additionalProperties` the same enum), descriptions citing RFC-0014 classes and that `phase_models` is still honoured. `scripts/validate_task_contract.py`: asserts that a contract with `route: balanced` and `phase_routes: {planning: frontier}` validates, `route: tier-frontier` and `phase_routes: {coding: economy}` are rejected, absent fields validate. New `tests/test_task_contract_routes.py` (use `tests/contract_schema.py` helpers, jscpd budget): the schema enum equals the set of `class` values in `apis/model-catalog.json`. Check: `python scripts/validate_task_contract.py`; `pytest tests/test_task_contract_routes.py tests/test_task_contract*.py`.
   Traps: do not reorder or reformat other schema lines (PFactory's vendored copy is compared parsed); jscpd clone budget only ratchets down.
2. PFactory `apps/backend/plan/usage.py`: `PlanUsage.route: str = ""`; `add()` keeps the latest non-empty route; `usage_from_obj` reads `route` (dict key) and an `X-Model-Route` header (case-insensitive) from a `headers` mapping (dict key or attribute), and returns a zero-token record when only a route is found. `plan/decompose/planner.py` ~l.371-377: when the first record is route-only, take tokens from `usage_from_obj(llm)` and carry the route over (4 lines). Tests in `tests/test_plan_usage.py`: dict route, headers mapping any case, headers attribute, header-only response without token counts, latest route wins in `add`, planner seam with a stub llm returning a header-bearing raw response ends with the route in the sink, and a stub whose raw response has only headers while `llm.last_usage` has tokens keeps BOTH route and token totals (the ceiling reads the totals). Check: `pytest tests/test_plan_usage.py` and the planner tests that exist (`pytest -k "planner or usage"`).
   Traps: `PlanUsage.as_event_block` must not gain `route` (RFC-0001 envelope is frozen); keep ruff (aliases in parenthesised imports: plain names).
3. PFactory `apps/backend/plan/emit/docs/render.py` ~l.168: `model_route` = `session.usage.route or planning phase route from session.contract_result["contract"]["execution"]["phase_routes"]["planning"] or None`; a small helper `_model_route(session)` next to `_routing_verdict`. `apps/backend/plan/emit/cost_router.py` `apply_cost_routing`: write `execution["phase_routes"]` = `{role: catalog class}` for each picked role present in the catalog, merged like `phase_models`; `select_phase_models` returns it under `phase_routes`. Tests: `tests/test_cost_router.py` (phase_routes classes, `phase_models` unchanged, unknown model omitted); `tests/test_plan_docs_run_signature.py` (signature `model_route` filled by a session whose usage went through a stubbed gateway response with the header; fallback to the planning route with a contract; null with neither; second-run route wins). Check: `pytest tests/test_cost_router.py tests/test_plan_docs_run_signature.py tests/test_contract_emit.py`.
   Traps: signature stays deterministic (no clock); `change_id` stays null; `signature_schema` stays 2 (additive value, same meaning).
4. PFactory `apps/backend/plan/governance_cli.py`: `MATCH_KEYS` += `controls`, `agent_identity`, `model_route`; `format_result` prints them (`controls` comma-joined, all through `_clean`). Tests in `tests/test_governance_cli.py`: update the exact-row expectation at l.98-108 for the three new keys; JSON has the three keys with values from a real rendered signature; `--control`, `--tier` and both together return exactly the matching rows, schema-1 rows excluded; hostile control characters in the new fields are scrubbed. Check: `pytest tests/test_governance_cli.py`.
   Traps: existing text format keeps its field order, the new fields are appended.
5. PFactory `governance_cli.py` `--repo <path>`: after select, one `subprocess.run(["git", "-C", str(Path(repo).resolve()), "log", "--format=%H%x00%(trailers:key=Plan-Slug,valueonly)"], capture_output, text, check False, timeout 60)`; a nonzero exit (not a repo), `subprocess.TimeoutExpired` and a missing `git` (`OSError`) each print `error:` to stderr and return 2; each matched row gets `commits` = shas whose trailer lines contain its `correlation_key` exactly; the summary line gains `N commits carry a Plan-Slug trailer`. Tests: temp git repo with commits with and without a matching trailer (git config user set locally in the test), a non-repo path, a timeout (monkeypatched run) and a missing git executable (monkeypatched) each return 2, a path starting with `-` is not read as an option, no `--repo` leaves output unchanged. Check: `pytest tests/test_governance_cli.py`.
   Traps: no shell, no network, read-only git; `git` absent is an error exit 2, not an empty answer.
6. Issues and docs (lead): file follow-up issues (route resolution + consumer preference; gateway `X-Model-Route`; AIFactory `Plan-Slug` trailer + gitops bump copy) and link them; document `--repo` and the new fields in PFactory's governance doc if one names the CLI (`grep -rn governance_cli docs techdocs`); RFC-0014 one-line note in Factory that the schema now carries the class as `route`. Decision comments on #1959 and #1958 (no close).

## Tests

Factory: `python scripts/validate_task_contract.py`; `pytest tests/ -q -k "contract or catalog"`; CI. PFactory: the pytest files named in steps 2-5, then the repo ratchet commands from `.github/workflows/ci.yml` (ruff ratchet, mypy strict ratchet) on the changed files; CI green on the head SHA.

## Rollback

Revert the PRs. Every change is additive (new optional schema keys, new signature value for an existing key, new CLI fields and an opt-in flag); `phase_models` and the RFC-0001 usage block are untouched, so a revert needs no data fix. Signatures already written keep a harmless extra `model_route` value.
