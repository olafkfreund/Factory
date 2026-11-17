---
status: approved
issue: 3766
intent: intent/2026-11-17-3766-memory-scratchpad.md
---

# Spec: scratchpad observation layer and dead_end (RFC-0021 Phase 3)

## Design

New `apps/backend/memory/scratchpad.py` (stdlib only, identical logic in the
three repos). Store: `<memory_dir>/scratchpad.json`,
`{kind: {key: {"text", "n", "bad", "ab", "last", "reason"?, "promoted"?}}}`
(`n` observations, `bad` observed while untrusted, `ab` observations tied to an
abandoned approach),
atomic write (temp file + replace, as `retention.confirm`), corrupt or missing
reads as empty, never raises on the write path.

- `KINDS`: the seven signals of RFC section 3.1 (closed set, unknown kinds are
  ignored with a warning). Wired producers this round: `dead_end` and
  `error_fingerprint`. The rest need producers that do not exist and are left as
  accepted-but-unused kinds.
- `normalise(text)`: lowercase, whitespace collapsed, digit runs replaced by `#`,
  truncated to 160 characters. Stored `text` and `reason` are also cut to 160
  characters, so 7 kinds x 100 keys bounds the file. `key = sha256(normalised)[:16]`.
- `observe(memory_dir, kind, text, reason=None, untrusted=False, now=None)`:
  increments `n` (and `bad` when untrusted), sets `last`. `record_dead_end(...)`
  is `observe("dead_end", approach, reason)` plus, for every non-dead_end signal
  with `last` within `ABANDON_WINDOW` (15 minutes) before now, `ab = n`: errors
  seen just before an approach was declared dead belong to that approach. Per kind at most 100
  keys; on overflow the lowest `(n, last)` key is evicted. Counters and sets only.
- `dead_end_context(memory_dir, limit=800, now=None)`: dead_end entries with
  `n - bad >= 1` (a wholly untrusted entry is never recalled as authoritative)
  and not older than `EXPIRE_DAYS` (from `retention.windows()`), ranked by `last` then `n`,
  whole entries packed into `limit`, rendered `- <approach> (why: <reason>; seen
  Nx)`. Empty string when none.

Wiring:
- `agents/tools_pkg/tools/memory.py`: new tool `record_dead_end{approach, reason}`
  (new dead ends per spec dir count against `CAPS[session_type()]`, a repeat only
  increments `n`); `get_session_context` appends `## Dead ends (already tried, do
  not retry)` from `dead_end_context`.
- Producer for `error_fingerprint`: not `RecoveryManager.record_attempt` (its
  callers pass status boilerplate such as "Subtask not marked as completed",
  `agents/session.py`). Instead `memory/hooks.py` `make_failure_hook(memory_dir)`
  returns a `PostToolUseFailure` hook that observes `"<tool>: <error>"`, which is
  a real diagnostic. Registered in `core/client.py` of all three repos where the
  client is built with the spec dir (PF/TF already register a PostToolUseFailure
  group; AIFactory gets one). Never raises. This corrects the intent, which named
  recovery; the intent text is amended in its own commit.
- Pooling needs no change: `scratchpad.json` lives in `memory/`, which the
  existing seed/sync already copies (AIFactory). The store is derived only from
  the spec dir or the project's own `.aifactory/memory` (see tests).
- PFactory/TFactory: no project pool; recall is same-spec (later session of the
  same spec dir). Pooling for them stays a follow-up.
- Prompt mention: the tool list text in each repo's tool registry is unchanged
  except adding the tool name where the memory tools are enumerated.

Measures: store growth per session (bytes of `memory/` after N sessions, with a
recurring failure) reported in the PR; dead-end block size bounded by `limit`.

## Alternatives rejected

- Observing in `record_attempt`: boilerplate, see above.
- A second file `dead_ends.json`: two stores to sync and cap for one concept.
- Storing dead ends in `gotchas.md`: that is the section 1.3 failure (a dead end
  indistinguishable from a working lesson).
- Cross-project dead_end sharing: owner decision 2026-11-16.

## Risks

- `copytree` overwrites same-named files, so two specs building from one seed can
  lose each other's scratchpad entries (same as `gotchas.md` today; no locking
  across processes). A lost observation only delays promotion.
- Hot path cost: one small JSON read-modify-write per failed attempt or dead end.

## Verification

`tests/test_memory_scratchpad.py` in each repo: observe counts and caps;
normalisation; eviction; corrupt store; repeated-failure recall (record in one
session, a new tool instance or a seeded next spec retrieves it); tool cap and
repeat; failure hook registered in each `core/client.py` (source-level check plus hook
call); no-cross-project read (two project dirs, B's dead end
never appears for A; AIFactory through `seed_memory_from_project` and
`sync_memory_to_project`, PF/TF through spec dirs); growth measure. Mutation
checks: remove the recall block from `get_session_context`; seed from a wrong
directory; remove the key-count eviction; remove the failure-hook observe; remove the `n - bad` filter in recall.

Pool overwrite: `copytree` replaces the whole file, so a stale spec snapshot can
also erase `ab`, `bad` and `promoted` marks. Same limit as `gotchas.md` and
`confirmed.json`; documented, not fixed here (a lost mark can re-promote at most
once more, and the novelty gate catches an exact repeat).
