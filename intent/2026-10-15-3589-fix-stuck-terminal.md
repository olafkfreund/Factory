---
status: approved
issue: 3589
author: olafkfreund
---

# Intent: fix-stuck-tasks.py must not turn a terminal status back into running

## Problem

`apps/backend/scripts/fix-stuck-tasks.py` is forked into AIFactory, PFactory
and TFactory (identical apart from the specs folder and plan file name). It
keeps a list of "valid" plan statuses (`:54-67`) and rewrites any status not
on that list to `in_progress` (`:179-198`). `failed` is not on the list, so a
plan the service closed as `{"status": "failed"}` (the AIFactory#1431
fallback) is rewritten as running. That restores the phantom-running state
AIFactory#1430 removed. The same branch would do the same to any other
terminal value the services write later, because "not on my list" is read as
"must be running".

Found by the Factory#971 audit (`docs/audits/2026-10-14-terminal-status.md`,
section "fix-stuck-tasks.py").

## Proposed outcome

- Running the script on a project never changes a terminal plan status
  (`failed`, `done`, `completed`, `cancelled`, ...) into a non-terminal one.
- A plan status the script does not know is reported, not rewritten.
- Same behaviour in all three forks.

## Affected users and systems

- Operators who run the script by hand against a project directory. Nothing
  in the three repos calls it (no CI, no service, no test references it).
- The services and dashboards that read `implementation_plan.json` /
  `test_plan.json` afterwards.

## Constraints

- One PR per service repo (AIFactory, PFactory, TFactory), base `dev`; the
  artifacts stay in the hub.
- The script stays standalone (stdlib only): the service backends do not
  depend on `factory-contracts`.
- No deploys, no runs against live project data.

## Open questions

- The issue also notes that the script creates `approved:false` review
  states and repairs only the plan file, never control or durable rows, and
  suggests retiring the forks in favour of in-service reconcilers. Retiring
  is a product decision outside this fix; this task fixes the terminal
  rewrite only and leaves the rest recorded on the issue.
