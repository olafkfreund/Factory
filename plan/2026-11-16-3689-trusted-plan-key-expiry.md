---
status: draft
issue: 3689
spec: spec/2026-11-16-3689-trusted-plan-key-expiry.md
coders:
  1: you (lead edits directly; two small files, no handoff)
  2: you
reviewers:
  - codex
---

# Plan: trusted-plan key expiry

Implements the approved spec in AIFactory (branch `feat/3689-key-expiry`, base
`dev`). Verifier-side `AIFACTORY_TRUSTED_PLAN_EXPIRY`
(`authority/kid=date` or `authority=date`), fail closed on a bad date, unset =
no change, no envelope or signer change.

## Steps

1. `apps/backend/trusted_plan.py`: add `_NOT_AFTER_ENV`, `load_not_after_from_env(env)`
   returning `{key: datetime}` (bad date -> sentinel that expires always), and
   an optional `not_after`/`now` check inside `_select_verification_key` and
   `verify_plan_signature` (keyword args, default from env / UTC now). Add tests (incl. expiry var is not a keyring entry, before/after-expiry transition, malformed date)
   in `tests/test_trusted_plan.py`. -> `pytest tests/test_trusted_plan.py`, `ruff check`.
   Traps: ruff sorting of "as" aliases (use plain names); keep signature of
   `verify_trusted_plan` unchanged.
2. `docs/docs/compliance/trusted-plan-key-rotation.md` and
   `docs/docs/environment-reference.md`: expiry section, 90/14-day interval,
   owner commands. -> read-through.

## Tests

`cd AIFactory && pytest tests/test_trusted_plan.py apps/web-server/tests/test_trusted_contract_merge.py`.

## Rollback

Revert the commit; unset var already means no behaviour change.
