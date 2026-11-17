---
status: approved
issue: 3765
intent: intent/2026-11-17-3765-memory-ranking.md
---

# Spec: age-based retrieval ranking (RFC-0021 Phase 5)

## Design

Change only `gotchas_context(memory_dir, text, limit, now)` in
`apps/backend/memory/retention.py` (AIFactory, PFactory, TFactory; same
behaviour, each repo's own formatting). Signature and callers unchanged.

1. Split with `split_gotchas` (unchanged). No headings: return `text[-limit:]`
   as today (legacy).
2. For each entry compute `last` = max(heading time, `confirmed.json` value for
   the body), as today. Age >= `expire_days`: omitted. Age >= `demote_days`:
   demoted. Otherwise fresh.
3. Rank fresh entries by `last` descending (ties: later in the file first). The
   undated preamble (text before the first heading) is a candidate ranked last.
4. Pack whole entries into `limit` in rank order, skipping an entry that does not
   fit and trying the next (greedy). If nothing fits, take the tail of the
   top-ranked entry, so the result is never empty when fresh text exists.
5. Emit the chosen entries in file order. If nothing is demoted or expired and
   everything was chosen, the output equals the file text (as today when it fits).
6. Demoted entries go under the existing `## Low confidence (not re-observed in N
   days)` heading, ranked and packed the same way into the leftover budget; the
   block is omitted when no whole demoted entry fits (no fragments).

Measure (fixed fixture in the test, injected `now`): retrieved tokens (an estimate,
characters / 4; the real tokenizer is not a dependency) before (the Phase 2 function, copied into the test as `_legacy_context`)
and after; stale share = loaded entries with `last` older than the demote window
over loaded entries (fragments count as one loaded entry). Asserted:
after.tokens <= before.tokens and after.stale_share < before.stale_share.

## Alternatives rejected

- Ranking by validation or trust signals: Phases 3-4, per the issue.
- Re-ordering output by rank: changes what agents read for no gain; selection is
  what saves tokens.
- Scoring with decay weights: more knobs, same selection on this data.

## Risks

- A whole-entry rule can exclude a long newest entry: covered by step 4.
- Output order differs from rank order; accepted (file order is chronological
  by write time).
- `confirmed.json` still unlocked across processes (Phase 2 gap); a lost stamp
  only demotes earlier.

## Verification

`pytest tests/test_memory_ranking.py tests/test_memory_retention.py` in each
repo. Mutation checks, each must turn a test red: rank by file position instead
of `last`; allow fragments (tail slice); drop whole-entry packing; omit the
legacy no-heading branch. Measures are reported in each PR.
