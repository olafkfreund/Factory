---
layout: default
title: "RFC-0008: Autonomous PARR Completion"
permalink: /rfc/autonomous-completion/
---

# RFC-0008 — Autonomous PARR Completion

> **Status:** Partially Implemented (the seven robustness fixes shipped in AIFactory; remaining autonomy gaps tracked) · **Created:** 2026-06-18 · **Updated:** 2026-06-20 · **Extends:** [RFC-0001](./0001-correlation-key-and-completion-event.md) (correlation key), [RFC-0002](./0002-task-contract.md) (task contract), [RFC-0005](./0005-environment-manifest-and-toolchain-provisioning.md) (toolchain), [RFC-0006](./0006-verification-assurance-levels.md) (assurance), [RFC-0007](./0007-access-and-credential-provisioning.md) (access) · **Affects:** PFactory, AIFactory, TFactory, CFactory
>
> A team submits **intent**. The pipeline must return a working, tested artifact **with no human in the happy path**, and **bounded auto-correction** in the unhappy path. Human review is reserved for ambiguous *intent* — never for engineering mechanics the user should not have to know about. The rule carried forward from RFC-0006: never claim something works when it was never verified; this RFC adds that we must also never *stall silently* or *escalate to a human for something the pipeline could have fixed itself*.

## 1. The problem — the seams hold, but a human is still in the loop

On 2026-06-18 we ran the full pipeline end to end from a single brief: the
OpenAPI documentation + Backstage catalog entry for a small "Task Board"
service ([factory-demo-taskboard](https://github.com/olafkfreund/factory-demo-taskboard)).
The seams held: PFactory produced a Backstage-grounded signed contract, AIFactory
built the service and its web UI, TFactory independently generated a 15-file test
suite and **caught a real behavioural bug** (the service accepted a whitespace-only
title) that the build and a manual smoke test both missed.

That is the good news, and it is the point of the architecture. The bad news is
that **the run required a human at five separate points**, none of which a real
team submitting a brief would tolerate or even understand:

| # | What stopped the run | Class | Who should handle it |
|---|---|---|---|
| 1 | AIFactory QA agent (gemini CLI) hung 300s ×3, escalated to `human_review` | execution / provider | auto: bounded retry + failover |
| 2 | `CLAUDE_CODE_OAUTH_TOKEN` expired → 401, build produced nothing | infra / credential | auto: pre-flight + non-expiring key |
| 3 | Build had no runnable entrypoint (app assembled only in test fixtures) | planning gap | auto: implicit-requirement + smoke-boot |
| 4 | TFactory test-validation env had no `pytest` → unbounded replan loop | execution / env | auto: runner deps + replan cap |
| 5 | TFactory review-phase agent exited silently; status hung at `reviewing` | orchestration | auto: liveness watchdog |

Every one of these was *recoverable*, and the pipeline did the honest thing in
the sense that **it never shipped anything broken** — it escalated or stalled.
But escalation-to-human and silent-stall are not the same as *autonomous
completion*. This RFC closes the gap between "never ships garbage" and "delivers
a working artifact without supervision".

## 2. The reframe — complete the plan the user did not know to write

The deepest finding is not any single bug. It is that **users describe an idea,
not an implementation**. "A task board" implies — to any engineer — a service
that *starts*, *declares its dependencies*, *passes a health check*, and is
*deployable*. The user never writes those acceptance criteria, so today nothing
demands them, so the gate cannot enforce them, so the build can satisfy every
stated criterion and still not run.

The pipeline's job is therefore not only to *check* the plan the user wrote, but
to **complete it** with the implicit engineering requirements the domain
implies — and then hold the build to them automatically.

## 3. The fixes, by stage

### 3.1 PFactory — intent becomes a complete contract

- **Implicit-requirements enrichment.** For `service`-type plans, inject default
  acceptance criteria the user did not state: *the service starts*, *declares a
  dependency manifest*, *exposes and passes a health check*, *is deployable in
  the target environment*. Source these from the plan type + the Backstage
  `Component` annotations (which already carry language/framework/runtime).
- **Completeness review lens + readiness checks** so the gate has something to
  enforce. A `service` plan with no "starts and serves" criterion fails
  readiness with a remediation, rather than passing silently.

### 3.2 AIFactory — code *and* verify

- **(a) Auth pre-flight.** Before accepting a build, probe each configured
  provider (`claude -p`-style). Fail fast with a named, actionable error on 401;
  do not start a build that cannot authenticate.
- **(b) Non-expiring credential for headless builds.** Prefer `ANTHROPIC_API_KEY`
  over the interactive OAuth subscription token for server-side execution; the
  OAuth token is for interactive Claude Code and expires. (Operationally:
  eliminate the entire credential-expiry class.)
- **(c) Provider bounded-retry + failover.** A hung/timed-out provider CLI must
  retry within a deadline and fail over to another configured provider — never
  hang for 15 minutes, never silently escalate.
- **(d) QA smoke-boot.** QA must *start the artifact* (`uvicorn app.main:app`,
  hit `/health`, exercise a representative AC against the **running** service) —
  not only run unit tests. Today `pytest` passed against an app assembled in
  `conftest` while no runnable entrypoint existed. A smoke-boot gate catches this
  with zero human input.
- **(e) qa_fixer auto-repairs mechanics.** A missing entrypoint / missing dep is a
  mechanical defect the fix loop should repair and re-verify, not a reason to
  escalate to `human_review`.
- **(f) Declared test dependencies.** Dependencies the generated tests need
  (e.g. `httpx` for FastAPI's `TestClient`) must be added to the dependency
  manifest, not assumed present.
- **(g) Commit/finalize reliability.** The agent's written files must be
  committed and the commit awaited/verified; a post-run bookkeeping error must
  never leave agent work uncommitted.

### 3.3 TFactory — independent gate, and the loop must close itself

- **(a) Validation runs in the provisioned runner, not in-pod.** The in-pod
  validation environment lacked `pytest`/`packaging`, so every generated test
  failed with `ModuleNotFoundError` and the planner replanned forever. Test
  validation must run in the Nix runner ([RFC-0005](./0005-environment-manifest-and-toolchain-provisioning.md)
  Tier A) or against an image that bakes the test toolchain.
- **(b) Replan cap + liveness watchdog.** Bound the plan↔generate replan loop
  (fail loudly after *N* with the rejection reason); detect when an agent
  subprocess exits and transition the task to a terminal/recoverable state
  instead of leaving it hung at `reviewing`.
- **(c) Route UI criteria to the browser lane.** UI acceptance criteria must
  dispatch the Nix Playwright browser lane (screenshots + `.webm`), not be
  approximated by static-HTML string assertions in the unit lane. In the demo,
  a unit-lane assertion on `/api/tasks/` failed because the JS builds that URL at
  runtime — the behaviour works (the browser recording proves it); the routing
  was wrong.
- **(d) Autonomous handback.** When TFactory finds a real gap (e.g. the
  whitespace-title bug), it must auto-drive AIFactory via the existing handback
  mechanism (`handback_received.json`) to fix and re-verify in a closed loop,
  threaded by the [RFC-0001](./0001-correlation-key-and-completion-event.md)
  correlation key — no human ticket.

### 3.4 CFactory — make the stall visible

- Surface a **liveness / stuck-task signal** (last-activity age per work-item) so
  a hung phase shows as an alert in the watch plane rather than a quiet
  "reviewing". Pair with the provider-auth health tile.

## 4. The honesty rule, extended

RFC-0006 forbids overclaiming verification. RFC-0008 adds two siblings:

1. **No silent stall.** A task that stops making progress must surface as failed
   or recovering, never sit indefinitely in a non-terminal phase.
2. **No human for mechanics.** Escalating to a human for something the pipeline
   could deterministically detect and fix (missing entrypoint, missing dep,
   expired token, hung provider) is a defect, not a feature. Human review is for
   *ambiguous intent* only.

## 5. Rollout order

Highest leverage first — the subset that would have made the demo run hands-off:

1. **3.3a + 3.3b** (TFactory runner deps + replan cap / watchdog) — unblocks the
   most expensive failure (the infinite loop and the silent stall).
2. **3.2d** (QA smoke-boot) — turns "passes tests but does not run" into an
   auto-caught, auto-fixed defect.
3. **3.1** (implicit-requirements enrichment) — so the runnable-artifact
   requirement exists at plan time.
4. **3.2a/3.2b/3.2c/3.2f** (auth pre-flight, non-expiring key, failover, deps).
5. **3.3c + 3.3d + 3.2e** (browser routing, autonomous handback, auto-repair).
6. **3.4** (CFactory liveness signal).

## 6. Acceptance

The same brief (`factory-demo-taskboard`) re-run from intent produces a merged,
running, browser-verified service **with no human intervention**, and any induced
failure (revoke a token, break a dependency, hang a provider) is detected and
either auto-recovered or surfaced as a named failure within a bounded time — never
a silent stall, never a human asked to supply a `main.py`.
