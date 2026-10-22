---
status: approved
issue: 943
author: olafkfreund
---

# Intent: enforce_admins on main for the five code repos

## Problem

`enforce_admins` is `false` on every protected branch in the fleet
(`scripts/apply_branch_protection.sh`). Required checks therefore do not bind a
repository admin, and the fleet's merges are admin merges. The 2026-10-07 probe
recorded on #943 showed an admin merging past a red required check with a plain
`PUT repos/.../pulls/N/merge`. The "red required check cannot be merged" floor
holds today only because every client happens to call `gh pr merge` without
`--admin`. It is `false` by default, not by decision, and #943 asks for the
decision to be made and recorded.

## Proposed outcome

- The owner's decision (option 2 of #943) is declared in the intent table:
  `enforce_admins` ON for `main` of AIFactory, PFactory, TFactory, CFactory and
  Factory.
- `factory-gitops` main stays OFF: its CD bot pushes `cd(...) [skip ci]`
  commits straight to main and relies on the admin bypass.
- Every `dev` branch stays OFF, so it remains bypassable during an incident.
- The script comment records the decision and the break-glass step.
- Check mode reports drift until someone runs `--apply`. This PR does not apply
  anything to GitHub.

## Affected users and systems

- `scripts/apply_branch_protection.sh` (intent table, `build_payload`).
- `tests/test_branch_protection_intent.py` (offline tests of the emitted intent).
- `docs/compliance/branch-protection.md` (rationale prose).
- Once applied: admins merging into `main` of the five repos. Release PRs and
  sync PRs must pass required checks like anyone else's.

## Constraints

- Must not run the script against GitHub from this lane.
- Must not break the factory-gitops CD bot.
- Must not change `dev` behaviour.
- Trivy, CodeQL and security-lint promotion (part 1 of #943) are out of scope.

## Open questions

None. The owner chose option 2.
