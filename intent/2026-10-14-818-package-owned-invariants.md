---
status: draft
issue: 818
author: olafkfreund
---

# Intent: decide whether the fleet adopts package-owned runtime invariants

## Problem

A check that was never written, never wired up, or quietly stopped running
looks exactly like a check that passed. #818 lists six cases of this
(Factory #805, #807 and #816, AIFactory #1351, PFactory #595 and #601). Its
comments add five more found after those were fixed: Factory #932 and #858,
TFactory #1148, AIFactory #1387 and #1390.

Each was fixed on its own, and new cases kept appearing. The #971 audit found
the runtime version of the same class: final statuses that never reach the
place they are read.

#818 proposes the DeepSeek Harness pattern:
1. every package declares its runtime invariant, or states in writing,
   specifically for that package, why it has none;
2. a central registry that only records which package owns which check;
3. a repository check that **every** package is covered, with its own test;
4. the checks run in production, not only in CI.

Part of it already exists as a PFactory pilot:
- `apps/backend/factory_invariants` (the registry);
- `scripts/check_invariant_ownership.py`;
- PFactory#622.

The pilot falls short of the pattern in three ways, measured 2026-10-14:
- **3 packages are covered** out of about 33 backend packages.
- **The ownership check reads a hand-written list** (`Covered(...)` entries),
  so a new package is invisible to it. That is exactly the gap the pattern
  exists to close.
- **Checks only run if `FACTORY_INVARIANTS=1` is set** and a caller invokes
  `registry.verify_all()`. I found no call in app startup, so nothing runs in
  production.

The hub already points at the pilot in `scripts/check_gate_liveness.py` and
`scripts/check_test_collection.py`. No other repo has it.

The issue also notes the RFC overlaps with the VAL levels in RFC-0006 and
should be reconciled with them rather than added alongside.

## Proposed outcome

An RFC in `docs/rfc/`, numbered 0024, that makes a decision and stands on its
own. It settles:
- whether to adopt the pattern fleet-wide, extend it, or retire the pilot;
- what is in scope: which repos, and what counts as a "package";
- how coverage of every package is enforced, mechanically and with a test;
- how and where the checks run in production, and what happens when one
  fails (fail at startup, or report it);
- how the pattern relates to RFC-0006 VAL levels and to the existing gate
  checks (`check_gate_liveness.py`, `check_test_collection.py`);
- the rollout order and its cost.

The RFC is the deliverable. Implementation is follow-up work, filed as issues
the RFC names.

A small separate issue will propose recording rejected designs, as the
`rejected/` directory does in #818's source material. It's a side idea in
#818 and not part of this RFC.

## Affected users and systems

- The Factory hub (`docs/rfc/`) and any repos the RFC brings into scope:
  PFactory first, then TFactory, CFactory and AIFactory.
- No code changes in this task.

## Constraints

- Measure before deciding. The RFC states the real package counts and the
  cost per repo, rather than estimating them.
- No partial adoption that quietly gives up the guarantee that every package
  is covered. As #818 says, adopting it only for the riskiest packages loses
  the property that makes it work. If the RFC narrows the scope, it must
  still enforce full coverage *within* that scope.
- Placeholder declarations stay forbidden. The pilot's `_PLACEHOLDER` and
  `_EMPTY_REASON_MIN_WORDS` guard is kept.
- No new vendored dependency. This is a pattern to implement, not a library
  to add.

## Open questions

1. **Scope of the decision.** My recommendation is that the RFC adopts the
   pattern **per service**, with every package covered within each service
   it takes on, starting with PFactory, where the pilot is. Other repos
   adopt only after PFactory reaches full coverage and its checks run in
   production. The alternative is the whole fleet at once: about 5 × 30
   declarations up front.
2. **What happens in production when a check fails.** My recommendation is
   to fail readiness (the pod stays not-ready) for invariants the owner marks
   critical, and to log at error level plus a metric for the rest. The
   alternative is that every failure stops startup.
3. **Merge approval in advance.** May I merge this task's docs PR (intent,
   spec, plan and RFC) once CI is green?
