---
status: approved
issue: 1961
spec: spec/2026-10-14-1961-artifact-governance-header.md
---

# Plan: governance fields in the PFactory run signature

## Decisions carried over

From the intent and spec, both approved on 2026-10-14:

- **Scope.** This plan covers the hub control catalog, signature schema 2 with
  the fields the run already knows, `controls[]` and the query CLI. It leaves out
  `originator` threading, which waits for #1960, portal auth, the ITSM link,
  `agent_identity` (#1960) and `model_route` (#1959).
- **Flat keys** next to the existing ones in `_run_signature`. No existing key
  changes meaning. `SIGNATURE_SCHEMA` goes from 1 to 2.
- **Absent values are never plausible.**
  - `risk_class` falls back to `"unknown"` (never `"low"`), with a `risk_class_basis`.
  - `autonomy_tier` falls back to `"unknown"`.
  - `autonomy_verdict` is a separate key, using the RFC-0014 axis, and falls back to `null`.
  - `data_classification` is `"Regulated"` only when the contract's
    `compliance.data_classes` includes a personal-data class. Otherwise it is
    `"unknown"`, with a `data_classification_basis`. It is never `Internal` or
    `Confidential`.
  - `approved_by` and `approved_at` fall back to `null`, never `""`.
  - `change_id`, `originator`, `agent_identity` and `model_route` are always `null`.
- **`controls[]` lists the control domains this run's gates engaged.** The rule
  table in step 3 decides them. `audit-logging` is always included. An id the
  catalog doesn't know, or a catalog that is missing, gives `controls: null`.
- **`render.py` stays pure.** The catalog is loaded in `emit_docs.py` and passed
  into the render.
- **The CLI has no index.** It always prints the count line and counts every row
  it reads, including rows without a signature and schema-1 rows.
- **Where the work lives.** The artifacts stay in Factory. The code goes in two
  PRs: one in Factory for step 1, one in PFactory (base `dev`) for steps 2 to 5.
  The PFactory PR links back here.

## Deviation from the spec, recorded at planning

Spec §2 says the catalog drift check is "byte-identical, same code path". In
fact, `scripts/check_schema_drift.py` checks that a schema is a subset of the
vendored one; it is not a byte comparison. For a data file the right check is
equality. Step 2 therefore adds a catalog comparison that uses `==` on the parsed
JSON, inside the same script and CI step, and reuses its fetch and soft-skip
logic. The intent is unchanged: the vendored catalog cannot drift from the hub.

## Ordering trap

PFactory CI fetches hub files at a pinned commit: `HUB_SHA` in
`.github/workflows/ci.yml:34`, currently `565afeaf`. The script
`assert-hub-pin-on-main.sh` requires that commit to be on hub `main`. So
**step 1's Factory PR must merge first**, and step 2 then moves the pin to that
merge commit. Moving the pin also re-checks `task-contract.schema.json` against
the newer hub, so step 2 runs the drift script locally before it pushes.

## Steps

### 1. Factory: the control catalog and its matrix test

Coder: **Codex**. Worktree: `../Factory-1961`. Branch: `docs/1961-artifact-governance-header`.

- [ ] Add `apis/control-catalog.json`:
  ```json
  {"version": 1, "controls": [{"id": "...", "domain": "...", "issue": 311}, ...]}
  ```
  - It has 14 entries, in the order of the rows in
    `docs/compliance/control-matrix.md`. Each `domain` is the name of a matrix
    row with its `(#nnn)` removed.
  - The ids are:
    `governance-isms` (#311), `iam-access` (#312), `audit-logging` (#313),
    `encryption-at-rest` (#314), `secrets-management` (#315),
    `change-mgmt-sod` (#316), `vuln-mgmt` (#317), `supply-chain` (#318),
    `incident-response` (#319), `data-governance` (#320),
    `business-continuity` (#321), `runtime-isolation` (#322),
    `agentic-ai-governance` (#323), `evidence-audit-readiness` (#324).
- [ ] Add `tests/test_control_catalog.py`. It:
  - reads the table under "## Framework mapping" in the matrix and takes the
    `(#nnn)` from each row;
  - asserts that the set of issue numbers in the catalog equals the matrix's set;
  - asserts that the ids are unique, kebab-case, and that `version` is a positive int.
- Check: run `uvx --with pytest pytest tests/test_control_catalog.py -q`, which
  should pass. Then delete one catalog entry by hand and confirm the test fails.
  Restore the entry afterwards.
- Traps: `tests/` is collected by `contracts.yml` (`pytest tests/ ...`), so no
  workflow edit is needed. Read the matrix file with `encoding="utf-8"`.

### 2. PFactory: vendor the catalog, check its drift, move the pin

Coder: **agy**. Worktree: `../PFactory-1961`, made from `origin/dev`. Branch:
`feat/1961-governance-header`.

- [ ] Copy the hub's `apis/control-catalog.json` byte for byte to
  `apps/backend/plan/emit/contracts/control-catalog.json`.
- [ ] Change `scripts/check_schema_drift.py`:
  - Add `_CATALOG_VENDORED` and `_CATALOG_RAW`, mirroring `_VENDORED` and `_RAW`
    (lines 41 to 45).
  - After the schema check in `main()`, fetch the canonical catalog through the
    same `fetch_canonical` and compare it with the vendored one using `==`.
  - A mismatch prints the two `version`s and the ids that differ, then exits 1.
  - A deterministic fetch failure exits 1, and a transient failure soft-skips,
    exactly like the schema check.
  - `--canonical` keeps meaning the schema only. Add `--catalog PATH_OR_URL`.
- [ ] In `.github/workflows/ci.yml:34`, set `HUB_SHA` to step 1's merge commit on hub `main`.
- Check:
  - `apps/backend/.venv/bin/python scripts/check_schema_drift.py --ref <new HUB_SHA>`
    prints OK for both checks.
  - Edit the vendored catalog and confirm the exit code is 1, then restore it.
  - Run the script's existing tests: `pytest tests -k schema_drift -q`.
- Traps:
  - Do not reformat the vendored JSON; it must match byte for byte.
  - If moving the pin shows task-contract schema drift, stop and report it. Do
    not sync the schema in this PR.

### 3. PFactory: signature schema 2 and `controls[]`

Coder: **Codex**. Same worktree.

- [ ] In `apps/backend/plan/emit/docs/render.py`:
  - Set `SIGNATURE_SCHEMA = 2`.
  - Give `render_plan_docs` and `_run_signature` a keyword
    `control_catalog: dict | None = None`.
  - Add the keys from the decisions above. They come from:
    - `session.epic.deployment` (`EpicPlan.deployment`, a dict or None) for
      `risk_class`, `required_scans`, `system_gates` and `production_classification`;
    - `session.plan.autonomy_tier`;
    - the contract's `execution.routing`, read through the same defensive path as
      `_routing_verdict`, for `autonomy_verdict`;
    - the contract `compliance.data_classes`, read from
      `(session.contract_result or {}).get("contract")`;
    - `review.human_approval`, used only when `approved` is true. An empty
      `approved_by` or `approved_at` becomes `None`.
- [ ] Import `_PERSONAL_DATA_CLASSES` from `plan.emit.skills_block` rather than copying it.
- [ ] Add a pure `_controls_engaged(session, catalog) -> list[str] | None` with these rules:

  | Evidence | Id |
  |---|---|
  | always | `audit-logging` |
  | `required_scans` contains `secret-scan` | `secrets-management` |
  | `required_scans` contains `dependency-audit` | `supply-chain`, `vuln-mgmt` |
  | `required_scans` contains `sast` or `iac-scan` | `vuln-mgmt` |
  | `system_gates` contains `human-approval`, or human approval is approved | `change-mgmt-sod` |
  | `production_classification == "production"` | `change-mgmt-sod`, `runtime-isolation` |
  | personal-data class present | `data-governance` |
  | `injection_scan` verdict is not `"not-run"` (and not missing) | `agentic-ai-governance` |

  - The result is sorted and has no duplicates.
  - If the catalog is `None`, return `None`.
  - If any id is not in `{c["id"] for c in catalog["controls"]}`, return `None`
    (the caller logs it).
  - Set `controls_basis` to `"gates-engaged"` when `controls` is a list, and to
    `null` otherwise.
  - Set `control_catalog_version` from `catalog["version"]`, or `null`.
- [ ] In `apps/backend/plan/emit/docs/emit_docs.py`:
  - Add `_control_catalog()` next to `_app_version()`, with the same
    `@lru_cache(maxsize=1)`. It reads
    `Path(__file__).resolve().parents[1] / "contracts" / "control-catalog.json"`
    and returns `None` on any exception.
  - Pass `control_catalog=_control_catalog()` at the `render_plan_docs` call (line 163).
- [ ] Extend `tests/test_plan_docs_run_signature.py`:
  - Assert `signature_schema == 2` and that every new key is present.
  - For each field, test a present case and an absent case. The absent case must
    never give `"low"` or `""`. Note that the `processed` fixture has no
    deployment, contract or approval, so it is the all-absent case.
  - One test for each `_controls_engaged` rule. Use a session stub, or set
    `session.epic.deployment` and `session.contract_result` on `processed`.
  - An unknown id in the catalog case gives `None`, and no catalog gives `None`.
  - The existing idempotency test also covers the new keys.
  - **Purity:** render twice, the second time with `os.environ` cleared
    (`monkeypatch`) and `chdir` to `tmp_path`, and assert identical JSON. Then
    check this test against a mutation: temporarily make `render.py` load the
    catalog from disk through a relative path, and confirm the test fails. Revert
    the mutation, and report it in the step's output.
- Check: `apps/backend/.venv/bin/pytest tests/test_plan_docs_run_signature.py -q`
  passes, and the full suite `pytest tests/ -m "not slow" -q` passes.
- Traps:
  - `render.py` must not import `emit_docs` or open files.
  - `session.epic` can be `None`.
  - `deployment` and `contract` are open dicts, so read them with `.get` and `isinstance`.
  - Strict mypy and ruff run on changed files through the ratchet.

### 4. PFactory: the query CLI

Coder: **agy**. Same worktree.

- [ ] Add `apps/backend/plan/governance_cli.py`, in the same style as `plan/access_cli.py`:
  - Pure functions `scan(root) -> (rows, counts)` and
    `select(rows, control=, tier=, since=)`, plus a formatter and a thin `main(argv)`.
  - `scan` reads `<root>/registry.json`. The `plans` dict is keyed by
    `correlation_key`; see `targets/registry.py`.
  - For each row it reads `signature_file`. A row with no signature, or a file
    that is missing or can't be parsed, counts as `unsigned`.
  - A signature with `signature_schema < 2` counts as `schema1`. It never matches
    a `--control` or `--tier` filter, and it is never counted as a non-match.
  - The output ends with
    `scanned N rows, M with a signature, S schema-1, U without a signature, K matched`.
  - `--json` emits `{"matches": [...], "counts": {...}}`.
  - Each match has: `correlation_key`, `title`, `autonomy_tier`,
    `autonomy_verdict`, `approved_by`, `approved_at`, `originator`, `risk_class`
    and `created_at`.
  - `--since` compares the `created_at` ISO date as a string prefix (YYYY-MM-DD).
- [ ] Fixtures go in `tests/fixtures/governance/`:
  - a registry with four rows;
  - a schema-2 match;
  - a schema-2 non-match;
  - a schema-1 signature, which is a byte copy of the live PVC file if the session
    supplies one, and otherwise the output of the current schema-1 render that the
    session captures before step 3;
  - a TFactory-style row with no `signature_file`.
- [ ] Add `tests/test_governance_cli.py`. It asserts the exact count line, the
  match set for `--control change-mgmt-sod`, and `--tier`, `--since` and `--json`.
- Check: `apps/backend/.venv/bin/pytest tests/test_governance_cli.py -q` passes.
- Traps: no network and no server. The CLI reads files only, and a malformed row
  is counted, never raised.

### 5. Docs and cluster check

Done by the session.

- [ ] Add a short section to the PFactory docs page that documents the run
  signature (find it with `grep -rl "run.json" docs/`): the schema 2 keys and the
  absent-value rule.
- [ ] Add one line to Factory `docs/compliance/control-matrix.md` that points at
  `apis/control-catalog.json`.
- [ ] After the PFactory PR merges and deploys: emit one plan with
  `PFACTORY_DOCS_EMIT=1` and compare the written `run.json` with the table in the
  decisions above. Report the result on #1961.

## Tests

| Where | Command | Expected |
|---|---|---|
| Hub | `uvx --with pytest pytest tests/test_control_catalog.py -q` | passes; fails when an entry is removed |
| PFactory | `apps/backend/.venv/bin/pytest tests/ -m "not slow" -q` | passes |
| PFactory | `apps/backend/.venv/bin/python scripts/check_schema_drift.py --ref <HUB_SHA>` | OK for the schema and OK for the catalog |
| PFactory | the purity mutation in step 3 | the test fails while the mutation is in place |

## Rollback

- Revert the PFactory PR. Schema-2 files already written stay readable, because
  only keys were added.
- Revert the hub PR only after PFactory's pin no longer points at it.

## Execution

- Step 1: Codex. Its test is stricter than the plan asked: it also checks each
  domain name and the row order against the matrix. Verified by the session: the
  test passes, and fails when an entry is removed.
- Step 5 (hub half): the pointer line in `control-matrix.md` lands in step 1's PR,
  so the hub needs only one PR.
