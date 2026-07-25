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
| B1 | `phase_models` contract -> `task_metadata.phaseModels` -> resolved per phase | TBD | TBD | TBD | Prove the whole hop, not just that the field is accepted |
| B2 | Planning model (PFactory) | TBD | TBD | TBD | TBD |
| B3 | Coding model (AIFactory) | TBD | TBD | TBD | TBD |
| B4 | Testing/verify model (TFactory) | TBD | TBD | TBD | TBD |

---

## C. Backend x service matrix

Four backends across three services: twelve cells. Each needs its own run — a
backend that works in AIFactory tells you nothing about the same backend in
TFactory, because the phases resolve models independently.

`Model resolved` is the value observed in the `workers` map, not the value
requested.

| Cell | Backend | Service | Run link | Model resolved | Verdict | Notes |
|---|---|---|---|---|---|---|
| C1 | Anthropic (Claude) | PFactory | TBD | TBD | TBD | TBD |
| C1 | Anthropic (Claude) | AIFactory | TBD | TBD | TBD | Prior green exists (api-gateway, 2026-06-13, runbook) — re-run under this matrix for a linkable cell |
| C1 | Anthropic (Claude) | TFactory | TBD | TBD | TBD | TBD |
| C2 | Gemini online (gemini-cli / antigravity) | PFactory | TBD | TBD | TBD | TBD |
| C2 | Gemini online (gemini-cli / antigravity) | AIFactory | TBD | TBD | TBD | Needs `phaseModels`, not `BENCH_MODEL`; workspace trust flag required |
| C2 | Gemini online (gemini-cli / antigravity) | TFactory | TBD | TBD | TBD | TBD |
| C3 | Ollama self-hosted (p510, `host.k3d.internal:11434`) | PFactory | TBD | TBD | TBD | TBD |
| C3 | Ollama self-hosted (p510, `host.k3d.internal:11434`) | AIFactory | TBD | TBD | TBD | TBD |
| C3 | Ollama self-hosted (p510, `host.k3d.internal:11434`) | TFactory | TBD | TBD | TBD | TBD |
| C4 | Ollama online (hosted) | PFactory | TBD | TBD | TBD | TBD |
| C4 | Ollama online (hosted) | AIFactory | TBD | TBD | TBD | TBD |
| C4 | Ollama online (hosted) | TFactory | TBD | TBD | TBD | TBD |

Cells filled: 0 / 12.

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
| E1 | Concurrency ceiling (N simultaneous builds, KEDA scale) | TBD | TBD | TBD | Record peak concurrent build Jobs, peak replicas, Pending pods, and whether quality held |
| E2 | Polyglot ladder (multiple languages end to end) | TBD | TBD | TBD | One row per language in the sub-table below |
| E3 | Large / complex single issue (monorepo-scale context) | TBD | TBD | TBD | Record repo size, context strategy, whether the plan decomposed |

E2 polyglot ladder — one row per language, all the way to a verify verdict:

| Language | Scenario | Run link | Build verdict | Verify verdict | Wall-clock | Notes |
|---|---|---|---|---|---|---|
| Python | TBD | TBD | TBD | TBD | TBD | TBD |
| Go | TBD | TBD | TBD | TBD | TBD | TBD |
| Rust | TBD | TBD | TBD | TBD | TBD | TBD |
| TypeScript | TBD | TBD | TBD | TBD | TBD | TBD |
| Terraform / IaC | TBD | TBD | TBD | TBD | TBD | TBD |

---

## F. Benchmarks for documentation

### F1. Standard benchmark set

| Item | Status | Evidence | Notes |
|---|---|---|---|
| `run_benchmark.py` full sweep, all scenarios | TBD | TBD | Scenarios: api-gateway, rust-hello, go-hello, eks-aws, ts-tictactoe, tf-k8s |
| Published numbers in the docs | TBD | TBD | Feeds the fleet blog and TechDocs |

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

| Section | Cells | Filled | Blocked | Blocker |
|---|---|---|---|---|
| A. Handover surfaces | 3 | 0 | TBD | TBD |
| B. Model control per stage | 4 | 0 | TBD | TBD |
| C. Backend x service | 12 | 0 | TBD | TBD |
| D. Swarms | 3 | 0 | TBD | TBD |
| E. Stress and scale | 3 | 0 | TBD | TBD |
| F. Benchmarks | 3 | 0 | TBD | TBD |
| G. Adoption | 2 | 0 | TBD | TBD |

---

*Keep this page and epic #295 in sync: when a cell here graduates from TBD, tick
the matching box on the epic and link the run in both places.*
