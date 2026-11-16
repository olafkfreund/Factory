---
status: draft
issue: 389
spec: spec/2026-11-16-389-memory-caps-expiry.md
coders:
  2: codex   # small tricky logic (window math, atomic sidecar, cap budget)
  3: codex   # same worktree, runs after step 2
  4: codex   # tests for steps 2-3, same worktree
  5: you     # mechanical port of one tested diff, PFactory
  6: you     # mechanical port of one tested diff, TFactory
reviewers:
  - codex    # final read-only review of each repo diff; agy is off by owner decision
---

# Plan: RFC-0021 baseline and Phase 2 (caps, last_confirmed_at, demotion)

Self-contained summary of the approved spec
(`spec/2026-11-16-389-memory-caps-expiry.md`, which refines the intent: caps
are per writer). Work in three service repos (base `dev`, branch
`feat/389-memory-caps-expiry`) and Factory (base `main`, branch
`docs/389-memory-phase2`). All paths are under `apps/backend/` in the service
repos. Phase 1 (`memory/novelty.py`, `memory/sessions.py`,
`agents/tools_pkg/tools/memory.py`) is already on `dev` in all three.

Decisions carried over from the spec:

- New `memory/retention.py`: `CAPS = {"build": 20, "planning": 5,
  "verification": 8, "insights": 5, "docs": 0}`; `DEFAULT_SESSION_TYPE` is
  `build` (AIFactory), `planning` (PFactory), `verification` (TFactory), the only
  per-repo difference; `session_type(explicit=None)` precedence explicit, env
  `MEMORY_SESSION_TYPE`, default, unknown name warns and uses the default.
- Sidecar `memory/confirmed.json` `{sha256(text)[:16]: ISO UTC}`, atomic write,
  corrupt or missing reads as empty. `confirm(memory_dir, texts, now=None)`.
- Windows `DEMOTE_DAYS=30`, `EXPIRE_DAYS=90`, env `MEMORY_DEMOTE_DAYS` /
  `MEMORY_EXPIRE_DAYS`; valid only if `0 < demote < expire`, else both defaults.
- `drop_repeats(candidates, seen, label, rejected=None)`: keys of dropped repeats
  are appended to `rejected` when given. Default behaviour unchanged.
- `save_session_insights(spec_dir, session_num, insights, session_type=None)`:
  after the repeat gate, one shared budget `CAPS[type]` across gated lists in
  order `patterns_found, gotchas_encountered, patterns_discovered,
  gotchas_discovered, recommendations` (inside `discoveries`), then `what_worked`,
  `recommendations_for_next_session`; non-list values, `what_failed`,
  `subtasks_completed`, `files_understood` are never capped. Then `confirm()` for
  every kept and rejected key.
- `record_gotcha`: repeat check, `confirm()` of a repeat, then per-closure cap
  check (refuse a NEW gotcha with a plain message), then write and `confirm()`.
- `get_session_context` gotchas: classify entries (split on the existing
  `## [YYYY-MM-DD HH:MM]` heading regex; last_confirmed = max(heading time,
  sidecar value for `body.strip()`)). If none demoted/expired, output unchanged
  (`content[-1000:]`). Else fresh entries tail-limited to 1000 chars, then a
  `## Low confidence (not re-observed in N days)` block with the leftover budget;
  expired entries omitted. Nothing is rewritten or deleted.
- AIFactory `prompts/coder.md`: the block that `cat`s `gotchas.md` (about lines
  119-121) becomes an instruction to call `get_session_context`.
- Legacy rule: a `gotchas.md` with no `## [` headings keeps today's output.
- Not in scope: Graphiti write path, agent direct-write instructions, the
  unfiltered `cat` of `gotchas.md` in AIFactory `prompts/followup_planner.md`
  (lines 64-69, known gap), PF/TF project pooling, reclassifying callers.
- Paths: service code is under `apps/backend/`; tests live in the repository
  root `tests/` (existing `tests/test_memory_novelty.py`; `tests/conftest.py`
  supplies the backend imports). Run pytest from the repository root with
  `apps/backend/.venv/bin/pytest` (AIFactory has it; PF/TF use the repo's own
  venv or `python -m pytest`, as their CI does).

## Steps

1. Factory `docs/rfc/0021-earned-memory-and-promotion-gates.md`: add section
   "6.1 Baseline (recorded 2026-11-16)" after section 6 with the October live
   figures and the five-store table, the finding and limits from spec section A
   (copy the table and wording); add one line to section 5 Phase 2 pointing at
   the implementation PRs once open. Content to add (approved baseline):
   October live pool (AIFactory `docs/dev/memory-baseline-2026-10.md`, 2026-10-24,
   `aifactory-demo`): 33 items, 19 exact pairs, 80 near pairs (lexical cosine
   0.88), 15 of 33 `Implemented subtask:` boilerplate; `pfactory-friends-demo`
   14 items, 11 exact, 4 near; `AIFactory` 6 items, 3 exact, 0 near. Local
   re-measurement 2026-11-16 with `scripts/memory_dup_baseline.py` (lexical
   bag-of-words cosine, 0.88, read-only) on five local stores, worktree copies
   excluded: aifactory-test 8 items / 4 exact / 0 near / 8 boilerplate;
   factory-demo-api-gateway 8 / 3 / 4 / 7; gnomedoom 22 / 8 / 6 / 22; hello-python
   16 / 8 / 0 / 16; factory-demo-api-gateway-2 (workspace) 22 / 11 / 12 / 22.
   Finding: 76 items, 75 are `Implemented subtask:` or `Failed to complete
   subtask:` markers, 1 is a QA status line (not a durable lesson); with markers
   removed, 0 pairs, so equivalent pairs among durable lessons is 0 of 0. Phase 1
   stopped storing `Implemented subtask:` (a `what_worked` item); `Failed to
   complete subtask:` is `what_failed`, ungated, still stored. Limits: stores
   pre-date Phase 1 and pooling; lexical metric under-counts paraphrase; no
   `gotchas.md` exists in the sample; so it measures boilerplate, not paraphrase
   rate, which needs a pooled project that has run on Phase 1 for several specs.
   Check: `grep -n "6.1 Baseline"` and the doc
   renders (front matter intact). [Factory worktree, me]
2. AIFactory `memory/retention.py` (new) and `memory/novelty.py` (add `rejected`
   param to `drop_repeats`) per the decisions above. Check:
   `python -c "import memory.retention"` from `apps/backend`; existing
   `pytest tests/test_memory_novelty.py` green. [codex]
   Traps: ruff in this repo disagrees with `standards/ruff.toml` on "as" aliases
   in parenthesised imports; use plain names. Standard library only.
3. AIFactory wire it: `memory/sessions.py` `save_session_insights` (cap + confirm,
   new `session_type` kwarg), `agents/tools_pkg/tools/memory.py` `record_gotcha`
   (order above, closure counter) and `get_session_context` (gotchas filter), and
   `prompts/coder.md` gotchas read. Check: step 4 tests, plus the existing
   novelty tests unchanged. [codex]
   Traps: keep `except Exception` and the escape rule in `record_gotcha`; do not
   change the 1000-char window constant `GOTCHA_CONTEXT_CHARS`.
   Existing test to adapt in the same step: `tests/test_memory_novelty.py`
   `test_gotcha_repeat_outside_window_appended` writes 30 fillers through one
   tool instance and would hit the build cap of 20 first. Replace the fillers
   with 8 entries of about 150 characters each (still more than 1000 characters
   in total) and keep every assertion. Grep the file for any other test that
   writes more than 20 gotchas through one instance.
4. AIFactory `tests/test_memory_retention.py` (new): cap per type incl. 0 and
   shared budget order; env override and unknown type; confirm refreshes on a
   repeat (sidecar written); `record_gotcha` cap refuses new but still confirms a
   repeat after the cap is spent; fresh/demoted/expired rendering with injected
   `now`; unchanged output when nothing is old; legacy store without sidecar;
   corrupt sidecar; inconsistent window env falls back; cap table assertion.
   Check (repo root): `apps/backend/.venv/bin/pytest tests/test_memory_retention.py tests/test_memory_novelty.py -q`.
   Then mutations, each must turn a test red: cap loop removed; confirm on
   rejection removed; expired skip removed; demotion block removed. [codex]
5. PFactory: port steps 2-4 from the AIFactory commit (same files minus the
   `coder.md` change, which PFactory does not have), `DEFAULT_SESSION_TYPE =
   "planning"`. Check: the same two pytest files, plus the mutations. [me]
   Traps: PFactory formatting differs (line length); run its ruff config.
6. TFactory: same port, `DEFAULT_SESSION_TYPE = "verification"`. [me]
7. Each repo: rebase on origin/dev (wave 3 is merging), run the repo's own lint
   and tests for touched paths, `codex review --base origin/dev`, fix confirmed
   findings (max 2 rounds), push, open PR with "Refs olafkfreund/Factory#389",
   wait for required checks on the head SHA. Factory PR for artifacts and RFC.

## Tests

- `pytest tests/test_memory_retention.py tests/test_memory_novelty.py -q` in each
  service worktree: all pass; with each mutation applied the new tests fail.
- Repo CI commands for touched paths (ruff check and format on `memory/`,
  `agents/tools_pkg/tools/memory.py`, the new tests).
- Wider `pytest tests/ -m "not slow"`; failures also present on untouched
  `origin/dev` are reported, not fixed.

## Rollback

Revert the PR in each repo. The sidecar `confirmed.json` is ignored by old code;
`gotchas.md` and session files are never rewritten, so no data is lost. Setting
`MEMORY_SESSION_TYPE=build` and a large `MEMORY_DEMOTE_DAYS`/`MEMORY_EXPIRE_DAYS`
(demote < expire) effectively disables demotion without a deploy of code.
