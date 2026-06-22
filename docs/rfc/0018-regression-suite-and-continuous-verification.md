---
layout: default
title: "RFC-0018: Regression Suite & Continuous Verification — making generated tests live over time"
permalink: /rfc/regression-suite-and-continuous-verification/
---

# RFC-0018 — Regression Suite & Continuous Verification

> **Status:** Shipped end-to-end 2026-06-22 (TFactory epic #482 + all 7 children #483–#489 closed; PRs #490–#511; follow-up: MCP-tool surface #512) · **Created:** 2026-06-22 · **Owner:** TFactory ·
> **Extends:**
> [RFC-0006](./0006-verification-assurance-levels.md) (VAL — a regression run
> re-asserts the same VAL over time),
> [RFC-0016](./0016-horizontal-concurrent-execution.md) /
> [RFC-0017](./0017-full-job-native-execution-and-scale-out.md) (Job-native
> execution — regression runs are just scheduled fan-out of the same Job
> substrate) ·
> **Affects:** TFactory (new regression subsystem + scheduling + portal surface).
> No contract changes to PFactory/AIFactory.

## 1. Motivation

TFactory is excellent at one thing: take a **single feature's acceptance
criteria**, generate tests, run them once against a real deployment, grade them
with the five-signal verdict, and triage. But the platform is **one-shot and
feature-scoped**. Once a suite is committed to `main`, **nothing re-runs it**. A
commit that breaks five of the two hundred tests already in the corpus enters
`main` silently — TFactory never looks back.

That single fact is why "regression testing is hard" on TFactory today. The raw
material to fix it already exists and is unused for this purpose:

- a **persistent test corpus** per project (`tests-catalog.json`, versioned via
  `generation_version`);
- **cross-run flaky history** (`flaky_history.py`, 30-run flip-rate ring);
- **per-test coverage deltas** (`coverage_delta.py`);
- **visual baselines** (`evidence/visual_baseline.py`).

None of it is wired into a loop that re-executes the corpus and **diffs results
over time**. This RFC defines that loop: a regression subsystem that re-runs the
persisted corpus on a schedule (or on demand), stores each run, diffs run N
against a baseline, classifies regressions vs fixes vs flakes, quarantines
chronic flakies, and tracks coverage drift — turning TFactory from a *one-shot
feature verifier* into a *continuous quality system*.

## 2. Current state (audited 2026-06-22)

| Capability | Today | Gap |
|---|---|---|
| Persistent corpus | `tests-catalog.json` survives runs, versioned | Never re-executed as a suite |
| Run results | `findings/verdicts.json` per spec run | Not persisted as a comparable time series per project |
| Flaky detection | flip-rate over 30 runs | Flakies only down-ranked, never quarantined/retried |
| Coverage | per-test delta vs branch baseline | No project-level trend or drift alert |
| Triggers | reactive (label / AIFactory handoff / manual) | No scheduled or programmatic regression run |
| Regression signal | none | No "run N vs run N-1" diff, no regression flag |

## 3. Principles

1. **Reuse the corpus and the runners.** A regression run is the existing
   execution path applied to the **already-persisted** tests, not new generation.
2. **A run is an immutable, comparable record.** Every regression run is stored
   keyed by `(project, commit, ran_at)` so any two runs can be diffed.
3. **Classification over raw pass/fail.** The value is the *diff*: newly-failing
   (regression), newly-passing (fixed), still-failing, flaky, quarantined.
4. **Flakiness is a first-class state, not noise.** Chronic flakies are
   quarantined with a reason and a retry policy, not silently failing the suite.
5. **Honest trends.** Coverage drift and regression counts are reported as
   evidence, never as a blanket "passing".
6. **Schedule is just fan-out.** Reuse RFC-0016/0017 Job-native execution; a
   nightly run is N Jobs, not a new runtime.

## 4. Design

### 4.1 Regression run record + baseline store (foundation)

A new `agents/regression/` subsystem. A `RegressionRun` is an immutable record:

```
RegressionRun {
  run_id, project_id, commit, ran_at, target_url?,
  results: [ TestOutcome { test_id, lane, framework, status, duration_ms,
                           coverage_pct?, evidence_uri? } ],
  totals: { passed, failed, skipped, quarantined },
  baseline_run_id?            # the run this one is diffed against
}
```

Stored under `~/.tfactory/workspaces/<project>/regression/<run_id>.json` (atomic
write, same convention as `workspace_status.py`), with a `latest.json` /
`baseline.json` pointer. Pure data + I/O; no execution. **Fully unit-testable in
isolation — this is child issue #1 and the first PR.**

### 4.2 Diff & classification

Given a run and its baseline, classify each `test_id`:

| Class | Condition |
|---|---|
| `regression` | passed in baseline, fails now |
| `fixed` | failed in baseline, passes now |
| `still_failing` | failed in both |
| `stable_pass` | passed in both |
| `flaky` | flip-rate ≥ threshold from `flaky_history` |
| `quarantined` | marked quarantined (skipped from gate) |
| `new` | not present in baseline |
| `dropped` | in baseline, absent now |

Emits `regression_report.{md,json}`. Pure logic over two `RegressionRun`s +
flaky history. (Child #1 covers the store; classification ships with it as the
core "brain".)

### 4.3 Re-run executor

Load `tests-catalog.json`, materialize the corpus, execute via the **existing**
runners (`docker_runner` / `kube_sandbox` / Nix Job), assemble a `RegressionRun`,
set its baseline to the prior `latest`, run the diff, write the report. CLI:
`python -m apps.backend... regression run --project P [--commit SHA] [--select …]`.
(Child #2.)

### 4.4 Flaky quarantine + retry policy

Consume `flaky_history` flip-rate. A test over the quarantine threshold for K
consecutive runs is **quarantined**: excluded from the pass/fail gate, surfaced
in the report with its history, retained for visibility. A transient single
failure is **retried** up to N times before counting as failed. Quarantine state
persists per project and is operator-releasable. (Child #3.)

### 4.5 Coverage trend ledger

Persist project-level coverage per run (roll up the existing per-test
`coverage_delta`). Compute drift vs the trailing baseline; flag a drop beyond a
configurable threshold. Exposed in the report and the portal. (Child #4.)

### 4.6 Impact-based selection

Build a reverse index from the catalog's `covers_acs` (and, where available, the
file/module each test touches) to `test_id`. Given a changed AC set or a git
diff, select the affected subset to re-run: `--select changed`. Falls back to
full-corpus when the map is unavailable. (Child #5.)

### 4.7 Scheduling & triggers

A nightly GitHub Actions workflow (`tfactory-regression-nightly.yml`) plus a
manual/programmatic entrypoint (MCP tool + `POST /api/regression/run`) that kicks
a regression run for a project against `main`. Reuses RFC-0016/0017 Job dispatch
for fan-out. (Child #6.)

### 4.8 Portal surface

A regression view: run history, current regressions/fixes, flaky/quarantine list,
and the coverage trend. (Child #7, frontend, Tier 1.5.)

## 5. Phasing

1. **Phase 1 — Detection brain (no infra).** Regression run record + baseline
   store + diff/classification, fully unit-tested (child #1). This alone makes
   "did anything regress between these two runs?" answerable.
2. **Phase 2 — Execution.** Re-run executor over the persisted corpus (child #2);
   flaky quarantine + retry (child #3); coverage trend ledger (child #4).
3. **Phase 3 — Selection + automation.** Impact-based selection (child #5);
   nightly schedule + programmatic trigger (child #6); portal surface (child #7).

## 6. Verification

- **Diff correctness:** synthetic baseline + current run with one each of
  regression / fixed / flaky / new / dropped → classification matches expected
  (unit, Phase 1).
- **Re-run proof:** a project with a known-good corpus re-runs green; introduce a
  breaking change → exactly the affected tests classify as `regression` and the
  run is marked failed.
- **Quarantine proof:** a deliberately flaky test crosses the threshold, gets
  quarantined out of the gate, and a green suite passes despite it; operator
  release returns it to the gate.
- **Trend proof:** coverage drop beyond threshold raises a drift flag in the
  report.
- **Schedule proof:** the nightly workflow triggers a regression run that lands a
  stored `RegressionRun` + report without manual action.

## 7. Adoption (tracked by the TFactory epic)

Tracked as a TFactory epic with seven child issues (§4.1–4.8). No PFactory /
AIFactory / contract changes. Phase 1 is implementable and shippable immediately
because the corpus, flaky history, and coverage-delta primitives already exist.
