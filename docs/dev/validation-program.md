---
layout: default
title: Factory validation program
updated: 2026-07-25
---

# Factory validation program

The index for epic [#295](https://github.com/olafkfreund/Factory/issues/295):
prove the factory on every axis, capture reusable benchmarks for the docs, and
graduate to using the factory for its own future work.

Each matrix cell is a tracking issue with a run behind it. This page is the map:
what the cells are, how to run one, what evidence a run must leave behind, and
which issue owns each cell.

Companion docs: [benchmark-matrix-runbook.md](./benchmark-matrix-runbook.md)
(how to drive the harness on the live fleet),
[secrets-and-tokens.md](./secrets-and-tokens.md) (credential refresh),
[creating-issues-and-workitems.md](../creating-issues-and-workitems.md) (label
intake and difficulty tiers).

---

## The A-G structure

- **A. Handover surfaces** — the ways work enters the factory.
- **B. Model / module control per stage** — proving the contract's
  `phase_models` actually decides which model runs planning, coding, testing.
- **C. Model backend matrix** — 4 backends across 3 services (12 cells),
  tracked as one issue per backend row.
- **D. Agent swarms** — the parallel wave harness, per backend and compared.
- **E. Stress and scale** — concurrency ceiling, polyglot ladder, large context.
- **F. Benchmarks for documentation** — the published numbers and tables.
- **G. Adoption** — real fleet work routed through the factory.

A1 (label-driven intake) and A3 (issue-form templates) are already proven and
are not re-tracked. A2 (Claude Code conductor / trusted-plan handover) is the
`parr-run` conductor method described below, and is exercised by the cells that
use it rather than by a cell of its own.

---

## How to run one cell

Pick the method that matches the cell. Both leave the same evidence.

### Method 1 — label intake (hands-free)

File one issue on a watched repo, apply a difficulty label
(`factory:low`, `factory:medium`, `factory:hard`, or `factory:parallel` for the
wave harness), and the chain runs itself: classify, plan (PFactory for `hard`),
build (AIFactory), auto-PR, verify (TFactory). Normative behaviour per tier is
in [RFC-0011](../rfc/0011-label-driven-intake-and-difficulty-tiers.md); the
practical guide is
[creating-issues-and-workitems.md](../creating-issues-and-workitems.md).

Use this for cells that are about the product path: C rows, D swarms, E scale,
G adoption.

### Method 2 — parr-run conductor (trusted plan)

Claude Code authors the plan, PFactory reviews and signs it, AIFactory builds it
on the trusted-plan fast path, TFactory verifies, with progress watched from the
CFactory cockpit. Use this when the cell needs a specific plan shape, a specific
model per phase, or a controlled comparison. This is the method the B cells
depend on, since the contract is authored directly.

### Method 3 — benchmark harness

`run_benchmark.py` from `aifactory-demo`, run **inside the AIFactory pod** (the
agent sandbox has no pod-network egress, so `kubectl port-forward` fails). Full
procedure, including how to read `human_review` as success and the known
observability gaps, is in
[benchmark-matrix-runbook.md](./benchmark-matrix-runbook.md). Use this for the F
cells and for any cell that wants comparable numbers rather than a single
verdict.

---

## Evidence format

Every cell run records the following on its tracking issue, as a comment, before
the box is ticked. Keep it copy-pasteable, plain text, no screenshots for the
numbers.

| Field | What to record |
|---|---|
| Cell | The cell id, for example `C2 / AIFactory`. |
| Method | Label intake, parr-run, or benchmark harness. |
| Job | Spec id or task id, plus the k8s job or pod name that ran it. |
| Repo / issue | The source issue or repo the work came from. |
| Model resolved | The model actually used per phase (planning / coding / testing), as resolved at run time — not the requested value. |
| Verdict | `pass`, `fail`, or `human_review` (see the runbook: `human_review` is a success state). |
| Timings | Wall-clock per phase and total. |
| Tokens / cost | Tokens per phase; cost only for metered backends (api/cloud). Subscription and local backends record tokens and time only. |
| Notes | What broke, what was worked around, what should become a follow-up issue. |

If a run exposes a defect, file a separate issue for it and link it from the cell
issue. Do not fold product bugs into the validation cell.

---

## Cell to issue map

| Cell | What it proves | Issue |
|---|---|---|
| A1 | Label-driven intake, one issue to hands-free chain | proven (see #295) |
| A2 | Claude Code conductor / trusted-plan handover | covered by the `parr-run` method above |
| A3 | Issue-form templates for non-CLI users | shipped (see #295) |
| B1 | `phase_models` end to end: contract to `task_metadata.phaseModels` to resolved model | [#335](https://github.com/olafkfreund/Factory/issues/335) |
| B2 | Control the PLANNING model (PFactory) | [#336](https://github.com/olafkfreund/Factory/issues/336) |
| B3 | Control the CODING model (AIFactory) | [#337](https://github.com/olafkfreund/Factory/issues/337) |
| B4 | Control the TESTING/verify model (TFactory) | [#338](https://github.com/olafkfreund/Factory/issues/338) |
| C1 | Anthropic (Claude) backend, 3 services | [#339](https://github.com/olafkfreund/Factory/issues/339) |
| C2 | Gemini online backend, 3 services | [#340](https://github.com/olafkfreund/Factory/issues/340) |
| C3 | Ollama self-hosted (p510) backend, 3 services | [#341](https://github.com/olafkfreund/Factory/issues/341) |
| C4 | Ollama online (hosted) backend, 3 services | [#342](https://github.com/olafkfreund/Factory/issues/342) |
| D1 | Opus swarm, multi-worker wave on Anthropic | [#343](https://github.com/olafkfreund/Factory/issues/343) |
| D2 | Gemini swarm, same wave shape | [#344](https://github.com/olafkfreund/Factory/issues/344) |
| D3 | Cross-model swarm comparison (wall-clock, correctness, cost) | [#345](https://github.com/olafkfreund/Factory/issues/345) |
| E1 | Concurrency ceiling, N simultaneous builds, KEDA scale | [#346](https://github.com/olafkfreund/Factory/issues/346) |
| E2 | Polyglot ladder end to end | [#347](https://github.com/olafkfreund/Factory/issues/347) |
| E3 | Large/complex single issue, monorepo-scale context | [#348](https://github.com/olafkfreund/Factory/issues/348) |
| F1-F3 | Published benchmark set and the per-backend and parallel-vs-serial tables | [#349](https://github.com/olafkfreund/Factory/issues/349) |
| G1-G2 | Real fleet issues routed through the factory, and factory-authored PRs merged | [#350](https://github.com/olafkfreund/Factory/issues/350) |

The C row issues each cover three cells (PFactory, AIFactory, TFactory); record
one evidence block per service on the issue so the 12-cell matrix stays legible.

---

## Order of work

1. **B first.** Everything below it depends on being able to pin a model per
   phase; without B the C and D results are not attributable.
2. **C rows next**, Anthropic baseline before the alternatives, so each later row
   has something to be compared against.
3. **D swarms** once a backend has a green C row, since a swarm on a broken
   backend proves nothing.
4. **E scale** after D, because the wave harness is the thing being scaled.
5. **F** is a rollup: it publishes what C, D and E produced.
6. **G** runs continuously alongside, not at the end.

Results feed the fleet blog and TechDocs.
