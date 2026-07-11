# SWE-bench Verified baseline — 2026-07-11

First end-to-end benchmark of the PARR pipeline (PFactory -> AIFactory ->
TFactory) on a real external benchmark. Every task was submitted through the
normal intake and driven autonomously by `scripts/benchmarks/run_pipeline_task.py`;
the produced patches were scored by the OFFICIAL SWE-bench harness (swebench
4.1.0), never self-scored.

## Configuration

- Task set: `benchmarks/swebench-verified-50.json` (50-task stratified subset).
- Model / mode: fleet default (Opus 4.8), ponytail minimal-code on, graphify
  code-graph OFF, no cost-routing policy, injection scan in warn mode.
- Execution: local AIFactory (dev), subscription OAuth only. 4-way concurrent.
- Predictions: `benchmarks/all-predictions.jsonl`. Harness run_id
  `factory-baseline-20260711`.

## Headline

- **Resolve rate: 19/50 = 38.0%** on SWE-bench Verified (official harness).
- **Of the 28 non-empty patches, 19 resolved / 5 unresolved / 4 harness-error
  = 19/24 scorable = 79.2%.** When the pipeline produces a patch the harness
  can score, it is correct ~4 times in 5.
- **Biggest gap: 22/50 (44%) produced NO patch** (empty diff). This is an
  orchestration/reliability gap, not model capability — the single highest-
  leverage thing to fix to raise the score.
- 4 instances hit harness INFRASTRUCTURE errors (Docker image-build read
  timeouts under 4-way concurrency), not pipeline faults; they are re-scorable.

## Cost

- Total: 118.3M tokens, **$57.65** across 50 tasks.
- Per task: avg $1.15 / 2.37M tokens; median 1.30M tokens.
- Heavy tail: one task consumed 12.5M tokens (~$6). A per-task token ceiling
  and cost-aware routing (RFC-0014, now implemented) are the levers.

## Resolve rate by repo

| repo | resolved / total |
|---|---|
| django | 10/24 |
| sympy | 5/8 |
| sphinx | 1/5 |
| pylint | 1/1 |
| pytest | 1/2 |
| xarray | 1/2 |
| astropy | 0/2 |
| matplotlib | 0/3 |
| scikit-learn | 0/3 |

## Resolve rate by difficulty

| difficulty | resolved / total |
|---|---|
| <15 min fix | 7/21 |
| 15 min - 1 hour | 11/26 |
| 1-4 hours | 1/3 |

## Verdict-vs-gold calibration

How the pipeline's OWN terminal status compared to the official outcome — the
key question for trusting the pipeline's self-report:

| pipeline status | RESOLVED | unresolved | empty-patch | harness-error |
|---|---|---|---|---|
| human_review (39) | 12 | 4 | 21 | 2 |
| failed (9) | 6 | 0 | 1 | 2 |
| backlog (2) | 1 | 1 | 0 | 0 |

Two findings that matter:

1. **The pipeline's status is a WEAK proxy for correctness.** 21 of 39
   `human_review` tasks carried no patch at all, and — strikingly — **6 of the
   9 tasks the pipeline marked `failed` actually produced a correct, gold-
   passing patch.** Those 6 are the API-timeout cases the driver's salvage
   fix (#282) recovered post-hoc; without salvage they would have been lost.
   Do not treat pipeline status as a verdict — the deterministic harness (or
   TFactory's own executed tests) is required.
2. Of the 18 tasks that reached verify (`human_review`) WITH a patch, 12 (66%)
   resolved — so the verify stage is seeing mostly-correct work, but the
   44% empty-patch rate upstream is what caps the overall number.

## What this says to do next

- **Close the empty-patch gap (44%).** The coder is exiting without writing a
  diff on nearly half the tasks (often when the target repo's tests could not
  run locally). Per-task venv provisioning is in the driver; making the coder
  reliably use it, and hardening the "no subtasks / silent exit" paths
  (AIFactory #810 landed one such guard), is the top lever.
- **Re-run with graphify ON and with a routing policy** to measure their
  deltas against this baseline (AIFactory #803/#804) — the whole point of the
  re-runnable harness.
- The 79% scorable-patch rate says the model+prompt are sound; the gap is
  pipeline reliability, not capability.

## Reproduce

    # per instance (through the live pipeline)
    python scripts/benchmarks/run_pipeline_task.py --instance-id <id> ...
    # score (official harness)
    python -m swebench.harness.run_evaluation \
      --dataset_name SWE-bench/SWE-bench_Verified \
      --predictions_path benchmarks/all-predictions.jsonl \
      --run_id <run> --max_workers 4

Caveats: single run (no self-consistency); 4 harness-infra errors depress the
raw number by up to 4; django-heavy sample (24/50) mirrors the dataset's own
distribution; local execution, not the k8s Job path.

## Per-instance results

| instance | difficulty | pipeline status | patch | gold outcome | tokens | cost |
|---|---|---|---|---|---|---|
| astropy__astropy-14309 | <15 min fix | human_review | no | empty-patch | 298,532 | $0.24 |
| astropy__astropy-14598 | 15 min - 1 hour | human_review | yes | unresolved | 0 | $0.00 |
| django__django-10554 | 1-4 hours | human_review | yes | RESOLVED | 8,302,047 | $3.96 |
| django__django-10999 | <15 min fix | human_review | yes | unresolved | 1,213,633 | $0.64 |
| django__django-11149 | 15 min - 1 hour | human_review | no | empty-patch | 973,601 | $0.60 |
| django__django-11299 | <15 min fix | human_review | yes | RESOLVED | 2,931,714 | $1.26 |
| django__django-11477 | 15 min - 1 hour | human_review | yes | RESOLVED | 5,029,040 | $2.19 |
| django__django-11551 | 15 min - 1 hour | human_review | yes | RESOLVED | 2,469,081 | $1.14 |
| django__django-11749 | 15 min - 1 hour | human_review | no | empty-patch | 338,754 | $0.31 |
| django__django-12304 | <15 min fix | human_review | yes | RESOLVED | 1,539,742 | $0.75 |
| django__django-12406 | 15 min - 1 hour | human_review | yes | RESOLVED | 3,681,175 | $1.78 |
| django__django-12419 | <15 min fix | human_review | no | empty-patch | 568,220 | $0.40 |
| django__django-12754 | 15 min - 1 hour | failed | yes | RESOLVED | 5,583,414 | $2.31 |
| django__django-13023 | <15 min fix | human_review | no | empty-patch | 751,608 | $0.41 |
| django__django-13344 | 1-4 hours | human_review | no | empty-patch | 9,174,098 | $4.06 |
| django__django-13809 | 15 min - 1 hour | human_review | no | empty-patch | 766,815 | $0.42 |
| django__django-14351 | 15 min - 1 hour | human_review | no | empty-patch | 1,729,091 | $1.00 |
| django__django-14771 | 15 min - 1 hour | human_review | yes | RESOLVED | 2,012,094 | $0.89 |
| django__django-15277 | <15 min fix | failed | yes | RESOLVED | 1,115,117 | $0.53 |
| django__django-15525 | 15 min - 1 hour | human_review | no | empty-patch | 1,022,940 | $0.58 |
| django__django-15572 | <15 min fix | human_review | yes | RESOLVED | 1,290,395 | $0.65 |
| django__django-15916 | 15 min - 1 hour | failed | yes | harness-error | 1,903,390 | $0.93 |
| django__django-16100 | <15 min fix | human_review | no | empty-patch | 746,266 | $0.41 |
| django__django-16429 | <15 min fix | human_review | no | empty-patch | 338,764 | $0.25 |
| django__django-16950 | 15 min - 1 hour | failed | no | empty-patch | 2,426,094 | $1.61 |
| django__django-9296 | <15 min fix | human_review | yes | harness-error | 1,299,815 | $0.63 |
| matplotlib__matplotlib-22719 | <15 min fix | human_review | no | empty-patch | 493,100 | $0.34 |
| matplotlib__matplotlib-24970 | 15 min - 1 hour | human_review | yes | harness-error | 11,001,955 | $5.24 |
| matplotlib__matplotlib-26342 | 15 min - 1 hour | human_review | no | empty-patch | 712,534 | $0.41 |
| pydata__xarray-4966 | 15 min - 1 hour | human_review | no | empty-patch | 355,236 | $0.27 |
| pydata__xarray-6461 | <15 min fix | failed | yes | RESOLVED | 3,187,120 | $1.37 |
| pylint-dev__pylint-6386 | 15 min - 1 hour | human_review | yes | RESOLVED | 12,520,631 | $6.19 |
| pytest-dev__pytest-10051 | 15 min - 1 hour | human_review | yes | RESOLVED | 3,547,618 | $1.68 |
| pytest-dev__pytest-5809 | <15 min fix | failed | yes | harness-error | 1,141,069 | $0.59 |
| scikit-learn__scikit-learn-13328 | <15 min fix | human_review | no | empty-patch | 294,262 | $0.23 |
| scikit-learn__scikit-learn-14710 | 15 min - 1 hour | human_review | no | empty-patch | 760,506 | $0.48 |
| scikit-learn__scikit-learn-25747 | 15 min - 1 hour | human_review | no | empty-patch | 568,429 | $0.42 |
| sphinx-doc__sphinx-10449 | <15 min fix | human_review | yes | RESOLVED | 4,443,816 | $1.91 |
| sphinx-doc__sphinx-7440 | <15 min fix | human_review | yes | unresolved | 0 | $0.00 |
| sphinx-doc__sphinx-7748 | 15 min - 1 hour | human_review | no | empty-patch | 550,054 | $0.36 |
| sphinx-doc__sphinx-7985 | 15 min - 1 hour | backlog | yes | unresolved | 5,504,502 | $2.34 |
| sphinx-doc__sphinx-8475 | <15 min fix | human_review | no | empty-patch | 334,399 | $0.24 |
| sympy__sympy-12481 | <15 min fix | human_review | no | empty-patch | 492,585 | $0.34 |
| sympy__sympy-13647 | 15 min - 1 hour | failed | yes | RESOLVED | 2,367,919 | $1.13 |
| sympy__sympy-16597 | 1-4 hours | human_review | yes | unresolved | 2,142,213 | $0.99 |
| sympy__sympy-16792 | 15 min - 1 hour | human_review | yes | RESOLVED | 2,044,423 | $0.97 |
| sympy__sympy-18189 | <15 min fix | human_review | no | empty-patch | 291,142 | $0.23 |
| sympy__sympy-19783 | 15 min - 1 hour | backlog | yes | RESOLVED | 3,032,450 | $1.42 |
| sympy__sympy-23950 | 15 min - 1 hour | failed | yes | RESOLVED | 3,644,350 | $1.83 |
| sympy__sympy-24539 | <15 min fix | failed | yes | RESOLVED | 1,394,558 | $0.70 |
