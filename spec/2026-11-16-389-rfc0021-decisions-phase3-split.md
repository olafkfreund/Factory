---
status: approved
issue: 389
intent: intent/2026-11-16-389-rfc0021-decisions-phase3-split.md
---

# Spec: close RFC-0021's open questions and split Phases 3-5

## Design

1. `docs/rfc/0021-earned-memory-and-promotion-gates.md`: update the status line (Phase 2 merged in AIFactory#2063, PFactory#1012, TFactory#1514) and replace the three §8 questions with "Decided 2026-11-16" entries: project scope kept, conditional on no read path crossing projects (RFC-0020 does not guarantee one tenant per project, so this becomes a Phase 3 acceptance test and the question stays open for multi-tenant projects); `dead_end` stays per project; no Graphiti investment, Phase 3 uses the file store. §4 ("the store stays Graphiti/LadybugDB") gets a targeted correction to match; §0-§3 and the rest of §4-§7 are untouched.
2. Issues: Phase 3 (scratchpad and `dead_end` signals), Phase 4 (validation and trust gates, blocked on 3), Phase 5 (retrieval ranking, can run after Phase 2 data exists). Each says: lands in AIFactory, PFactory and TFactory together (a new rule for 3-5; RFC §7 states it for Phase 1 only), no Aperant code, and carries the RFC §6 measures (duplicate-rate before/after, store growth per session, retrieved-memory tokens, mutation check per gate; Phase 3 adds the repeated-failure `dead_end` recall test). Phase 5 is scoped to age-based ranking (recency and `confirmed.json` age); ranking on validation or trust signals waits for Phases 3-4, because the RFC does not define Phase 5 confidence otherwise.
3. Edit the #389 and #1958 bodies (tick boxes, link issues, fix stale line).

## Alternatives rejected

- Start Phase 3 code now: largest change, needs its own spec and three-repo coordination.
- Tenant-scope the pool key now: no demonstrated multi-tenant sharing of one project; adds a migration. Revisit if projects become shared across tenants.

## Risks

None to runtime. A wrong decision is cheap to revisit in the RFC.

## Verification

Docs build or markdown lint as run by the repo CI; `gh issue view` shows the links.
