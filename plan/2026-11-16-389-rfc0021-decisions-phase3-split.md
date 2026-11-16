---
status: draft
issue: 389
spec: spec/2026-11-16-389-rfc0021-decisions-phase3-split.md
coders:
  1: you   # prose edit, no handoff
reviewers:
  - codex
---

# Plan: close RFC-0021's open questions and split Phases 3-5

Decisions from the spec: project scope kept, conditional on no cross-project read path (Phase 3 acceptance test); `dead_end` per project only; no Graphiti investment (targeted §4 correction); Phases 3-5 become issues carrying the §6 measures and the all-three-or-none rule; Phase 5 first, scoped to age-based ranking.

## Steps

1. `docs/rfc/0021-earned-memory-and-promotion-gates.md` line 10 (status), §4 (~218, store sentence) and §8 (~317-326): apply the decisions above → verify by `git diff` and the repo's markdown/docs check from `.github/workflows`.
   Traps: edit only the status line, §4's store sentence and §8; keep the Updated date.
2. Issues via `gh` (not in the diff): create Phase 3/4/5 issues (each lists the §6 measures that apply), edit #389 and #1958 bodies, comment decisions starting "Decision (owner delegation 2026-11-16):".

## Tests

Docs CI check on the PR (look up the exact job in `.github/workflows`).

## Rollback

Revert the doc commit; issues can be closed or edited.
