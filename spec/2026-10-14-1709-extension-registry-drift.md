---
status: draft
issue: 1709
intent: intent/2026-10-14-1709-extension-registry-drift.md
---

# Spec: a drift check for PFactory's vendored extension registry

## Design

The change goes in PFactory's `scripts/check_schema_drift.py`, which already
runs in CI at the pinned `HUB_SHA`. Since #1961 it compares the control catalog
with `==` in `_check_catalog`.

- Generalise `_check_catalog` into one equality check. It takes:
  - a name;
  - the vendored path;
  - the hub path, used to build the raw URL at `--ref`;
  - an optional detail function for the failure message.

  The catalog keeps its current detail (the differing ids). The extension
  registry lists the top-level keys whose values differ, plus `version` if it
  has one.
- The fetch logic is reused unchanged. A transient failure soft-skips with a
  loud warning, and a deterministic failure fails the check.
- Add `--extension-registry PATH_OR_URL`, mirroring `--catalog`.
- `main()` runs the schema check, the catalog check and the registry check. It
  returns 1 if any of them fails, and runs all three so one failure doesn't hide
  another.
- The vendored file is `apps/backend/plan/emit/contracts/extension-registry.json`
  (the same path as `_VENDORED` in `plan/review/extension_registry.py`). The hub
  file is `apis/extension-registry.json`.

## Alternatives rejected

- **A hub-side job reading PFactory `dev`.** Rejected at intent approval.
- **A byte (`cmp`) comparison.** The catalog check compares parsed JSON. Using
  the same comparison keeps one rule for both files and ignores differences in
  file encoding.
- **A separate script or workflow step.** That would duplicate the fetch and
  soft-skip logic, which already exists in this step.

## Risks

- **The copies differ when the check lands.** Today they are identical at
  `f53f32b`, the current `HUB_SHA`, and on hub `main`.
- **A hub-only edit is picked up only at the next pin bump.** That is
  intended; it is the fleet pattern.

## Verification

- The existing `tests/test_schema_drift.py` tests still pass.
- A new test passes on a matching registry and returns 1 on a mismatched one,
  and its message names the differing key.
- A local-hub sync test for the registry, like the catalog's: it skips when no
  Factory checkout is present.
- `check_schema_drift.py --ref <HUB_SHA>` prints three OK lines.
