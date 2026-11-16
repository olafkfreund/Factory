---
status: draft
issue: 3745
spec: spec/2026-11-16-review-gap-fixes-factory.md
coders:
  1: lead   # single-file logic edit; a handoff costs more than it saves
  2: lead   # tests for step 1 in the same sitting
reviewers:
  - codex   # read-only diff review
---

# Plan: pin-freshness reads factory_common/.hub-sha

Decisions carried from the approved spec: add `Gate.pin_files`; new
`factory-common` gate (canonical_root `shared/factory-common`, layout key
`factory_common`, five `.hub-sha` paths: aifactory apps/backend and
apps/web-server, pfactory/tfactory apps/web-server, cfactory apps/backend);
`_gather` reads each file, validates 40 hex, picks the furthest-behind pin per
service; `scope_problems` asserts pin_files keys == layout keys and non-empty ONLY for gates
with non-empty `pin_files` (default empty = workflow-variable behavior, unchanged,
so the six existing gates are untouched); `required_check=False`; `--pin`
overrides and `--no-fetch` are honored before any fetch;
failure footer names `.hub-sha` for such gates. Consumers are not edited.

## Steps

1. `scripts/check_pin_freshness.py`: add `pin_files` field and `factory-common`
   gate after `test-collection`; add `pin_from_file(repo, body, path)`; extend
   `_gather` and `scope_problems`; footer text per gate kind
   → verify `python3 scripts/check_pin_freshness.py --self-test`.
   Traps: stdlib only; keep `GATES[0]` verification-core; mypy ratchet needs
   typed returns.
2. `tests/test_pin_freshness.py`: tests for gate declaration and root, exact
   five paths, scope guard, bad-sha rejection, multi-file picks older pin, and
   a mocked `_gather` test raising `PinUnavailableError` when either AIFactory file is unreadable/malformed, and the `294a62d5`-era pin failing with b4e2f32 named (fails on main: no gate)
   → verify `python3 -m pytest tests/test_pin_freshness.py`.

## Tests

`python3 scripts/check_pin_freshness.py --self-test` passes; pytest file passes;
repo ruff/mypy per its CI.

## Rollback

Revert the commit; the watchdog returns to its previous six gates.
