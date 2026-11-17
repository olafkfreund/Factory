---
status: approved
issue: 3765
spec: spec/2026-11-17-3765-memory-ranking.md
coders:
  1: you     # one function, small tricky logic, I wrote the spec
  2: you     # tests and mutations for step 1
  3: you     # mechanical port to PFactory
  4: you     # mechanical port to TFactory
reviewers:
  - codex    # read-only final review per repo; agy is off by owner decision
---

# Plan: age-based retrieval ranking (RFC-0021 Phase 5)

Self-contained summary of the approved spec `spec/2026-11-17-3765-memory-ranking.md`.
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

Decision: `gotchas_context(memory_dir, text, limit, now)` in `memory/retention.py`
keeps its signature. No `## [` headings: return `text[-limit:]` (legacy). Else
classify each entry as before (`last` = max(heading time, `confirmed.json` value
for the stripped body); age >= expire omitted; age >= demote demoted; else
fresh). Rank fresh by `last` descending (ties: later in file first), undated
preamble last. Pack whole entries greedily into `limit`; if none fits take the
tail of the top-ranked entry. Emit chosen entries in file order. Demoted ones
get the existing `## Low confidence (not re-observed in N days)` block, ranked
and packed into the leftover budget, omitted when no whole entry fits. Output
equals the file text when nothing is old and everything fits.

## Steps

1. AIFactory `memory/retention.py` `gotchas_context` (about lines 99-143):
   rewrite per the decision. Check: `pytest tests/test_memory_retention.py
   tests/test_memory_novelty.py -q`; adapt only assertions that encoded
   tail-slicing (expected: tests asserting a mid-entry cut), keep the rest.
2. AIFactory `tests/test_memory_ranking.py` (new): fixed fixture with injected
   `now` (fresh entries, an old-written entry re-confirmed yesterday via
   `confirmed.json`, demoted and expired entries, an undated preamble), a
   `_legacy_context` copy of the old function, assertions after.tokens <=
   before.tokens (chars/4 estimate) and after.stale_share < before.stale_share;
   re-confirmed old entry kept; oversized sole entry tail; legacy no-heading
   text; no fragment starts a block. Mutations (each turns a test red): rank by
   file position; tail slice instead of whole-entry packing; drop the legacy
   branch; drop the demoted block fragment rule. Check: pytest as above.
3. PFactory: port steps 1-2 (same files, repo formatting). Check: same pytest.
4. TFactory: same. Each repo then: ruff for touched files, `pytest tests -m "not
   slow"` for touched areas (failures also present on untouched `origin/dev`
   are reported, not fixed).

## Tests

`pytest tests/test_memory_ranking.py tests/test_memory_retention.py
tests/test_memory_novelty.py -q` green in each repo; each mutation red.

## Rollback

Revert the PR in each repo. Nothing on disk changes format.
