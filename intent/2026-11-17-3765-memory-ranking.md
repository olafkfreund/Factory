---
status: approved
issue: 3765
author: olafkfreund
---

# Intent: RFC-0021 Phase 5, rank loaded memory by recency and confirmation age

## Problem

`get_session_context` loads gotchas by cutting the last 1000 characters of the
file. Phase 2 added `last_confirmed_at` and 30/90-day demotion, but inside the
fresh set the order is still file position, and every cut can end in a half
entry (a fragment with no heading or date). A gotcha that was re-observed
yesterday but written months ago sits early in the file and is the first to be
cut; a stale one can fill the leftover budget as a fragment. Memory is loaded
into agent context, so this is token spend on the wrong lines.

## Proposed outcome

Entries are chosen for the 1000-character window by last confirmation (newest
first), whole entries only, and shown in file order. For a fixed fixture the
retrieved token count drops or stays equal while the share of stale entries
(not confirmed within the demotion window) in the loaded set falls. A mutation
check shows the ranking is what produces that.

## Affected users and systems

AIFactory, PFactory and TFactory `apps/backend/memory/retention.py`
(`gotchas_context`) and its callers (`get_session_context`). Vendored tree: all
three or none. Factory hub: RFC-0021 section 6 measures, epic #389.

## Constraints

- Age-based only. No ranking on validation or trust (Phases 3-4).
- No new dependency, no LLM, no embedder. Nothing is rewritten or deleted.
- Memory stays project-scoped. No Aperant code (AGPL).
- Known Phase 2 gaps stay: Graphiti write path bypasses caps; `confirmed.json`
  is not locked across processes.

## Open questions

None open. Decisions (owner delegation 2026-11-17): whole-entry packing with
file-order output (least change to what agents read). Compatibility: undated
legacy text before the first heading is never dropped for age and ranks lowest
(kept if budget remains); if no whole entry fits the window, the tail of the
newest-confirmed entry is shown, as today, so context is never empty.
Measures: retrieved-memory tokens and stale share (this phase); duplicate rate
and store growth are N/A (nothing is written).
