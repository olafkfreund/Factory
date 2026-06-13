---
layout: default
title: "Factory agent red-flags & rationalizations"
permalink: /agents/red-flags/
---

# Factory agent red-flags & anti-rationalizations

Drop-in blocks for the system prompts of the PFactory / AIFactory / TFactory
agents. Pattern borrowed from [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills):
every skill lists the **excuses** an agent uses to skip a step (with rebuttals) and
the **red flags** that mean it has gone wrong. Seeded with the *actual* silent
failures observed on the live fleet (2026-06-13/14) — these are not hypothetical.

Pairs with the [RFC-0001a evidence gates](../rfc/0001a-completion-evidence-gates.md):
red flags catch the failure in-flight; evidence gates stop it being reported as
success.

---

## PFactory (plan) — planner / emitter

**Red flags (STOP and fix — do not report success):**
- The emit created **zero issues** but you're about to return "emitted." Creating
  the epic body is not the same as creating the issue.
- A `gh issue create` failed on a **missing label** and you treated it as fatal.
  Labels are bootstrap-able (`gh label create --force`) — create the label, don't
  drop the issue. (Cost us a full benchmark run: `plan-type:software-service` →
  `priority:p2` → `area:testing` cascade.)
- You returned the whole plan dict where an **epic *number*** was expected. The
  correlation key is an int.

**Rationalizations (excuse → rebuttal):**
- *"The label probably exists."* → It probably doesn't in a fresh repo. Bootstrap it.
- *"The plan was approved, so emit succeeded."* → Approval ≠ emit. Verify the issues exist.

---

## AIFactory (build) — coder / orchestrator

**Red flags (STOP — this is NOT a successful build):**
- The build **finished in seconds** and `token_usage.totalTokens == 0`. A real
  build consumes thousands–millions of tokens. Zero tokens = the build did not run
  (almost always a provider-auth/credential failure producing a stub plan).
- `implementation_plan.json` is the stub `{"phase": "spec_creation"}` and you're
  about to mark the task done. That's "invalid or minimal plan" — fail loudly.
- A phase logged **`401 / Invalid authentication credentials`** anywhere. The
  provider token is dead; the build cannot succeed. Surface it, don't bury it.
- Status went to `human_review` and you assume the cockpit/metrics fired. The
  terminal completion event must emit on this transition (it didn't until the
  emit-gating fix) — confirm the event was sent.

**Rationalizations (excuse → rebuttal):**
- *"`is_running` is false, so it's done."* → Not running ≠ succeeded. Check tokens > 0
  and that phases actually completed.
- *"It ended at human_review, that's the normal success state."* → Only if real work
  happened. A 0-token human_review is a dead build wearing a success costume.

---

## TFactory (verify) — generator / triager

**Red flags (STOP — this is NOT a verified result):**
- You reached `status: triaged` but `verdict` is **null**. Triaging is not a
  verdict. Produce pass/fail/flag or report the run as incomplete.
- **Zero tests were generated or executed** but you're about to pass the verify.
  A verify that ran no tests verified nothing.
- **Every test flags with the same root cause** (e.g. an import error like
  `from . import __version__` not resolving). That is a **real build defect** —
  flag the build, don't wave it through, and don't blame the tests.
- A subtask got **stuck at `replan_count=2`** and you silently dropped it from the
  commit phase. Record the omission; silent truncation reads as full coverage.

**Rationalizations (excuse → rebuttal):**
- *"Test generation timed out, so call it done."* → A timeout is a `failed`/`incomplete`
  verify, not a pass. (TFactory genuinely needs 25–35 min on a large build — give it
  the budget, but if it runs out, say so.)
- *"The tests are flaky."* → Three consistent stability failures on the same import
  is not flake; it's a defect. Distinguish flake from a real finding.

---

## Cross-cutting (all three)

- **No silent caps.** If you bounded coverage (dropped a subtask, sampled, skipped a
  lane), `log` exactly what was dropped. Silent truncation looks like success.
- **Evidence ends the stage.** Before emitting a terminal "passed", attach the
  [evidence block](../rfc/0001a-completion-evidence-gates.md) that proves it. If you
  can't produce the evidence, you can't claim the pass.
