---
status: draft
issue: 943
spec: spec/2026-10-22-943-enforce-admins-main.md
---

# Plan: enforce_admins on main for the five code repos

Approved decisions, carried over from the spec:

- Owner's decision, option 2 of #943: `enforce_admins` is ON for `main` of
  AIFactory, PFactory, TFactory, CFactory and Factory. It is OFF for
  factory-gitops `main`, whose CD bot pushes directly to main, and OFF for
  every `dev`.
- Mechanism: a per-branch override `ENFORCE_ADMINS_MAIN`, in the same shape as
  `CHECKS_DEV`. It is reset at the top of `repo_config()`. The `main` arm of
  `build_payload()` uses it when it is set and otherwise falls back to
  `ENFORCE_ADMINS`.
- The comment that justifies `enforce_admins=0` records the decision and the
  break-glass step.
- No call to GitHub. Trivy, CodeQL and security lint promotion are out of
  scope. The PR refs #943 and does not close it.

## Steps

1. `scripts/apply_branch_protection.sh`
   - At about line 109, document `ENFORCE_ADMINS_MAIN` in the field list.
   - At lines 115-116, replace the `enforce_admins is 0` paragraph with the
     decision and the break-glass step.
   - At about line 217, add `ENFORCE_ADMINS_MAIN=""` next to `CHECKS_DEV=""`.
   - In the arms for the five code repos (lines 219-240), add
     `ENFORCE_ADMINS_MAIN=1`.
   - In `build_payload()` (about line 336), add a local `ea="$ENFORCE_ADMINS"`.
     The `main` arm sets `ea="${ENFORCE_ADMINS_MAIN:-$ENFORCE_ADMINS}"`. Pass
     `$ea` to jq.

   Verify with `bash scripts/apply_branch_protection.sh --emit Factory main | jq .enforce_admins`.
   It prints `true`. For `--emit AIFactory dev` and `--emit factory-gitops main`
   it prints `false`.

   Traps: the globals are set by case arms, and the reset is what stops leaks
   (#691). Keep `ENFORCE_ADMINS=0` on every arm, because dev reads it.
2. `tests/test_branch_protection_intent.py`
   - Add an `enforce_admins: bool = False` keyword to `_live_shaped`.
   - In `test_matching_live_response_compares_equal`, pass
     `enforce_admins=(branch == "main" and repo != "factory-gitops")`.
   - Add a parametrized test over `_DECLARED` that asserts the decision table.

   Verify with `pytest tests/test_branch_protection_intent.py -q` and
   `ruff check` plus `ruff format --check` on the file.

   Traps: the mutation test `enforce-admins-imposed` uses TFactory dev, which
   stays false. Leave it as is.
3. `docs/compliance/branch-protection.md`: in the current-state line ("enforce_admins
   is false everywhere"), the "How the bypass works" section and Phase 4, record
   the decision. Note that the live state changes only after `--apply`.

   Verify by reading the result.

   Traps: none.

## Tests

- `pytest tests/test_branch_protection_intent.py -q` passes. The new test fails
  without step 1.
- `bash scripts/apply_branch_protection.sh --plan` is offline: it prints
  payloads and writes nothing. It shows `"enforce_admins":true` on the five
  main payloads only.
- `shellcheck scripts/apply_branch_protection.sh`, if it is installed.

## Rollback

Revert the commit. If it has already been applied, also rerun
`scripts/apply_branch_protection.sh --apply` after the revert, so live
protection goes back to `enforce_admins=false`.
