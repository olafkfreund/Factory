---
status: approved
issue: 389
author: olafkfreund
---

# Intent: close RFC-0021's open questions and split Phases 3-5

## Problem

Epic #389 has Phases 0-2 done but its body still shows Phases 1-2 unticked, and RFC-0021 §8 still lists three open questions (tenant scope, dead-end sharing, Graphiti). Phases 3-5 are one-line bullets that cannot be picked up. The epic also bundles vendored code in three repos (AIFactory, PFactory, TFactory), which must land together.

## Proposed outcome

- RFC-0021 records a decision for each §8 question and a status line that matches the merged state.
- Phases 3, 4 and 5 are separate issues with scope, the all-three-or-none rule and acceptance measures, and the epic body ticks Phases 1-2 and links them.
- Epic #1958 body is corrected (its Gap 2 line is stale: #1960 closed).

## Affected users and systems

Maintainers planning the memory work. Docs and issue text only; no code.

## Constraints

No Aperant code (AGPL). No code change in this slice: Phase 3 is the largest change and needs its own spec.

## Open questions

None. Decisions by owner delegation (2026-11-16): memory stays project-scoped, on the condition that no read path crosses projects (made a Phase 3 acceptance test, because RFC-0020 does not itself guarantee one tenant per project); `dead_end` is not shared across projects; Graphiti is not extended (no GRAPHITI env was set when last observed, RFC §0), Phase 3 builds on the file store.
