---
status: approved
issue: 3745
intent: intent/2026-11-16-review-gap-fixes-factory.md
---

# Spec: pin-freshness reads factory_common/.hub-sha

## Design

In `scripts/check_pin_freshness.py`:

- `Gate` gains `pin_files: dict[str, tuple[str, ...]]` (default empty): per
  service, the in-repo `.hub-sha` paths holding this gate's pin. Empty means the
  pin is a workflow variable, as today.
- New gate `factory-common`: `canonical_root="shared/factory-common"`, layout
  key `factory_common` (a directory pathspec, since the copy is the whole
  package: its `__init__` imports every sibling), `pin_files`: aifactory
  `apps/backend/...` and `apps/web-server/...`, pfactory and tfactory
  `apps/web-server/...`, cfactory `apps/backend/...` (each `factory_common/.hub-sha`).
  `required_check=False`.
- `_gather`: for a gate with `pin_files`, fetch each file with the existing
  `fetch_workflow` (raw fetch of any path), validate 40 hex, and when a service
  has several pick the one furthest behind (`total_behind`). The older pin's
  moved-commit set is a superset of the newer's, so a stale copy cannot hide
  behind a fresh sibling.
- `scope_problems` also checks that each gate's `pin_files` keys equal its
  layout keys and that no service lists zero files; a test pins the exact five
  paths so dropping AIFactory's second copy fails. Picking the furthest-behind
  pin assumes the pins are commits on the hub's linear squash-merge history
  (the consumer drift gates enforce that).
- The failure footer names the pin files for a `pin_files` gate (bump
  `<path>/.hub-sha` after re-vendoring `factory_common`) instead of `HUB_PIN_SHA`.
- `fetch_pin`/workflow paths unchanged. `unlisted_consumers` only compares
  repos absent from a layout; all four are present, so no change.

## Alternatives rejected

- One gate per AIFactory copy: needs fake service keys that `scope_problems`
  rejects.
- Fail the CFactory-style per-service pin equality: rejected in #519.
- Editing the four consumer repos: out of this repo's scope; the watchdog going
  red is the signal that drives the re-vendor.

## Risks

The daily workflow goes red until the four repos re-vendor (intended). A
`.hub-sha` with whitespace or a short sha: parsed with strip and a 40-hex check;
anything else raises `PinUnavailableError` (never a pass).

## Verification

`tests/test_pin_freshness.py` gains: the gate is declared and reads its own
canonical root; `pin_from_file` rejects non-sha; multi-file pick returns the
older pin; with the pre-#3745 pin `294a62d5` the check FAILS naming b4e2f32
(fails on main because the gate does not exist). `scripts/check_pin_freshness.py --self-test`.
