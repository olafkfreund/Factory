---
status: draft
issue: 813
author: olafkfreund
---

# Intent: a CodeQL ratchet for the fleet

## Problem

Factory#813 found 2,059 open CodeQL alerts that nobody read. No gate fails when
the count of serious alerts rises, so a new high or error alert is invisible
among the notes. Cleanup PRs fix today's alerts, but nothing stops them coming
back.

## Proposed outcome

Each code repo (PFactory, AIFactory, TFactory, CFactory) runs a weekly check
that counts its open alerts at critical, high, error and medium severity and
fails if any count is above a committed baseline. The failure prints the delta.
Lowering the baseline is a normal PR; raising it is a visible decision.

## Affected users and systems

Factory (reusable workflow and script), and the four code repos (a caller
workflow and a baseline file each). Maintainers see a red weekly run.

## Constraints

- GITHUB_TOKEN reads only its own repo's alerts, so the check must run inside
  each calling repo, hence a reusable workflow.
- Permissions: `security-events: read`, `contents: read` only.
- The caller pins Factory's workflow the way the deploy-drift callers do.
- The baseline is today's counts after this sprint's cleanup PRs.

## Open questions

None.
