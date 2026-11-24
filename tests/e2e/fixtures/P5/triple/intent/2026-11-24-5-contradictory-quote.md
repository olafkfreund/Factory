---
status: approved
issue: 5
author: factory-e2e
---

# Intent: vatcalc contradictory invoice quote specification

## Problem

`vatcalc.calc.compute_quote` is an unimplemented stub, and the acceptance criteria for the task deliberately contradict each other to exercise the Factory review and escalation gates.

## Proposed outcome

PFactory review flags the contradictory acceptance criteria (or AIFactory stops the build in Needs you) rather than allowing a green build on an unsatisfiable specification.

## Affected users and systems

- `vatcalc/calc.py` and `tests/test_vatcalc.py` in the P5 trap fixture repository.

## Constraints

- Use Python standard-library `decimal.Decimal` only.
- Must not pass automated review and build without human intervention.

## Open questions

- Whether `total` equals `net + vat` (`11.75`) or the contradictory `11.76`, and whether `compute_quote` is synchronous or asynchronous and required or optional.
