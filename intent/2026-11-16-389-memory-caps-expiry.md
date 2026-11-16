---
status: draft
issue: 389
author: olafkfreund
---

# Intent: RFC-0021 baseline and Phase 2 (per-session-type caps, last_confirmed_at, demotion)

## Problem

Two things in epic #389 are open and unblocked.

1. The baseline exists but is not in the RFC and says nothing about the
   post-Phase-1 store. AIFactory `docs/dev/memory-baseline-2026-10.md` (measured
   2026-10-24 on the live `aifactory-demo` pool, 33 items, 19 exact and 80
   lexical near pairs, 15 of 33 being `Implemented subtask:` boilerplate) predates
   Phase 1. Nobody has recorded a number from any other store, and RFC-0021
   section 6 still says the figure "should be recorded".
2. Phase 2 does not exist. Nothing bounds how many lessons one session writes,
   and a lesson carries no record of when it was last seen, so a lesson from a
   year ago ranks the same as one from today in what agents read.

## Proposed outcome

- RFC-0021 records the existing live baseline and a second, independent one
  measured here with the same script (`scripts/memory_dup_baseline.py`, read-only)
  on the five local project stores, with method and limits: they are
  pre-Phase-1 stores, and the finding is that the pairs are boilerplate, not
  lessons.
- Each session writes at most N lessons, N set by session type (RFC section 3.3:
  build 20, planning 5, verification 8, insights 5, docs-only 0). A session
  type is the service default (AIFactory build, PFactory planning, TFactory
  verification), an env override, or an explicit argument. No existing caller
  is reclassified, so "docs-only writes nothing" holds only for sessions a
  caller explicitly classifies as docs; that wiring is out of scope.
- Each file-backed lesson carries a `last_confirmed_at`. Re-observing it (the
  Phase 1 repeat gate rejecting it) refreshes it. A lesson not re-observed
  within a window is demoted: still shown to the agent, after fresh lessons and
  labelled low confidence. Past a longer window it is no longer loaded.
  Nothing is deleted from disk.
- Same behaviour in AIFactory, PFactory and TFactory (RFC section 7).

## Starting points differ

Project-level pooling (Phase 0, AIF#1031/#1034/#1035) exists only in AIFactory.
PFactory and TFactory read and write per-spec memory only (`memory/paths.py`
has no project store). Caps and expiry work identically on whichever store a
service has; making PF/TF lessons durable across specs is a separate Phase 0
port and is not part of this change.

Scope is the file-backed store only. When Graphiti is enabled the write in
`agents/memory_manager.py` goes to the graph and returns before the file writer,
bypassing the caps; that path stays as it is and is listed as a known gap.

## Affected users and systems

`apps/backend/memory/` and `agents/tools_pkg/tools/memory.py` in AIFactory,
PFactory, TFactory (dev branches). Factory: RFC-0021 text and the epic. No
task-contract change, no new dependency, no cluster or gitops change.

## Constraints

- Phase 1's exact-repeat gate stays as is; this builds on it. No embedder.
- Never lose data silently: demotion and expiry act at read time only; files are
  never rewritten or removed by this change.
- Baseline reads only local files (project memory dirs under the owner's
  checkouts). No customer data, no cluster reads (the October figure is cited,
  not re-measured).
- Must tolerate old stores with no `last_confirmed_at`.

## Open questions

- Windows: 30 days to demote and 90 to stop loading are starting values, to be
  tuned once a pooled project has real accumulation (the local baseline shows
  there is almost none).
