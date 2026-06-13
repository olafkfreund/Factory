---
layout: post
title: "Seeing the Factory think: per-worker, per-provider observability — and the hardening wave that made it safe to ship"
subtitle: "A 16-agent deep audit set off a security and CI hardening wave across the suite, then a super-brainstorm produced the missing leg: observability. The key finding was codebase-first — AIFactory already ran parallel multi-provider coding workers; we just couldn't see them. So we built additively: per-worker cost and OTel metrics, live worker events, a CFactory cockpit with a ticking per-task cost stamp, a soft budget alert, and OpenObserve bundled as the OTLP backend. You can finally answer what a build cost, on which model, and where the time went — live, per task."
date: 2026-06-13 09:00:00 +0000
author: Olaf Freund
---

This was a two-act session across the whole program. Act one was defensive:
a deep audit found things, and we hardened. Act two was the payoff: we closed
the **observability** leg — the third pillar of the bet this suite is built on.
This is the program-level write-up that ties the per-service changes together.

If you only read one sentence: **AIFactory already ran heterogeneous parallel
coding workers — Claude, Gemini, and Ollama side by side — we just couldn't
see what they cost or how long they took. Now we can, per worker and per
provider, live, per task.** Everything below is how we got there honestly.

## Act one: the audit, and the hardening wave it triggered

We ran a 16-agent deep audit of the suite. It produced epic **Factory#45** and
a queue of findings serious enough to stop new feature work until they were
closed. The interesting part is not that an audit found things — it's that the
findings clustered into two themes: **inputs we trusted that we shouldn't have**,
and **a merge button that could ship red**.

The security fixes, repo by repo:

- **GitHub Actions script-injection** — several workflows interpolated
  untrusted context (titles, branch names, bodies) straight into `run:` shell
  blocks. Fixed across repos by moving values into `env:` and quoting, the
  standard mitigation.
- **CVE-2025-66032, the `[bot]`-suffix bypass** — a copilot workflow trusted an
  actor check that a `[bot]`-suffixed identity could satisfy. Fixed across the
  repos that carried the pattern.
- **PFactory's command allowlist became an AST parser** — the old allowlist was
  a prefix check, and a prefix check is porous. A `$(...)` substitution or a
  pipe could smuggle a second command past it — in the worst case an **IMDS
  exfiltration** (`curl http://169.254.169.254/...` hidden inside an allowed
  command). We replaced it with a **bashlex**-based parser that walks the actual
  command AST, so `$()`, pipes, and chaining are evaluated, not glossed over.
- **Fail-closed boot guards** — `/mcp` and a `DISABLE_AUTH` escape hatch now
  **refuse to boot** in a posture that would silently disable auth, rather than
  starting up quietly insecure.
- **TFactory SSRF guards** — the verifier fetches URLs; it now refuses to fetch
  internal/metadata ranges.
- **CFactory finally got a test CI gate** — it was the one service shipping
  without one. Now it has one.

Then the structural fix, which matters more than any single CVE:

- **Branch protection is on.** "Auto-merge on green" is a great accelerator and
  a terrible single point of failure — if "green" is wrong, it merges anyway. It
  had caused **two regressions** (both caught, both fixed forward). Branch
  protection means auto-merge **can no longer merge red**. The accelerator stays;
  the footgun is gone.
- **A reusable PARR seam-regression check became a post-deploy gate.** The first
  attempt — a cross-repo *reusable workflow* — broke fleet deploys at startup and
  was reverted. We re-engineered it as **explicit steps** instead of a reusable
  workflow reference, which removed the cross-repo coupling that caused the
  break. (There's a [whole field report](/blog/2026/06/12/putting-the-factory-on-a-benchmark/)
  on how that seam check earns its keep.)
- **Operational glue** — a secrets/tokens runbook plus a finisher script, and a
  best-effort **teardown** for the seam-probe so it stops leaving residue.

The honest read on act one: none of this is glamorous, and all of it is the
price of letting agents push code. The audit didn't find a smoking gun; it found
the unglamorous gaps you accumulate moving fast, and we closed them before
building the next thing.

## Act two: the brainstorm, and the codebase-first finding that shaped everything

With the suite hardened, we ran a super-brainstorm on the next leg. The bet has
always been **governance + verification + observability**. We had the first two.
Observability was the gap.

The brainstorm's most important output wasn't a design — it was a **finding**.
Before designing anything, we read the code. And the code said something we
hadn't fully internalised:

> AIFactory **already** dispatched parallel coding workers across multiple
> providers. The orchestration was real and running. What was missing was the
> ability to **see** it.

Two specific blind spots:

1. **Cost had collapsed to a single model string.** A run that fanned out across
   Claude, Gemini, and a local Ollama model reported one model and one cost
   number. The parallelism was invisible in the accounting.
2. **OpenTelemetry was scaffolded but dormant.** The hooks existed; nothing
   emitted real per-worker metrics.

That finding set the entire posture: **don't rebuild what exists — make it
visible.** Every change in act two is *additive* and *spine-preserving*. We did
not touch the orchestration that already worked. We added a measurement layer
around it. Across roughly **30 PRs**, nothing in the build path was rearchitected.

## What we built

**Per-worker capture (the v1.3 completion event).** The completion event the
suite passes around grew a richer shape: instead of one model and one cost, it
now carries `workers[]` with **`by_provider`** and **`by_model`** breakdowns. The
parallelism that was always happening is now in the data envelope, where CFactory
and OpenObserve can both read it.

**Real OpenTelemetry per-worker metrics — from the web-server.** We woke the
dormant OTel scaffolding up and emit genuine per-worker metrics. A deliberate
decision here: metrics are emitted **from the web-server**, with **bounded
cardinality** — labelled by provider and model, **never by `task_id`**.
High-cardinality labels are how you melt a metrics backend; per-task detail
belongs on the **event path**, not on a metric label. So the split is clean:
**per-task detail via the event path; fleet aggregates via OpenObserve.**

**Live worker events + a 10s heartbeat.** Workers now emit live events as they
start, progress, and finish, plus a heartbeat every ten seconds. That heartbeat
is what makes the cockpit *feel* live rather than polled — and it's also how you
tell "still working" from "stalled."

**A CFactory cockpit that shows the money, live.** The cockpit gained a **live
per-task cost stamp with a ticking graph** — you watch the cost of a build
accrue in real time as workers report in, drill into **per-worker** detail, and
follow a link out to **OpenObserve** for the fleet-wide view.

**A soft budget alert — observe, don't enforce.** There is now a budget alert,
and it is deliberately **observe-only**. It surfaces when a task crosses a
threshold; it does **not** kill the run. You don't put a hard kill-switch on a
brand-new measurement the day you ship it — you watch it first, learn what
"normal" looks like, and earn the right to enforce later.

**OpenObserve, bundled as a sibling app.** Rather than reinvent a time-series
database inside CFactory, we're adding **OpenObserve** as a bundled OTLP backend
that sits **behind CFactory's ingress** — same pattern as the other services:
**Keycloak SSO** in front, **Cloudflare tunnel** for access. The practical
upshot is that `OTEL_EXPORTER_OTLP_ENDPOINT` simply **points at CFactory**, and
CFactory doesn't have to grow a TSDB to honour it. Observability backend as a
sibling, not as a feature smuggled into the cockpit.

## The decisions, stated plainly

- **Codebase-first.** The most valuable hour was the one spent reading the code
  before designing. It turned a "build parallel workers" project into a "make
  the existing parallel workers visible" project — a far smaller, far safer
  scope.
- **Additive and spine-preserving.** ~30 PRs, zero changes to the orchestration
  that worked. New behaviour rode alongside the old, never through it.
- **Branch protection as the safety net.** Shipping 30 PRs of measurement code
  is exactly when you want a merge button that can't ship red.
- **Bounded-cardinality metrics, event-path detail.** Metrics answer "how is the
  fleet doing"; events answer "what happened on task #142." Don't make one do
  the other's job.
- **Observe, don't enforce.** The budget alert watches before it ever blocks.
- **OpenObserve as a sibling, not OTLP-in-CFactory.** Reuse the proven
  ingress/SSO/tunnel pattern; don't reinvent a TSDB.

## What it means for the future

Heterogeneous parallel builds — Claude plus Gemini plus Ollama, running at once —
are now **observable and governable per worker and per provider**. For the first
time you can answer, live and per task:

> What did this build cost, on which model, and where did the time go?

That question is the foundation for the next two things the market is converging
on: **cost-aware model routing** (send the cheap subtasks to the cheap model,
because now you *know* which is which) and **budget governance** (enforce, once
you've watched long enough to set a fair threshold). This session closed the
**observability leg** and the **cost-per-task FinOps gap** — the third pillar
under the bet. Governance, verification, observability: the factory you can
**trust**, **verify**, and now **watch**.

---

*The per-service tours have the receipts: the [CFactory cockpit](/cfactory/)
(live cost stamp, per-worker drill-down, OpenObserve link) and the
[AIFactory tour](/aifactory/) (per-worker OTel metrics, live worker events,
soft budget alert). Live status is in the
[program board](https://github.com/users/olafkfreund/projects/1).*
