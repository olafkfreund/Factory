---
status: approved
issue: 392
author: olafkfreund
---

# Intent: Close out epic checklists after the 2026-11-18 merges

## Problem

Many PRs merged on 2026-11-18 (RFC-0022 Phases 3-5, gateway routes ConfigMap, WS review follow-ups) but the epic and issue checklists (#392, #1959, #1958, #312, #324, #310, #314, #3701, #3775, #3776) still show the earlier state. A reader cannot tell what is done, what waits for the owner and what an agent can still do.

## Proposed outcome

Each issue body or a status comment states the current truth with evidence (PR numbers, merge SHAs, live read-only checks). A box is ticked only when its acceptance is verifiably met. Nothing is closed unless everything in it is met.

## Affected users and systems

Issue text on olafkfreund/Factory only. No code, no cluster change (read-only kubectl get).

## Constraints

- Never tick a box whose acceptance is not met; owner-only items stay unticked.
- #392 Phases 3-5 are ticked with "code merged, flag off; live smoke test pending (owner)" only after checking flags, tests and the Alembic head in the tree.
- #3775, #3776, #3701 and all epics stay open.

## Open questions

None. Owner delegation 2026-11-18 records the recommended option for each.
