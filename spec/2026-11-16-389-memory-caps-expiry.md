---
status: approved
issue: 389
intent: intent/2026-11-16-389-memory-caps-expiry.md
---

# Spec: RFC-0021 baseline and Phase 2 (caps, last_confirmed_at, demotion)

## Design

### A. Baseline (docs only)

Add a "Baseline" section to `docs/rfc/0021-earned-memory-and-promotion-gates.md`
(after section 6). It cites AIFactory `docs/dev/memory-baseline-2026-10.md` (live
pool, 33 items, 19 exact and 80 near pairs, 15 boilerplate) and adds a second
measurement made with AIFactory `scripts/memory_dup_baseline.py` (lexical
bag-of-words cosine at 0.88, read-only) on the five local project stores found
under the owner's checkouts (git worktree copies of the same spec excluded):

| Store | Items | Exact pairs | Near pairs | Of which boilerplate items |
|---|---|---|---|---|
| aifactory-test | 8 | 4 | 0 | 8 |
| factory-demo-api-gateway | 8 | 3 | 4 | 7 |
| gnomedoom | 22 | 8 | 6 | 22 |
| hello-python | 16 | 8 | 0 | 16 |
| factory-demo-api-gateway-2 (workspace) | 22 | 11 | 12 | 22 |

Finding: 76 items, 75 are `Implemented subtask:` / `Failed to complete subtask:`
markers and 1 is a QA status line (`QA session 1: All acceptance criteria
validated successfully`), not a durable lesson. Re-running the pair count with the
markers removed gives 0 pairs, so the count of equivalent pairs among durable
lessons is 0 of 0. Every pair found was marker boilerplate. Phase 1 stopped
storing `Implemented subtask:` (a `what_worked` item); `Failed to complete
subtask:` is a `what_failed` item, which Phase 1 leaves ungated, so it is still
stored. Limits:
all stores pre-date Phase 1 and pooling; the metric is lexical so it under-counts
paraphrase; the sample has no `gotchas.md` at all. It is a baseline for "how much
is boilerplate", not for paraphrase rate; the paraphrase rate needs a pooled
project that has run on Phase 1 for several specs, and the RFC says so.

### B. Phase 2, one new module per service: `apps/backend/memory/retention.py`

Identical in AIFactory, PFactory, TFactory except one constant,
`DEFAULT_SESSION_TYPE` (`build`, `planning`, `verification`).

- `CAPS = {"build": 20, "planning": 5, "verification": 8, "insights": 5, "docs": 0}`
  (RFC section 3.3).
- Windows are valid only if `0 < DEMOTE_DAYS < EXPIRE_DAYS`; otherwise both fall
  back to the defaults.
- `session_type(explicit=None)`: explicit argument, else env
  `MEMORY_SESSION_TYPE`, else `DEFAULT_SESSION_TYPE`; an unknown name logs a
  warning and falls back to the default (never silently to 0 or unlimited).
- Sidecar `memory/confirmed.json`: `{sha256(lesson text)[:16]: ISO-8601 UTC}`.
  `confirm(memory_dir, texts)` sets now for each; atomic write (temp + replace);
  a missing or corrupt file reads as empty and is replaced, never raised.
- Windows: `DEMOTE_DAYS = 30`, `EXPIRE_DAYS = 90`, env `MEMORY_DEMOTE_DAYS` /
  `MEMORY_EXPIRE_DAYS` (unparsable or inconsistent values fall back to both defaults).
- `split_gotchas(text)` splits `gotchas.md` on the existing
  `## [YYYY-MM-DD HH:MM]` headings (the same regex `record_gotcha` uses), and
  `gotchas_context(memory_dir, text, limit, now=None)` returns the text to show.

### C. Caps (write side)

1. `save_session_insights(spec_dir, session_num, insights, session_type=None)`:
   after the Phase 1 repeat gate, one shared budget of `CAPS[type]` lessons is
   spent across the gated lists in a fixed order (`patterns_found`,
   `gotchas_encountered`, `patterns_discovered`, `gotchas_discovered`,
   `recommendations`, `what_worked`, `recommendations_for_next_session`); items
   past the budget are dropped and logged at info like the repeat gate. Non-list
   values, `what_failed`, `subtasks_completed`, `files_understood` are not lessons
   and are not capped, as in Phase 1. Cap 0 empties every gated list.
2. `record_gotcha` (the live writer): the tool closure counts gotchas it has
   written and, once the type's cap is reached, refuses a NEW gotcha with a
   plain message. Order inside the tool: repeat check, then `confirm()` of a
   repeat (so a repeat still refreshes after the cap is spent), then the cap
   check, then write.
3. **The cap is per writer, not per session total.** This refines the intent's
   wording: `record_gotcha` has its own counter and `save_session_insights` its
   own per-call budget, so one session can write up to twice the table value
   across the two channels. Sharing one budget needs a session boundary the
   three services do not share. The tool counter's lifetime is the tool
   instance: one agent session on the normal path (`core/client.py` creates a
   fresh set per client), one server process for the standalone MCP server.

### D. last_confirmed_at and demotion (read side)

- `drop_repeats` gains an optional `rejected: list[str] | None` out parameter that
  collects the key of each repeat it drops. `save_session_insights` and
  `record_gotcha` call `confirm()` for every kept and every rejected key, so a
  re-observed lesson gets a fresh `last_confirmed_at`.
- For a `gotchas.md` entry, last_confirmed_at is the later of its heading
  timestamp and the sidecar value for its body (`body.strip()`, the same string
  the gate compares).
- `get_session_context`: classify every entry first. If none is demoted or
  expired (or the file has no headings), output is unchanged from today
  (`content[-1000:]`). Otherwise: fresh entries, tail-limited to 1000 chars as today, then a
  `## Low confidence (not re-observed in N days)` block of demoted entries
  limited to whatever budget the fresh part left; entries older than
  `EXPIRE_DAYS` are not loaded. No file is rewritten or removed.
- Session-insight JSON items get `confirm()` on write. Read-time demotion is not
  applied to them: the Python readers (`load_all_insights`, summary, CLI) do not
  put them in prompts. The AIFactory `prompts/coder.md` does tell the coder to
  `cat` the whole `gotchas.md` and the last 3 session files; the gotchas read is
  changed to "call `get_session_context`" so the filter applies (lines 119-121),
  and the last-3 session read is already bounded by recency and left as is.
  PFactory and TFactory prompts do not read gotchas or session files.

### E. Scope limits, stated

File-backed memory only; the Graphiti write path in `agents/memory_manager.py`
is untouched and bypasses caps when Graphiti is on (known gap). PFactory and
TFactory have no project pool; caps and expiry apply to their per-spec stores.
AIFactory `prompts/followup_planner.md` (lines 64-69) also `cat`s `gotchas.md`
directly; that read is left unfiltered (known gap, follow-up planning only).
The same `coder.md` also tells the agent to write `session_NNN.json` and append
to `gotchas.md` itself with Python; those direct writes bypass the caps (known
gap: the read side still bounds what agents see, because reads go through the
1000-char filtered window). No caller is reclassified; docs and insights types are reachable by argument or
env only.

## Alternatives rejected

- Rewriting `gotchas.md` to delete expired entries: the pool merges by copytree,
  so a rewrite in one worktree is undone or races with another; read-time
  filtering cannot lose data.
- Storing `last_confirmed_at` inside each entry heading: changes the format the
  Phase 1 window parser, escape rule and existing stores depend on.
- Embedding-based confirmation (similar, not identical, counts as seen): no
  embedder in the pod; revisit with the semantic gate.
- Per-field caps: a flat per-session budget matches the RFC table (one number
  per session type).
- A shared package for the three copies: the memory tree is vendored per repo
  today; a package move is out of scope.

## Risks

- Sidecar read-modify-write can lose a refresh when two sessions in one worktree
  write at once; effect is an entry demoted earlier than deserved, not data loss.
- `copytree` pooling is last-writer-wins for `confirmed.json` and `gotchas.md`
  alike (existing behaviour of Phase 0).
- A too-low cap truncates real lessons; values come from the RFC and the env
  override exists for tuning. The cap order prefers discoveries over
  `what_worked`.
- Demotion window starting values are guesses; with almost no accumulated memory
  today the effect is nil until stores grow, which is why demotion never deletes.
- Three vendored copies can drift; the plan ports one tested diff and a test in
  each repo asserts the cap table.

## Verification

- New `tests/test_memory_retention.py` in each repo: cap per type incl. 0, shared
  budget order, env override, unknown type, confirm on repeat refreshes, fresh/
  demoted/expired rendering with injected `now`, legacy store with no sidecar,
  corrupt sidecar, `record_gotcha` cap, unchanged output when nothing is old.
- Mutations (each must turn a test red): cap not applied; confirm not called on
  rejection; expired entries not skipped; demotion not applied.
- Existing `tests/test_memory_novelty.py` stays green.
- Repo CI commands for the touched paths; `codex review --base origin/dev` per repo.
