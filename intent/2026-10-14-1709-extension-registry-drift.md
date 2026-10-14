---
status: draft
issue: 1709
author: olafkfreund
---

# Intent: a drift check for PFactory's vendored extension registry

## Problem

PFactory keeps its own copy of the hub's `apis/extension-registry.json` (RFC-0015
D3) at `apps/backend/plan/emit/contracts/extension-registry.json`. Nothing checks
that the two copies match. PFactory's `plan/review/extension_registry.py` reads
its own copy first.

The registry decides which review lenses and runtimes are switched on
(`enabled: false` switches one off). If the copies drift apart, the hub and
PFactory disagree about which checks run, and no CI job notices. #1708 and
PFactory#675 were brought back into sync by hand.

On 2026-10-14 the copies are byte-identical, both at PFactory's pinned
`HUB_SHA` (`f53f32b`) and on hub `main`.

## Proposed outcome

PFactory CI fails when its copy of `extension-registry.json` differs from the
hub's copy at the pinned `HUB_SHA`. It uses the same step and the same
whole-file comparison that the control catalog has used since #1961
(`scripts/check_schema_drift.py`).

## Affected users and systems

- PFactory: `scripts/check_schema_drift.py` and its tests, which run in the
  existing CI step. The vendored file does not change.
- Hub: none.

## Constraints

- Sync the copies before turning the check on. They already match, so no sync
  is needed.
- Reuse the catalog check's fetch, soft-skip and fail-hard logic. No new script
  and no new workflow.

## Open questions

1. **Do we also need a check on the hub side** that fetches PFactory's copy
   from `dev`? *Recommend no.* The pinned check is the pattern every other
   vendored file in the fleet uses. A change made only in the hub reaches
   PFactory at the next pin bump, and that bump fails if the copies differ.
   A hub job that reads PFactory's `dev` would turn red because of a change in
   another repository that nobody had reviewed yet.
2. **Is a full intent, spec and plan needed for this?** It is about 15 lines
   in one script plus a test, in a file #1961 just reviewed. *Recommend
   approving the spec and plan unseen together with this intent.*
