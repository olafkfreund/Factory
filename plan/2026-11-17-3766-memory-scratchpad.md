---
status: approved
issue: 3766
spec: spec/2026-11-17-3766-memory-scratchpad.md
coders:
  1: you     # new small module, I wrote the spec
  2: you     # tool + context wiring in one file
  3: you     # hook factory and client registration in three repos
  4: you     # tests and mutations
  5: you     # mechanical port to PFactory
  6: you     # mechanical port to TFactory
reviewers:
  - codex    # read-only final review per repo; agy is off by owner decision
---

# Plan: scratchpad observation layer and dead_end (RFC-0021 Phase 3)

Self-contained summary of the approved spec `spec/2026-11-17-3766-memory-scratchpad.md`.
Work happens on branch `feat/3765-memory-phases-3-5` in AIFactory, PFactory and
TFactory (base `dev`; one branch and one PR per repo carries all three issues,
steps run 3765, 3766, 3767) and `docs/389-memory-phases-3-5` in Factory (base
`main`, artifacts and RFC). All code paths are under `apps/backend/`; tests are
in the repo-root `tests/` (run pytest from the repo root: AIFactory
`apps/backend/.venv/bin/pytest`, PFactory/TFactory their own venv or
`python -m pytest`). Traps for every step: AIFactory's ruff and
`standards/ruff.toml` disagree on sorting "as" aliases in parenthesised imports
(use plain names); each repo keeps its own formatting (run its ruff); never
touch the live cluster; standard library only; Graphiti is not extended;
memory stays project-scoped, `dead_end` is never shared across projects; no
Aperant code (AGPL).

Decisions: new `memory/scratchpad.py` (stdlib; atomic write like
`retention.confirm`; corrupt/missing reads as empty; write path never raises).
Store `<memory_dir>/scratchpad.json` `{kind: {key: {text, n, bad, ab, last,
reason?, promoted?}}}`. `KINDS` = file_co_access, repeated_grep,
error_fingerprint, self_correction, dead_end, config_touch, tool_sequence
(unknown ignored with a warning). `normalise`: lowercase, collapse whitespace,
digit runs to `#`, cut to 160; `key` = sha256(normalised)[:16]; stored `text` and
`reason` cut to 160. `observe(memory_dir, kind, text, reason=None,
untrusted=False, now=None)`: n+=1, bad+=1 if untrusted, last=now; max 100 keys
per kind, evict lowest `(n, last)`. `record_dead_end(memory_dir, approach,
reason, untrusted=False, now=None)`: observe dead_end, then for every
non-dead_end signal with `last` within `ABANDON_WINDOW=900` seconds set `ab=n`.
`dead_end_context(memory_dir, limit=800, now=None)`: dead_end entries with
`n - bad >= 1`, age < `retention.windows()` expire, ranked `(last, n)` desc,
whole entries packed, `- <approach> (why: <reason>; seen Nx)`; "" when none.
Tool `record_dead_end{approach, reason}` in `agents/tools_pkg/tools/memory.py`:
a NEW dead end counts against `CAPS[session_type()]` per spec dir (dict keyed by
memory dir, like `gotchas_written`), a repeat only increments; refused message
when over cap. `get_session_context` appends `## Dead ends (already tried, do
not retry)` after gotchas. `memory/hooks.py` `make_failure_hook(memory_dir)` ->
async `PostToolUseFailure` hook observing `error_fingerprint` of
`"<tool_name>: <error>"` (never raises, returns `{}`, ignores `is_interrupt` failures as PF/TF `guard.failure` does), registered in
`core/client.py` where the client has `spec_dir` (`spec_dir / "memory"`):
AIFactory adds a `"PostToolUseFailure"` group; PF/TF add a second matcher next
to `guard.failure`. Pooling unchanged (AIFactory copies `memory/`). Known gaps
(not fixed): `copytree` overwrite and no cross-process locking can lose
observations or marks; PF/TF recall is same-spec only (no project pool).

## Steps

1. AIFactory `memory/scratchpad.py` (new). Check: `python -c "import memory.scratchpad"`
   from `apps/backend`; step 4 tests.
2. AIFactory `agents/tools_pkg/tools/memory.py`: add `record_dead_end` tool and
   the recall block; keep `except Exception` handling style and the 1000-char
   `GOTCHA_CONTEXT_CHARS` constant. Also add the tool name wherever memory tool
   names are enumerated (grep `record_gotcha` in `agents/tools_pkg/`).
3. AIFactory `memory/hooks.py` (new) and `core/client.py`: register the failure
   hook. Check: step 4 tests, `python -c "import core.client"`.
4. AIFactory `tests/test_memory_scratchpad.py` (new): normalise/key; counts and
   per-kind cap eviction; payload truncation; corrupt store; tool records,
   repeat increments, cap refuses; repeated-failure recall (record in one tool
   instance, a fresh instance and, in AIFactory, `sync_memory_to_project` then
   `seed_memory_from_project` into the next spec retrieves it); no-cross-project
   read (two project dirs; project B's dead end never appears for A; assert the
   pool dir is `project/.aifactory/memory`); untrusted-only dead end not recalled;
   `record_dead_end` abandon window; failure hook observes and never raises;
   `core/client.py` source registers `make_failure_hook`; store growth per
   session (bytes after 1, 5, 20 sessions of the same recurring failure stay
   flat after the first). Mutations (each red): drop recall block; seed from the
   wrong directory; drop eviction; drop the `n - bad` filter; drop the hook
   registration. Check: `pytest tests/test_memory_scratchpad.py -q`.
5. PFactory: port steps 1-4; `DEFAULT_SESSION_TYPE` there is `planning` (cap 5).
   Recall test uses the same spec dir across two tool instances; the
   cross-project test asserts nothing outside the spec dir is read. Check: pytest.
6. TFactory: same (`verification`, cap 8). Then per repo: ruff, touched-area tests.

## Tests

`pytest tests/test_memory_scratchpad.py tests/test_memory_retention.py
tests/test_memory_novelty.py -q` in each repo; each mutation red; growth numbers
recorded in the PR.

## Rollback

Revert the PR. `scratchpad.json` is ignored by old code and is not read by anything else.
