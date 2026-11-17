---
status: draft
issue: 3766
author: olafkfreund
---

# Intent: RFC-0021 Phase 3, scratchpad observation layer and dead_end signals

## Problem

Dead ends are stored as if they worked, or not at all. A session that tries an
approach, abandons it and moves on leaves nothing the next session can use, so
the fleet repeats the same failure. RFC-0021 section 3.1 asks for cheap
structured observations during a session instead of re-reading transcripts.

## Proposed outcome

- A per-store scratchpad of counters and sets (signal kind, normalised key,
  count, last seen). No LLM in the hot path.
- A `record_dead_end` agent tool and a `dead_ends` store, recalled by
  `get_session_context` under a "do not retry" heading.
- Failed subtask attempts feed `error_fingerprint` counters.
- Repeated-failure recall test: after a dead end is recorded, a later session on
  the same project retrieves it.
- A test that the pool path derives from the project directory only (no
  cross-project read), the condition on the tenant decision.
- Store growth per session measured.

## Affected users and systems

AIFactory, PFactory, TFactory `apps/backend/memory/` (new `scratchpad.py`),
`agents/tools_pkg/tools/memory.py`, `services/recovery.py`. Vendored tree: all
three or none. PFactory and TFactory have no project pool, so their dead-end
store is the spec memory dir only; the cross-project test there asserts that no
path outside the spec dir is read.

## Constraints

- Counters and sets only, bounded sizes. dead_end is not shared across projects.
- Graphiti is not extended. Memory stays project-scoped. No Aperant code.
- Hot path must never raise (a lost observation is acceptable).
- Known Phase 2 gap kept: files are not locked across processes.

## Open questions

None open. Decisions (owner delegation 2026-11-17):

- PFactory and TFactory have no project pool, so their recall is same-spec only
  in this round. Project pooling for them was already out of scope in Phase 2
  and stays a follow-up; the PR says so. AIFactory recalls across specs of the
  same project through the existing pool.
- Measures carried: store growth per session, retrieved-memory tokens of the
  dead-end block (bounded by a character cap). Duplicate rate is covered by the
  dead-end key (a repeat increments a counter, never appends).
- Ship the closed signal set of RFC section 3.1 but wire
only `dead_end` and `error_fingerprint`, the two with a producer today; the rest
need producers that do not exist yet.
