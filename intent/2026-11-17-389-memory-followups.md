---
status: draft
issue: 389
author: olafkfreund
---

# Intent: RFC-0021 memory follow-ups (locks, Graphiti caps, PF/TF pool)

## Problem

RFC-0021 phases 3-5 shipped (AIFactory#2091, PFactory#1039, TFactory#1540).
RFC section 6.2 lists three gaps still open:

1. (b) `confirmed.json`, `scratchpad.json` and the gotchas files are read, changed
   and rewritten with no lock. Two processes (coder, QA, a hook) can lose each
   other's writes. Tracked in #3796.
2. (c) The Graphiti write path (`save_to_graphiti_async`, `append_gotcha`,
   `append_pattern`) skips the per-session caps and the "unverified" source rule
   that the file path obeys. Tracked in #3797.
3. (a) PFactory and TFactory recall dead ends within one spec only: they have no
   project pool, unlike AIFactory. Tracked in #3795.

## Proposed outcome

- A small cross-process lock guards every read-modify-write of those files. A
  writer that cannot get the lock in a bounded time does not write.
- Graphiti receives no more items than the file path would keep, and gotchas
  written while the trust window is open carry the "unverified" marker. No new
  Graphiti feature.
- PFactory and TFactory seed a spec's memory from, and file it back to, a pool
  derived from the project directory only. A dead end that failed twice in one
  project is recalled by the next spec of that project, never by another project.
- The pool copy no longer replaces files wholesale: it merges (higher count and later
  stamp win, gotchas are unioned), so a stale spec snapshot cannot erase newer
  observations or marks (RFC 6.2 stale-snapshot gap).
- Each gate has a mutation check. Store growth and retrieved tokens are measured
  as in RFC section 6.2 and the RFC is updated.

## Affected users and systems

AIFactory, PFactory, TFactory `apps/backend/memory/` and the memory tools
(vendored tree: all three or none, one PR per repo). RFC-0021 section 6.2 and
epic #389 checkboxes in the Factory hub.

## Constraints

- Owner decisions stand: memory stays project-scoped; `dead_end` is never shared
  across projects; Graphiti is not extended.
- No new dependency; Linux pods (fcntl is stdlib).
- A lock failure must never fail a build session.
- If item (a) (PF/TF pool) proves larger than one PR per repo, do (b) and (c)
  first and leave #3795 open as the follow-up.

## Open questions

None. (Owner delegation 2026-11-17: take the recommended option.)
