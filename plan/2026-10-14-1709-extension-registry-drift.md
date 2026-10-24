---
status: approved
issue: 1709
spec: spec/2026-10-14-1709-extension-registry-drift.md
---

# Plan: a drift check for PFactory's vendored extension registry

## Decisions carried over

- PFactory-only. The check runs against the pinned `HUB_SHA`, inside the
  existing `check_schema_drift.py` CI step.
- It compares parsed JSON with `==`, reusing `fetch_canonical` (soft-skip on a
  transient failure, fail hard otherwise).
- `main()` runs all three checks (schema, catalog, registry) and returns 1 if
  any of them fails.
- On a mismatch, the message names what differs: ids for the catalog,
  top-level keys for the registry.

PFactory worktree: `../PFactory-1709`, made from `origin/dev`. Branch:
`feat/1709-extension-registry-drift`. Base branch: `dev`.

## Steps

1. Coder: **Codex**. In `scripts/check_schema_drift.py`:
   - Replace `_check_catalog(catalog_source)` with
     `_check_equal(name, vendored, source, detail)`. `detail` is a callable
     `(canonical, vendored) -> str` that adds lines to the failure message.
     Keep the fetch and soft-skip blocks exactly as they are.
   - The catalog call passes a detail built from `_catalog_diff_ids`, so the
     current output stays the same, including the "Sync … with …" hint.
   - Add `_REGISTRY_VENDORED = <repo>/apps/backend/plan/emit/contracts/extension-registry.json`
     and `_REGISTRY_RAW = .../{ref}/apis/extension-registry.json`.
   - The registry's detail lists the top-level keys whose values differ, plus
     both `version`s if present.
   - Add `--extension-registry PATH_OR_URL`, mirroring `--catalog`.
   - `main()`: after the schema check passes, compute
     `rc = max(catalog_rc, registry_rc)` with both calls always made, and
     return `rc`. Leave the schema check's early returns as they are.
   - Check: `apps/backend/.venv/bin/pytest tests/test_schema_drift.py -q`
     still passes, and the ratchet passes:
     `PATH=apps/backend/.venv/bin:$PATH python scripts/ratchet_lint.py --base origin/dev --package scripts`.
   - Traps: the module docstring says what the script checks, so extend it to
     name all three files. Keep the existing `--catalog` behaviour, because the
     tests call `main([... "--catalog", ...])`.
2. Coder: **agy**. In `tests/test_schema_drift.py`:
   - Add `test_vendored_registry_in_sync_with_local_hub`, mirroring
     `test_vendored_catalog_in_sync_with_local_hub`.
   - Add `test_registry_match_and_mismatch`, mirroring
     `test_catalog_match_and_mismatch`: a matching registry gives 0. A copy
     with one top-level value changed gives 1, and the output names that key.
     Also assert that a catalog mismatch together with a matching registry
     still returns 1.
   - Update `test_catalog_match_and_mismatch` if its calls now also need
     `--extension-registry` passed to stay offline. Pass the vendored path so
     no test reaches the network.
   - Check: `apps/backend/.venv/bin/pytest tests/test_schema_drift.py -q` passes.
3. The session:
   - Run `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt apps/backend/.venv/bin/python scripts/check_schema_drift.py --ref f53f32bfa37489b8278f8ec6d137fb57efa85974`
     and confirm three OK lines.
   - Add a CHANGELOG line under Unreleased.
   - Commit, open the PR, and close #1709 on merge.

## Tests

| Command | Expected |
|---|---|
| `apps/backend/.venv/bin/pytest tests/test_schema_drift.py -q` | passes |
| `check_schema_drift.py --ref f53f32b` | three OK lines |
| the ratchet on `scripts/` | passes |

## Rollback

Revert the PFactory PR. Nothing else depends on the check.
