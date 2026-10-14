---
status: draft
issue: 1961
intent: intent/2026-10-14-1961-artifact-governance-header.md
---

# Spec: governance fields in the PFactory run signature

All paths in PFactory are relative to `apps/backend/` on `dev` unless they say otherwise.

## Design

### 1. The control catalog lives in the hub (Factory)

`apis/control-catalog.json` is a new file:

```json
{ "version": 1,
  "controls": [ { "id": "change-mgmt-sod", "domain": "Change mgmt & SoD", "issue": 316 }, ... ] }
```

- It has one entry for each of the 14 rows in `docs/compliance/control-matrix.md`.
  Each `id` is a kebab-case slug and each `issue` is the domain's Factory issue
  (#311 to #324).
- A hub test, `tests/test_control_catalog.py`, parses the matrix table and
  fails unless the catalog and the matrix list the same issue numbers, one for one.
  If someone adds a domain in one place and not the other, the test fails.
- The catalog `version` goes up only when an id is renamed or removed. Adding an id
  is backward-compatible.

### 2. PFactory vendors the catalog

- PFactory keeps a copy at `plan/emit/contracts/control-catalog.json`.
- `scripts/check_schema_drift.py` already does a byte-identical comparison against
  the hub for `task-contract.schema.json`. It gains a second entry for the catalog,
  using the same code path and the same CI job. There is no new mechanism.

### 3. Signature schema 1 → 2 (`plan/emit/docs/render.py::_run_signature`)

The new fields are flat keys added next to the existing ones. No existing key
changes meaning. Each field comes from a value the session already holds, so
filling it is a copy:

| Key | Source | When absent |
|---|---|---|
| `risk_class` | `session.epic.deployment["risk_class"]` (RFC-0013 `_derive_risk_class`) | `"unknown"`, **never `"low"`** |
| `risk_class_basis` | `"deployment-block"` or `"absent"` | — |
| `autonomy_tier` | `session.plan.autonomy_tier` (RFC-0011 label: low, medium or hard) | `"unknown"` |
| `autonomy_verdict` | contract `execution.routing` (RFC-0014: autonomous, review or approval), from the data `_routing_verdict` already reads | `null` |
| `data_classification` | `"Regulated"` when contract `compliance.data_classes` includes a personal-data class (the `_PERSONAL_DATA_CLASSES` set in `plan/emit/skills_block.py`, reused, not copied) | `"unknown"` |
| `data_classification_basis` | `"compliance-data-classes"` or `"absent"` | — |
| `approved_by`, `approved_at` | `review.human_approval` when `approved` is true | `null` (never `""`) |
| `controls` | see section 4 | `null` |
| `controls_basis` | `"gates-engaged"` | `null` together with `controls` |
| `control_catalog_version` | the injected catalog's `version` | `null` |
| `change_id`, `originator`, `agent_identity`, `model_route` | not yet available (ITSM, #1960, #1959) | always `null` in schema 2 |

`data_classification` deliberately never says `Internal` or `Confidential`.
Nothing in the run can tell those two apart, and guessing either one would be a
plausible wrong value. The run can only prove that personal data is present.

`SIGNATURE_SCHEMA` becomes `2`. A schema-1 file still parses, because every new
key is simply missing from it. A reader treats a missing key as "not recorded",
which is different from `null`, meaning "recorded as not established".

### 4. `controls[]` lists the domains this run's gates engaged

This is a pure function, `_controls_engaged(session, catalog)`, in `render.py`.
Each rule needs evidence that is already on the session:

| Evidence on the session | Catalog id |
|---|---|
| always: the signature itself is an audit record | `audit-logging` |
| deployment `required_scans` contains `secret-scan` | `secrets-management` |
| `required_scans` contains `dependency-audit` | `supply-chain`, `vuln-mgmt` |
| `required_scans` contains `sast` or `iac-scan` | `vuln-mgmt` |
| deployment `system_gates` contains `human-approval`, or `review.human_approval.approved` | `change-mgmt-sod` |
| `production_classification == "production"` | `change-mgmt-sod`, `runtime-isolation` |
| contract `compliance.data_classes` contains a personal-data class | `data-governance` |
| `session.injection_scan` ran (its verdict is not `"not-run"`) | `agentic-ai-governance` |

- The output is sorted and has no duplicates.
- Any id the rules produce must exist in the injected catalog. If one doesn't,
  the render records `controls: null` and logs the missing id, so it cannot
  emit an id the catalog doesn't know.
- If no catalog was injected (it failed to load), the result is `controls: null`.
- `[]` cannot happen, because `audit-logging` is always present.

### 5. `render.py` stays pure

- `emit_docs.py` loads the catalog in `_control_catalog()`. That function sits
  next to `_app_version()`, uses the same `@lru_cache(maxsize=1)`, and returns
  `None` on any failure.
- The catalog is passed into `render_plan_docs(..., control_catalog=...)` the same
  way `pfactory_version` is.
- `render.py` never opens a file.

### 6. The query CLI

There is a new module, `plan/governance_cli.py`, run as `python -m plan.governance_cli`:

```text
python -m plan.governance_cli --root <docs dir> --control change-mgmt-sod
```

- It reads `registry.json` under `--root`, then the `signature_file` of each row.
- It prints one line per match: correlation key, title, `autonomy_tier`,
  `autonomy_verdict`, `approved_by`, `approved_at`, `originator`, `risk_class`.
- It always ends with a count of everything it read:
  `scanned N rows, M with a signature, S schema-1, U without a signature, K matched`.
  - Rows without a signature (TFactory's fork, or failed writes) are counted, never dropped.
  - Schema-1 signatures are counted as "controls not recorded", never as a non-match.
- `--json` gives output a machine can read.
- The filters are `--control`, `--tier` and `--since`. `--since` filters on `created_at`.
- The CLI is pure functions plus a thin `main`, like `plan/access_cli.py`. It has
  no index, because the registry already points at every signature.

## Alternatives rejected

- **A nested `governance{}` block.** Rejected at intent approval: we keep flat keys.
- **`controls[]` as the controls this change touches.** PFactory can't know that at
  plan time. It belongs at merge time in AIFactory, as a different epic.
- **Deriving `Internal` or `Confidential` from plan text.** That would be a guess,
  so the field says `unknown` instead.
- **`autonomy_tier` from the RFC-0014 scorer.** The scorer measures something
  else. Both values are kept, under different keys.
- **Loading the catalog inside `render.py`.** It would break purity, and the
  reproducible render depends on it.
- **A search index for the CLI.** The registry is small and already holds the
  pointers, so an index would be a second copy that drifts.
- **Threading `originator` now.** This waits for #1960's actor format. The field
  ships as `null`.

## Risks

- **A schema-1 reader sees `signature_schema: 2`.** Nothing in the fleet reads the
  field today; only `render.py` and its tests use it. Low risk.
- **The catalog and matrix drift apart.** The hub test fails if either changes alone.
- **Vendored-copy drift.** The existing drift job in PFactory CI catches it.
- **The corpus is one signature (n=1).** The CLI is proven on fixtures, not on real
  volume. Step 5 of the plan re-runs the emit on the cluster and compares the
  real file with the expected output.
- **No runtime change to planning.** Only the emitted JSON grows. The emit is
  off unless `PFACTORY_DOCS_EMIT` is set, and is best-effort.

## Verification

- Hub: `test_control_catalog.py` passes. A mutation that removes one catalog entry
  makes it fail.
- PFactory unit tests:
  - Each table row in section 3 has a present case and an absent case.
  - Absent values are checked to be `"unknown"` or `null`, never `"low"` or `""`.
  - Each rule in section 4 has a test.
  - An id missing from the catalog gives `null`.
  - No catalog gives `null`.
- Purity:
  - The existing double-render idempotency test is extended to the new keys.
  - A render with `os.environ` cleared and the working directory changed gives
    the same bytes.
  - **A mutation that makes `render.py` read the catalog off disk turns that test red.**
- Compatibility: a byte copy of the live PVC
  `004-find-friend-create-profile-mvp.run.json` (schema 1) parses in the CLI and
  is counted as schema-1.
- CLI fixtures: a schema-2 match, a schema-2 non-match, a schema-1 row, and a
  TFactory row with no signature. The fixtures check the count line exactly.
- On the cluster: emit one plan with `PFACTORY_DOCS_EMIT=1` and compare the
  written `run.json` against this table.
