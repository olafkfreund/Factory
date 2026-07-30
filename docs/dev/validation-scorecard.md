---
title: Validation scorecard — results matrix for epic #295
updated: 2026-07-25
---

# Validation scorecard

This is the results side of the validation program tracked in
[Factory#295](https://github.com/olafkfreund/Factory/issues/295). The epic holds
the checklist of what to prove; this page holds the numbers once a run lands.

Everything below ships **empty on purpose**. Cells read `TBD` until a real run
with captured evidence replaces them. Do not fill a cell from memory, from a
cockpit screenshot alone, or from a build that was not driven through the normal
intake — an unbacked green here is worse than an honest `TBD`, because the whole
point of the program is published proof.

Companion docs:
[benchmark-matrix-runbook.md](./benchmark-matrix-runbook.md) (how to run the
harness on the live fleet, how to read `RESULTS.md`, the known false-positive
traps), [secrets-and-tokens.md](./secrets-and-tokens.md) (credential refresh),
[reproducible-test-environments.md](./reproducible-test-environments.md) (the
per-task Nix flake the build and verify legs run in).

---

## How a cell graduates from TBD to filled

A cell is filled when four things exist and are linked. These are exactly the
four the epic's method line names, and they map one-to-one onto artifacts the
fleet already writes — nothing here asks for new instrumentation.

| Evidence | Where it comes from | What goes in the table |
|---|---|---|
| Run link | The GitHub issue that drove the run, or the CFactory WorkItem / spec id | The link itself, in the run-link column |
| Job name | The k8s Job (`kubectl get jobs -n factory`) or the spec directory `workspaces/<project>/.<svc>/specs/<spec-id>/` | Job name or spec id, in run-link or notes |
| Model resolved | `task_metadata.phaseModels` as **resolved per phase**, cross-checked against `token_usage.json`'s `workers` map (`provider`/`model`/`phase`) — not what was requested | The model that actually ran, in the model-resolved column |
| Verdict | AIFactory terminal status and TFactory verdict. `human_review` is a PASS for the build leg (auto-merge off); `triaged` is a terminal verify verdict | pass / fail / partial, in the verdict column |
| Timings, tokens, cost | Stage durations from the harness `results/<slug>.json`; `token_usage.json` for tokens and `costUsd` | The relevant numeric columns |

Rules that keep the scorecard honest:

- **Requested model is not resolved model.** `BENCH_MODEL` alone does not switch
  provider — the phase pins win. A cell claiming Gemini needs the `workers` map
  to show Gemini. See the runbook's provider-matrix section.
- **Zero tokens is a failed build**, whatever the status says. The classic
  symptom is a build that "finishes" in about 30 seconds — usually an expired
  provider credential.
- **A green build with a red plan stage is `partial`, not `pass`.** Record which
  stage failed in notes rather than collapsing it to one word.
- **Verify must have tested the built branch.** If the verify leg checked out
  `main` instead of the build branch, the verdict is void — record `fail
  (hollow verify)` and link the defect.
- Every cell that is not `pass` names its blocker with an issue link. "Didn't
  work" is not a result.

---

## Corrections to the matrix as specified

A code-level triage on 2026-07-30 found that some cells cannot be filled as
written, no matter how the run goes. Correcting the matrix is cheaper than
running four cells to discover they were never measurable.

**PFactory runs no LLM, so it has no backend.** PFactory's plan pipeline
decomposes deterministically. `PlanService.process(..., llm=None)` is what every
production caller passes — the HTTP routes
(`apps/web-server/server/routes/plan_pipeline.py`, `routes/github.py`) and the
agent API all omit it, and only tests supply an `llm`. The routing knobs that
exist (`PFACTORY_PLANNER_PINNED_MODEL`, `PFACTORY_ROUTING_POLICY`) resolve inside
`decompose_with_llm`, which is only reached when an `llm` is present. PFactory's
own usage accumulator says the same thing in its docstring: the block is
"honestly zero".

Consequences, and they are structural rather than cosmetic:

- The four **C-row PFactory cells are N/A**, not TBD. The backend matrix is
  **8 real cells** (AIFactory and TFactory across four backends), not 12.
- **B2** ("control which model runs PLANNING") cannot be proven as worded. What
  can be proven is the adjacent, useful thing: that `PFACTORY_EXECUTION_MODEL`
  decides the `execution.phase_models` PFactory *emits* for AIFactory. That is a
  contract-authoring behaviour, not a choice of the model PFactory thinks with.
- Anything downstream that reads "planning ran on backend X" is reading a
  routing hint, not evidence.

This is not a defect to fix. A deterministic planner is a legitimate design and
arguably the better one. It just means the epic's C column asks a question three
services can't all answer.

---

## Traps that void a cell

Each of these produces a run that completes and looks green while measuring
something other than what the cell claims. They are listed here because every
one of them was found by reading code, not by a run failing.

| Trap | Effect | Where |
|---|---|---|
| `phaseModels` without `isAutoProfile: true` | The resolver ignores the map entirely and the run uses defaults. Nothing warns. | AIFactory `apps/backend/phase_config.py` precedence chain |
| A phase key outside `{spec, planning, coding, qa, qa_fixer}` | Silently dropped by both AIFactory and TFactory whitelists. `testing` is the obvious one to reach for and does nothing. | AIFactory `routes/settings.py`; TFactory `tools/task_control.py` |
| `BENCH_MODEL` alone | Sets the flat model, which loses to the per-phase pins. Observed 2026-06-13 producing an all-Claude build from a Gemini-labelled run. | benchmark-matrix-runbook.md |
| Pinning `ollama:<model>` for the self-hosted box | The agentic Ollama provider is hard-pinned to `localhost:11434` and reads no env, so it never reaches p510. Use `openai-compatible:<model>`. | AIFactory#1099, TFactory#870 |
| Reading a TFactory model from `status.json` | `usage.model` is empty even on a Claude run, so the verify leg has no resolved-model evidence at all. | TFactory#869 |
| Comparing swarms on per-worker wall-clock | `duration_ms` is 0 for every worker; tokens and cost are real, time is not. | AIFactory#1100 |

Two operational constraints in the same spirit:

- **C3 and C4 are mutually exclusive as configured.** Both reach Ollama through
  `OPENAI_COMPATIBLE_BASE_URL`, which is one deployment-level value. It currently
  points at the self-hosted host, so running the hosted cell means changing
  deployment env and rolling the pods between the two runs.
- **The harness's Ollama preset names models the self-hosted host does not
  have.** It defaults to `qwen3-coder:480b` / `gpt-oss:120b`, which are
  ollama.com models. A C3 run must override them (see the measured inventory
  below).

---

## A. Handover surfaces

Status rows. One line per surface; `evidence` is the run or PR that proves it.

| Cell | Surface | Status | Evidence | Notes |
|---|---|---|---|---|
| A1 | Label-driven intake (one labeled issue, hands-free chain) | TBD | TBD | Build leg proven; re-state here only with a full chain incl. verify |
| A2 | Claude Code conductor / trusted-plan handover (parr-run skill) | TBD | TBD | Plan authored outside PFactory, signed, built, verified |
| A3 | Issue-form templates for non-CLI users | TBD | TBD | Needs one run started from the form alone |

---

## B. Model and module control per stage

Status rows. B1 is the control surface; B2-B4 are one stage each.

| Cell | Control | Status | Resolved model observed | Evidence | Notes |
|---|---|---|---|---|---|
| B1 | `phase_models` contract -> `task_metadata.phaseModels` -> resolved per phase | code path traced, **run pending** | TBD | code trace 2026-07-30 | Every hop exists: `execution.phase_models` -> `trusted_plan._EXECUTION_TO_METADATA` -> `task_metadata.json` -> `phase_config._resolve_phase_model` -> provider, recorded in `token_usage.json` `workers`. Requires `isAutoProfile: true` or the map is ignored |
| B2 | Planning model (PFactory) | **not provable as worded** | — | code trace 2026-07-30 | PFactory runs no LLM in production. Re-scope to "`PFACTORY_EXECUTION_MODEL` decides the emitted `execution.phase_models`" — see "Corrections" above |
| B3 | Coding model (AIFactory) | code path traced, **run pending** | `claude-opus-4-8` observed as the **default** | spec `097`, 2026-07-29 | The `workers` map gives per-worker provider/model/phase, which is exactly the evidence this cell needs. A pinned run is still required |
| B4 | Testing/verify model (TFactory) | **blocked** | UNKNOWN | TFactory#869 | Control surface exists but is keyed `coding` — there is no `testing` phase. Unprovable until TFactory records the model it resolved |

Measured default, live pods, 2026-07-30 (both AIFactory and TFactory):
`DEFAULT_PHASE_MODELS = {spec, planning, coding, qa, qa_fixer} -> "opus"`,
resolving to `claude-opus-4-8`. This supersedes the `sonnet` default quoted in
benchmark-matrix-runbook.md, which predates the change.

---

## C. Backend x service matrix

Four backends across three services: twelve cells. Each needs its own run — a
backend that works in AIFactory tells you nothing about the same backend in
TFactory, because the phases resolve models independently.

`Model resolved` is the value observed in the `workers` map, not the value
requested.

| Cell | Backend | Service | Run link | Model resolved | Verdict | Notes |
|---|---|---|---|---|---|---|
| C1 | Anthropic (Claude) | PFactory | — | — | **N/A** | PFactory runs no LLM — see "Corrections" above |
| C1 | Anthropic (Claude) | AIFactory | [aifactory-demo#449](https://github.com/olafkfreund/aifactory-demo/pull/449) | `claude-opus-4-8` (planning + 5 coding workers) | partial | Read from a prior run's artifact, not driven under this matrix; no `phaseModels` set, so it evidences the **default**, not the control surface. Spec `097-inventory-reservation-service-`, 2026-07-29, 1,992,976 tokens / $3.23 |
| C1 | Anthropic (Claude) | TFactory | same run as above | **UNKNOWN** | partial | Verdict `triaged` (terminal), 17 tests generated / 15 committed / 2 rejected, ac_fidelity 11/13. Model resolved is UNKNOWN because TFactory records none (TFactory#869). `git_writer` failed to commit tests back (TFactory#868) |
| C2 | Gemini online (gemini-cli / antigravity) | PFactory | — | — | **N/A** | PFactory runs no LLM |
| C2 | Gemini online (gemini-cli / antigravity) | AIFactory | TBD | TBD | TBD | Provider is `antigravity`; pin via `BENCH_PHASE_MODELS`, never `BENCH_MODEL`. Trust flag already set on this deployment |
| C2 | Gemini online (gemini-cli / antigravity) | TFactory | TBD | TBD | TBD | Expected to fail until TFactory#871 lands (no `GEMINI_CLI_TRUST_WORKSPACE` on the deployment) |
| C3 | Ollama self-hosted (p510, `host.k3d.internal:11434`) | PFactory | — | — | **N/A** | PFactory runs no LLM |
| C3 | Ollama self-hosted (p510, `host.k3d.internal:11434`) | AIFactory | TBD | TBD | TBD | Must be spelled `openai-compatible:<model>`; `ollama:` cannot reach p510 (AIFactory#1099) |
| C3 | Ollama self-hosted (p510, `host.k3d.internal:11434`) | TFactory | TBD | TBD | TBD | Same spelling constraint (TFactory#870); resolved-model evidence blocked on TFactory#869 |
| C4 | Ollama online (hosted) | PFactory | — | — | **N/A** | PFactory runs no LLM |
| C4 | Ollama online (hosted) | AIFactory | TBD | TBD | TBD | No authenticated Ollama client exists; only route is `openai-compatible:` + `OPENAI_COMPATIBLE_BASE_URL=https://ollama.com`. Requires a deployment env change (mutually exclusive with C3) |
| C4 | Ollama online (hosted) | TFactory | TBD | TBD | TBD | As above |

Cells filled: 0 / 8 real cells (2 partial). 4 of the original 12 are N/A.

### Endpoint inventory (measured 2026-07-30, from inside the AIFactory pod)

`GET http://host.k3d.internal:11434/api/tags` returned 200 with five models:
`gemma4:12b`, `gemma4:e4b`, `qwen2.5:7b`, `qwen2.5-coder:14b`,
`nomic-embed-text:latest`. A C3 run picks its coding and general models from
this list — nothing else is served there.

---

## D. Agent swarms

Parallel wave harness, one row per swarm configuration plus the cross-model
comparison. Wall-clock is the full run, intake to terminal verdict. Correctness
is measured against the acceptance criteria, not against "it compiled".

| Cell | Swarm | Workers | Run link | Wall-clock | Correctness (AC met / AC total) | Tokens | Cost | Notes |
|---|---|---|---|---|---|---|---|---|
| D1 | Opus swarm (Anthropic) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| D2 | Gemini swarm | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| D3 | Cross-model swarm (mixed workers) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

Comparison summary (fill once at least two of D1-D3 have landed on the **same**
scenario — different scenarios are not comparable):

| Dimension | Opus | Gemini | Cross-model | Winner | Notes |
|---|---|---|---|---|---|
| Wall-clock | TBD | TBD | TBD | TBD | Same scenario, same worker count |
| Correctness | TBD | TBD | TBD | TBD | AC pass rate plus verify verdict |
| Cost | TBD | TBD | TBD | TBD | Metered backends in USD; subscription and local in tokens plus time |

---

## E. Stress and scale

| Cell | Test | Run link | Result | Ceiling / limit found | Notes |
|---|---|---|---|---|---|
| E1 | Concurrency ceiling (N simultaneous builds, KEDA scale) | partial: [#295 comment](https://github.com/olafkfreund/Factory/issues/295#issuecomment-5006746661) | **no ceiling found** | none reached | Peak 5 concurrent build Jobs, 0 Pending pods, so the resource ceiling is above 5. The "KEDA scale" half was **never measured** — the scaler was misconfigured throughout (PFactory#265). Re-runnable now: see below |
| E2 | Polyglot ladder (multiple languages end to end) | partial | 4 languages built, 0 verified | toolchain provisioning | The 2026-07 batch needed hand-patching to Claude on all 4 (AIFactory#777), so it grades `partial`, not `pass`, per this page's own rule. Rust was never attempted |
| E3 | Large / complex single issue (monorepo-scale context) | TBD | TBD | TBD | Not started |

**E1 is unblocked as of 2026-07-30.** The scaler that voided the earlier attempt
is healthy again — measured: all three `ScaledObject`s report
`ScaledObjectReady=True` with live HPA metrics (`keda-hpa-aifactory 0/1`,
`pfactory 0/2`, `tfactory 0/2`), max replicas 6 / 4 / 4, on a 2-node cluster.
A re-run can therefore measure the KEDA half for the first time.

E2 polyglot ladder — one row per language, all the way to a verify verdict:

| Language | Scenario | Run link | Build verdict | Verify verdict | Wall-clock | Notes |
|---|---|---|---|---|---|---|
| Python | api-gateway | prior: RESULTS.md 2026-06-13..20 | passed | passed | ~53 min | Not driven under this matrix; 2.58M tokens / $1.51 |
| Go | go-hello | TBD | TBD | TBD | TBD | Blocked at the time of RESULTS.md on TFactory#443 (no Go test-gen). **#443 has since closed** — the recorded failure is stale and the cell needs a re-run, not a re-diagnosis |
| Rust | rust-hello | prior: RESULTS.md 2026-06-13..20 | passed | passed | ~59 min | Not driven under this matrix; 7.60M tokens / $5.05. Absent from the 2026-07 batch entirely |
| TypeScript | aws-3tier | prior: RESULTS.md 2026-06-13..20 | passed | **failed** | ~77 min build | Verify rejected the build — a real quality signal, not a pipeline error |
| Terraform / IaC | eks-aws, tf-k8s | TBD | TBD | TBD | TBD | `validate-only`; never run |

The three prior rows come from `aifactory-demo/benchmarks/results/RESULTS.md`.
They are recorded here as **prior evidence with links**, not as filled cells:
they predate this matrix, and the Go row in that document is now known stale.

---

## F. Benchmarks for documentation

### F1. Standard benchmark set

| Item | Status | Evidence | Notes |
|---|---|---|---|
| `run_benchmark.py` full sweep, all scenarios | TBD | TBD | Seven scenarios exist in `benchmarks/scenarios.yaml`: api-gateway, rust-hello, go-hello, aws-3tier, eks-aws, ts-tictactoe, tf-k8s. Four have ever been run; three (eks-aws, ts-tictactoe, tf-k8s) never have |
| Published numbers in the docs | TBD | TBD | Feeds the fleet blog and TechDocs |

The harness lives in `aifactory-demo/scripts/run_benchmark.py`. The Factory-side
roll-up tool is `scripts/benchmarks/report.py` in this repo, which reads the
harness sidecars and emits the F2 and F3 tables — it degrades unknown fields to
`UNKNOWN` rather than guessing, which is what makes it safe to publish from.

### F2. Per-backend latency, cost, quality

One row per backend. Numbers are medians across the scenario set, not a single
lucky run; put the sample size in `runs`.

| Backend | Runs | Median plan (min) | Median build (min) | Median verify (min) | Median wall-clock (min) | Median tokens | Median cost | Verify pass rate | Notes |
|---|---|---|---|---|---|---|---|---|---|
| Anthropic (Claude) | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | Baseline |
| Gemini online | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Ollama self-hosted (p510) | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | Cost column is tokens plus time, not USD |
| Ollama online | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

### F3. Parallel vs serial wall-clock

| Scenario | Mode | Workers | Run link | Wall-clock (min) | Speedup vs serial | Tokens | Cost | Notes |
|---|---|---|---|---|---|---|---|---|
| Baseline (wave harness) | Parallel | TBD | TBD | 21.4 | 1.64x | TBD | TBD | Figure quoted in epic #295; needs a run link, job names, and worker count before it can be published |
| Baseline (wave harness) | Serial | 1 | TBD | 35.0 | 1.00x | TBD | TBD | Same as above — the comparison pair for the 21.4 min row |
| TBD | Parallel | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| TBD | Serial | 1 | TBD | TBD | 1.00x | TBD | TBD | TBD |

The two baseline rows are seeded with the numbers the epic already records so the
shape of the table is unambiguous. They are **not** published-ready: until the
run links and job names are attached, treat them as a claim to re-verify, not as
evidence.

---

## G. Adoption

| Cell | Item | Status | Count | Evidence | Notes |
|---|---|---|---|---|---|
| G1 | Real fleet issues routed through the factory | TBD | TBD | TBD | Issues the fleet needed anyway, not synthetic test issues |
| G2 | Factory-authored PRs merged after CI plus verify | TBD | TBD | TBD | Merged, not just opened; the target repo's own CI must be green |

---

## Rolling summary

Update this block whenever a section moves. It is the one place to look for
"where is the validation program".

Last triage: 2026-07-30 (code + live cluster, no new runs commissioned).

| Section | Cells | Filled | Blocked | Blocker |
|---|---|---|---|---|
| A. Handover surfaces | 3 | 0 | 0 | Needs one run each restated under this matrix |
| B. Model control per stage | 4 | 0 | 2 | B2 not provable as worded (no PFactory LLM); B4 blocked on TFactory#869 |
| C. Backend x service | 8 (was 12) | 0 (2 partial) | 4 | 4 PFactory cells are N/A. C2/TFactory on TFactory#871; C3 on AIFactory#1099 + TFactory#870; C4 needs a deployment env change |
| D. Swarms | 3 | 0 | 3 | Per-worker wall-clock is 0 (AIFactory#1100), so D3's comparison has no time axis |
| E. Stress and scale | 3 | 0 (2 partial) | 0 | E1 unblocked and re-runnable; E2 needs a clean run; E3 not started |
| F. Benchmarks | 3 | 0 | 3 | Rollup — waits on C, D, E |
| G. Adoption | 2 | 0 | 0 | Needs a count with links, not a status |

Every remaining cell is now an **execution** cost, not a discovery cost: the
blockers are named, the traps are written down, and the harness can pin any
backend per phase (aifactory-demo#450).

---

*Keep this page and epic #295 in sync: when a cell here graduates from TBD, tick
the matching box on the epic and link the run in both places.*
