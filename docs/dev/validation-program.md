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

## Runbooks for the remaining cells

One block per cell that still needs a live run. Each names the exact command, the
environment it needs, a **budget estimate**, and what counts as a pass.

The cost and duration figures below are **estimates for planning**, extrapolated
from runs already recorded in
`aifactory-demo/benchmarks/results/RESULTS.md` (api-gateway 2.58M tokens /
$1.51 / ~53 min; rust-hello 7.60M / $5.05 / ~59 min; aws-3tier 9.47M / $7.35 /
~77 min build) and from spec `097` on 2026-07-29 (build 1.99M / $3.23; verify
$7.76). They are not measurements of the runs described here, which have not
happened. Treat them as a budget, not a result.

Common preamble for every harness run — the sandbox has no pod-network egress,
so the harness runs inside the AIFactory pod:

```bash
kubectl --context factory exec -n factory deploy/aifactory -c aifactory -- sh -c '
cd /home/nonroot/.aifactory/workspaces/olafkfreund-aifactory-demo
export AIFACTORY_API=http://127.0.0.1:3101
export PFACTORY_API=http://pfactory.factory.svc.cluster.local:3114
export TFACTORY_API=http://tfactory.factory.svc.cluster.local:3103
export AIFACTORY_TOKEN=$APP_API_TOKEN PFACTORY_TOKEN=$APP_API_TOKEN TFACTORY_TOKEN=$APP_API_TOKEN
<PER-CELL ENV HERE>
setsid nohup python3 -u scripts/run_benchmark.py --scenario api-gateway \
  > /tmp/bench.log 2>&1 < /dev/null & echo pid=$!'
```

**Before recording any result**, confirm the cluster is running the code you
think it is. ArgoCD reports `Synced/Healthy` while serving a stale image
(Factory#425), so check the digest rather than the sync status:

```bash
kubectl --context factory get deploy -n factory aifactory pfactory tfactory cfactory \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.image}{" "}{end}{"\n"}{end}'
gh api repos/olafkfreund/AIFactory/commits/main --jq '.sha[0:7]'   # and each sibling
```

A cell filled from a run against stale code is an unbacked green in the one
document whose whole premise is published proof.

### B1 / B3 — pin three phases to three distinct models

```
BENCH_PHASE_MODELS='{"planning":"opus","coding":"sonnet","qa":"haiku"}'
```
Needs aifactory-demo#450 merged (the harness rejects unknown phase keys and sets
`isAutoProfile`, without which the map is ignored). Scenario `api-gateway`.

- **Budget:** ~50-60 min, roughly $2-4.
- **Pass:** `token_usage.json`'s `workers` map shows three *different* resolved
  models against the matching `phase` values. A single model across all workers
  is a fail even if the build is green — it means the pin was ignored.

### B4 — verify model

Blocked on **TFactory#869**. Nothing records which model verified a build, so
there is no run that can produce the evidence. Do not run this cell until #869
lands; a run before then can only produce "UNKNOWN".

### C2 — Gemini, AIFactory then TFactory

```
BENCH_PHASE_MODELS='{"spec":"antigravity-3-pro","planning":"antigravity-3-pro","coding":"antigravity-3-pro","qa":"antigravity-3-pro","qa_fixer":"antigravity-3-pro"}'
```
- **Budget:** ~60-90 min. Metered against `GEMINI_API_KEY`; record tokens and
  time, and USD only if the key is on a paid tier.
- **Pass:** the `workers` map shows provider `antigravity` on every worker, and
  the build reaches a terminal state with tokens > 0. Zero tokens in ~30s means a
  credential or the trust guard, not a model failure.
- **Known blocker for the TFactory half:** TFactory#871 — expect the verify leg
  to exit before its first API call until that lands.

### C3 — Ollama self-hosted (p510)

```
BENCH_OLLAMA=1
BENCH_OLLAMA_CODING_MODEL=openai-compatible:qwen2.5-coder:14b
BENCH_OLLAMA_GENERAL_MODEL=openai-compatible:gemma4:12b
```
The `openai-compatible:` prefix is mandatory — `ollama:` is hard-pinned to
localhost and cannot reach p510 (AIFactory#1099, TFactory#870). The two models
above are chosen from what the host actually serves; the harness defaults name
cloud models that are not present there.

- **Budget:** no USD cost (local). Expect **substantially longer** wall-clock
  than frontier models on a 14B coder — budget several hours and set
  `BENCH_BUILD_TIMEOUT` accordingly rather than letting the default 90 min
  truncate the run.
- **Pass:** terminal state with tokens > 0 and provider `openai-compatible` in
  the `workers` map. A quality-equal result is **not** expected and is not the
  bar; the cell is asking whether the backend is usable at all.

### C4 — Ollama online (hosted)

Requires a deployment env change and a pod roll:
`OPENAI_COMPATIBLE_BASE_URL=https://ollama.com` plus
`OPENAI_COMPATIBLE_API_KEY`. This is **mutually exclusive with C3**, which uses
the same variable for the self-hosted host, so schedule the two runs apart and
restore the value afterwards.

- **Budget:** ~60-90 min; metered by the hosted provider.
- **Pass:** as C3, plus confirm the request actually left the cluster (a
  misconfigured base URL falls back to something local and still looks green).

### D1 / D2 — swarms

Same scenario and worker count for both, or the comparison is meaningless. The
harness defaults are `parallel: true, workers: 4` in `scenarios.yaml`.

- **Budget:** D1 (Opus) on a wide scenario is the most expensive cell in the
  programme — extrapolating from aws-3tier's 9.47M tokens, budget **$8-15** and
  60-90 min. D2 on Gemini, comparable time, provider-metered.
- **Pass:** all workers reach terminal state, per-worker attribution present in
  the `workers` map, and the build passes verify.

### D3 — cross-model comparison

**Blocked on AIFactory#1100.** `duration_ms` is 0 for every worker, so the
wall-clock axis of the comparison does not exist. Cost and correctness could be
compared today; time could not. Either land #1100 first, or explicitly narrow
the cell to cost and correctness and say so in the published table.

### E1 — concurrency ceiling

Now runnable — the KEDA scaler that voided the earlier attempt is healthy (see
the scorecard). Ramp concurrent builds past 5, which is the highest number
observed with 0 Pending pods.

```bash
kubectl --context factory get hpa -n factory -w          # replica response
kubectl --context factory get jobs -n factory            # concurrent build Jobs
kubectl --context factory get pods -n factory --field-selector=status.phase=Pending
```
- **Budget:** N x a trivial scenario. Use the cheapest possible spec — the cell
  measures scheduling, not build quality. Budget an afternoon and a few dollars.
- **Pass:** record the number at which Pending pods first appear **and what
  bound it** (PV binding, node capacity, KEDA max, provider rate limit). "It got
  slower" is not a ceiling. Note the maxima: aifactory 6, pfactory 4, tfactory 4.
- **Watch for:** the PFactory plan-stage OOM under concurrent bursts on a single
  replica (AIFactory#777) and the pod restart that killed two in-flight handoffs
  (PFactory#265). Both are prior findings from this cell, not new failures.

### E2 — polyglot ladder

Five languages, each to a **verify verdict**, with no hand-patching. Any run that
needed manual intervention grades `partial`.

- **Budget:** five full chains, ~$15-25 and the better part of a day. Rust and
  Go are the two that have never completed cleanly.
- **Pass:** one row per language filled in the scorecard sub-table, verify
  verdict included. Re-check Go rather than re-diagnosing it — TFactory#443 has
  closed since the failure was recorded.

### E3 — large / complex single issue

Not started. Needs a monorepo-scale target chosen first; the fleet's own repos
are the obvious candidates.

- **Budget:** unknown, and deliberately so — sizing this cell is part of the
  cell. Cap it with `BENCH_BUILD_TIMEOUT` and a token budget before starting.

### F1-F3 — published tables

Pure rollup. Run `scripts/benchmarks/report.py` over the sidecars once C, D and E
have produced them. No new runs of its own. **F3's 21.4-vs-35-minute pair is
currently a claim, not evidence** — it has no run link, job name, or worker count
behind it, and must not be published until it does.

### G1-G2 — adoption

Continuous, not a scheduled run. Intake is already configured on
`olafkfreund/aifactory-demo` and `olafkfreund/TFactory` (base branch `dev`).
Fill by counting: issues routed, PRs merged after the target repo's own CI went
green, each with a link.

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
