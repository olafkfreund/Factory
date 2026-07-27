---
layout: default
title: "RFC-0021: Earned Memory and Promotion Gates — a memory has to survive something before it is kept"
permalink: /rfc/earned-memory-and-promotion-gates/
---

# RFC-0021 — Earned Memory and Promotion Gates

> **Status:** Proposed — **§1 CORRECTED 2026-07-27, see §0** · **Created:** 2026-07-27 · **Owner:** AIFactory (memory subsystem; PFactory and TFactory vendor the same tree) ·
> **Extends:**
> [RFC-0010](./0010-code-aware-planning-and-behavioral-equivalence.md) (code-aware planning — memory is what makes the second pass over a codebase cheaper than the first),
> [RFC-0012](./0012-external-knowledge-grounding.md) (external grounding — this is the *internal* counterpart: what the fleet learned by doing, rather than what it read),
> [RFC-0014](./0014-cost-aware-model-and-runtime-routing.md) (cost routing — retrieval quality is a token-cost lever) ·
> **Affects:** `apps/backend/memory/` and `apps/backend/analysis/insight_extractor.py` in AIFactory, PFactory and TFactory. No task-contract change. No new external dependency in Phase 1.

## 0. Correction — the premise below was wrong

**Added 2026-07-27, the same day this RFC merged.** Going to record the baseline
§6 demands, I found there was nothing to measure, and why turned out to invert
the argument. AIFactory#1030 carries the defect; this section stays so the record
shows what was claimed and what was true.

§1 asserts *"the problem is not that nothing is remembered — it is that everything
is."* **That is backwards. Almost nothing is remembered.**

On the live cluster:

- **8** session-insight files exist, and **all 8 sit inside a per-task worktree**
  (`worktrees/tasks/035-…/.aifactory/specs/034-…/memory/session_insights/`).
  Memory for spec 034 is written inside the worktree for task 035.
- `agents/utils.py sync_plan_to_source()` copies **`implementation_plan.json`
  only**. `memory/` is never synced back, so it dies with the worktree and the
  next task starts blind.
- There are **zero `gotchas.md` or `patterns.md` files anywhere**.
- There are **no `GRAPHITI_*` variables in the running pod**, so the
  knowledge-graph path is disabled in production.

**§1.1's example is dead code.** The exact-string dedup in `memory/patterns.py`
is real, and `append_gotcha` appears to have 14 callers per repo — but every one
is a package re-export or a **usage example inside `memory/main.py`'s module
docstring**. There are no real call sites. A grep count was taken as a usage
count.

So of three memory mechanisms, one is dead code, one is disabled, and the live
one writes somewhere that is thrown away.

**What survives.** The promotion-gate design in §2–§3 is still the right shape,
and §1.4's reasoning about token cost still applies — *once memory accumulates*.
It does not today. A novelty filter, a cap and an expiry policy all presuppose a
store that grows; ours does not. So every phase in §5 now sits behind a new
Phase 0: **make memory survive a task** (AIFactory#1030).

**What this vindicates.** §6 insists the acceptance criteria are measurements
rather than assertions. That is what caught this. Had the novelty gate been built
on the strength of §1, it would have passed its tests, changed nothing, and
hidden a correctness bug behind a plausible improvement.

## 1. Motivation (as originally written — see §0)

The fleet already has a memory subsystem, and it already extracts insights with
an LLM after every session (`analysis/insight_extractor.py` → Graphiti /
LadybugDB, plus the flat `patterns.py` gotcha and pattern files). The problem is
not that nothing is remembered. **The problem is that everything is.**

Three properties of the current design compound:

### 1.1 Deduplication is exact string equality

`memory/patterns.py` decides novelty like this:

```python
if gotcha_stripped and gotcha_stripped not in existing_gotchas:
    # append
```

So these are two separate memories, permanently:

```
- API rate limits: 100 req/min per IP
- API rate limit is 100 requests per minute per IP
```

An LLM writes these strings. LLMs do not emit byte-identical prose across runs,
so in practice **the dedup check almost never fires** for the case it exists to
catch. The file grows by roughly one entry per session per insight, forever.

### 1.2 There is no cap, and no expiry

Nothing in `memory/` bounds how many gotchas or patterns a project accumulates,
and nothing removes one that stopped being true. A gotcha about a rate limit
that was raised last quarter has exactly the same standing as one discovered an
hour ago.

### 1.3 Nothing has to be *true* to be remembered

The extractor runs on a completed session and writes what it found. A session
that tried four approaches and shipped the fifth contributes insights from all
five — the four dead ends are indistinguishable in the store from the one that
worked. So the memory that gets retrieved next time may be a confident
description of an approach the fleet already proved does not work.

### 1.4 What this costs

Memory is loaded into agent context. An unbounded, duplicate-heavy,
partly-wrong store is not merely untidy — it is **a growing token bill that
buys progressively worse advice**, and it degrades exactly as a project matures
and its memory grows. That inverts the intended benefit: the codebase the fleet
has worked on most is the one whose memory helps least.

This also blunts RFC-0010. Code-aware planning is supposed to make brownfield
work cheaper on the second pass. It cannot, if the second pass retrieves ten
near-identical gotchas and one obsolete one.

## 2. The idea: a memory has to be earned

Today the pipeline is:

```
session ends → LLM extracts insights → write them all
```

Proposed:

```
session runs  → observe signals into a per-session scratchpad
session ends  → promotion gates decide which signals deserve to become memory
              → LLM synthesises only the survivors
              → write, under a cap
```

The change is **where the LLM sits**. Today it is the *first* step and decides
what is interesting from a transcript. Under this proposal it is the *last*
step and only writes up what cheap, deterministic filters already judged worth
keeping. That is both better and cheaper: fewer LLM calls, on better-chosen
input.

### 2.1 Prior art, and why this is not a port

The shape of this design — scratchpad, promotion filters, per-session-type caps
— is convergent with the memory architecture published by
[Aperant](https://github.com/AndyMik90/Aperant) (AGPL-3.0), which is worth
reading and worth crediting.

**No Aperant code is used, and none may be.** Aperant is AGPL-3.0; PFactory and
TFactory are MIT, and strong copyleft cannot be relicensed as MIT. This RFC
describes an independent design for our own Python/Graphiti subsystem, motivated
by defects in *our* code (§1.1–§1.3) that exist regardless of what anyone else
built. Where a threshold below matches theirs it is because the underlying
statistics are the same, not because a file was copied. Implementation must be
written from this document and our own store, not from theirs.

## 3. Design

### 3.1 Signals, not transcripts

During a session, record cheap structured observations rather than waiting to
re-read a transcript:

| Signal | Why it predicts a useful memory |
|---|---|
| `file_co_access` | Files repeatedly opened together are coupled in a way the tree does not show |
| `repeated_grep` | The same search re-run across sessions marks something hard to locate |
| `error_fingerprint` | A normalised error seen more than once is a real trap, not bad luck |
| `self_correction` | The agent undoing its own edit marks a wrong assumption worth naming |
| `dead_end` | An approach explicitly abandoned — the most valuable and least recorded thing today |
| `config_touch` | Config edited to make something work is invisible in the diff's intent |
| `tool_sequence` | A recurring short sequence is a workflow worth naming |

`dead_end` deserves emphasis: §1.3's failure mode is that dead ends are
currently recorded *as if they worked*. Recording them **as dead ends** turns
the fleet's single worst memory category into one of its most useful.

### 3.2 Promotion gates

Applied in order, cheapest first, so the expensive step runs on the fewest
candidates:

1. **Validation.** Discard signals from approaches the session abandoned —
   *unless* they are promoted as `dead_end`. Fixes §1.3.
2. **Frequency.** A signal class must recur (across a session or across
   sessions) before it counts. One occurrence is an anecdote.
3. **Novelty — semantic, not literal.** Embed the candidate and discard it if
   cosine similarity to an existing memory exceeds a threshold (start at
   **0.88**, tune against §6). This is the direct fix for §1.1, and the single
   highest-value gate.
4. **Trust.** Signals produced after an external tool returned untrusted content
   are marked lower-trust, so a memory cannot be laundered into the store by
   something the agent merely *read*. This matters more here than in a desktop
   tool: the fleet ingests issue bodies and web content, and RFC-0012 grounding
   pulls in external documents.
5. **Score and cap.** Rank survivors; keep the top N for the session type.
6. **Synthesise.** One LLM call turns the survivors into 1–3 sentence memories.
7. **Write.** One transaction.

### 3.3 Caps by session type

Not every session earns the same amount. Indicative starting values:

| Session type | Gate | Cap |
|---|---|---|
| Build (full PARR pipeline) | verification passes | 20 |
| Planning (PFactory) | plan approved | 5 |
| Verification (TFactory) | verdict reached | 8 |
| Insights / analysis | session end | 5 |
| Changelog / docs-only | — | 0 |

A cap of 0 is a real answer. A docs-only session has nothing durable to teach,
and letting it write anything is how a store fills with noise.

### 3.4 Expiry

Every memory carries `last_confirmed_at`. A memory not re-observed within a
configurable window is demoted before it is deleted — surfaced as
low-confidence rather than silently dropped, because a memory that stopped
being re-observed is usually stale but occasionally just rare.

## 4. What does not change

- The store stays Graphiti / LadybugDB. This RFC changes **what is written**, not
  where.
- No task-contract change.
- `insight_extractor.py` keeps its role, moved to the end of the pipeline.
- Phase 1 adds no new runtime dependency: the fleet already configures an
  embedder for Graphiti (`memory/graphiti_helpers.py` requires one), so the
  novelty gate can reuse it.

## 5. Phases

- **Phase 1 — the novelty gate.** Replace exact-string dedup with semantic
  similarity in `patterns.py`. Standalone, no observation layer, and on its own
  it fixes §1.1, the defect doing the most damage today.
- **Phase 2 — caps and expiry.** Bound the store; add `last_confirmed_at` and
  demotion.
- **Phase 3 — the scratchpad and signals.** Observation layer; `dead_end`
  recording. The largest change, and the one worth doing last, once the store
  is no longer drowning.
- **Phase 4 — validation and trust gates.** Requires Phase 3's signals.
- **Phase 5 — retrieval quality.** Rank by confidence and recency at read time.

Phase 1 is deliberately shippable alone. If this RFC stalls after it, the fleet
is still meaningfully better off.

## 6. How we will know it worked

A memory system is easy to declare improved and hard to prove improved, so the
acceptance criteria are measurements, not assertions:

- **Duplicate rate.** Sample an existing project's gotcha file and count
  semantically equivalent pairs. Phase 1 must cut this materially; the current
  figure is the baseline and should be recorded before any change lands.
- **Store growth per session.** Should fall and then flatten. Today it is
  roughly linear and unbounded.
- **Retrieved-memory token count** per build. Should fall.
- **Dead-end recall.** After Phase 3, a session hitting a previously-abandoned
  approach should retrieve the `dead_end` memory. This is testable directly:
  run a spec twice, break it the same way, assert the second run retrieves it.

Each gate must be verified by mutation, per the fleet's standard: disable a gate
and the test that covers it must go red. A promotion filter nobody has watched
reject something is a filter nobody knows works.

## 7. Risks

- **A too-aggressive novelty gate suppresses a real distinction.** "Rate limit
  is 100/min on the read path" and "…on the write path" are similar strings and
  different facts. Mitigation: tune the threshold against §6's sample rather
  than picking one by feel, and keep the discarded candidate in the scratchpad
  log for a window so a bad threshold is visible instead of silent.
- **Signal observation adds per-session overhead.** Mitigation: counters and
  sets only, no LLM in the hot path; the LLM call count strictly decreases.
- **Embedding cost on every candidate.** Mitigation: candidates reaching the
  novelty gate are already frequency-filtered, so this is a small batch, and it
  replaces a larger LLM synthesis call.
- **Vendoring.** The memory tree exists in three service repos. A change here
  needs the same discipline as `shared/factory-github/`, or the three drift.
  Phase 1 should land in all three or none.

## 8. Open questions

- Should memories be **tenant-scoped**? RFC-0020 made git configuration
  tenant-scoped; memory is currently project-scoped. A multi-tenant deployment
  sharing one project's memories across tenants is a leak, and this RFC does not
  resolve it.
- Is `dead_end` safe to share across projects, or is an approach that failed in
  one codebase actively misleading in another?
- Does the knowledge-graph structure earn its keep, given Aperant moved off
  Graphiti for their rebuild? Worth a spike before Phase 3, not before Phase 1.
