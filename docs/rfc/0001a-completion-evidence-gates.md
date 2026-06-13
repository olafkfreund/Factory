---
layout: default
title: "RFC-0001a: Completion-Event Evidence Gates"
permalink: /rfc/evidence-gates/
---

# RFC-0001a — Completion-Event Evidence Gates (addendum to RFC-0001)

> **Status:** Proposed · **Extends:** [RFC-0001](./0001-correlation-key-and-completion-event.md) v1.1 → v1.2 · **Created:** 2026-06-14
> Additive. Old consumers ignore the new `evidence` block; producers that omit it
> are treated as "unproven" (see §4), never as "passed".

## 1. Motivation — "seems right" is not "is right"

A completion event today can report a terminal `status: "completed"` / `"passed"`
**without any proof that real work happened.** Two failures observed on the live
fleet (2026-06-13) both passed silently because nothing checked for evidence:

- **AIFactory** emitted a build that finished in ~30s having consumed **0 tokens**
  (an expired provider credential produced a stub plan). The orchestrator read
  `is_running == false` and reported **passed**. A dead build looked green.
- **TFactory** terminated a verify at `status: "triaged"` with **`verdict: null`** —
  it ran the suite but never produced the verdict the contract implies, and
  downstream treated "reached a terminal phase" as success.

The discipline (borrowed from the agent-skills practice *"evidence requirements end
every skill"*): **a stage may only claim success if it carries the evidence that
proves it.** This addendum makes that a contract rule, not a convention.

## 2. The `evidence` block

Every completion event with a *successful* terminal status (`completed`,
`passed`, `verified`) MUST include an `evidence` object. Fields are per-stage:

```jsonc
"evidence": {
  // Universal (all stages)
  "produced_at": "2026-06-13T22:55:08Z",
  "proof_kind": "tokens|tests|issues|artifact",   // what proves this stage ran

  // PFactory (plan)  — proof_kind: "issues"
  "epic_issue": 134,                 // the emitted epic (int, not the plan dict)
  "child_issues": [135,136,137],     // ≥1 child issue actually created
  "child_count": 8,

  // AIFactory (build) — proof_kind: "tokens"
  "total_tokens": 2576651,           // MUST be > 0 for a real build
  "cost_usd": 1.5108,
  "phases_completed": ["planning","coding","validation"],
  "worktree_sha": "a1b2c3d",         // the commit the build produced

  // TFactory (verify) — proof_kind: "tests"
  "verdict": "pass|fail|flag",       // MUST be non-null on a terminal verify
  "lanes_run": ["unit","api"],
  "tests_generated": 6,
  "tests_executed": 6                 // > 0 — a verify that ran no tests is not verified
}
```

## 3. Per-stage evidence rules (the gates)

A producer MUST downgrade a "successful" terminal status to `failed` (with
`reason: "no_evidence"`) when its gate is not met:

| Stage | "passed" requires |
|---|---|
| **PFactory** plan | `evidence.epic_issue` is an int **and** `child_count ≥ 1` (the emit actually created issues) |
| **AIFactory** build | `evidence.total_tokens > 0` **and** `phases_completed` is non-empty (a 0-token "build" is a failure, not a pass) |
| **TFactory** verify | `evidence.verdict` is non-null **and** `evidence.tests_executed > 0` (reaching `triaged` is not a verdict) |

Consumers (CFactory, the benchmark harness, the PARR seam-gate) MUST treat a
successful status **without** a satisfying `evidence` block as **unproven**, and
render/report it as failed — never green.

## 4. Backward compatibility

- The `evidence` block is **additive**; pre-v1.2 producers that don't emit it are
  treated as `unproven` by §3 consumers (fail-safe, not fail-open).
- The existing scalar `usage.*` and `status` fields are unchanged.
- The benchmark harness's `tokens > 0` code-stage gate and verify-skip-on-failure
  (shipped 2026-06-13) are the first implementation of these rules; this RFC makes
  them a fleet-wide contract instead of one consumer's heuristic.

## 5. Why this matters for governance

The program's pitch is *governed, auditable* automation. An audit trail that can
record "passed" for work that never happened is worse than no trail. Evidence gates
make every green in the system falsifiable — the EU-AI-Act-grade property the spine
is supposed to provide.
