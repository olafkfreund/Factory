---
layout: post
title: "Field report: we put the Factory on a benchmark — and it found six bugs in our own harness first"
subtitle: "Phase 1 of the make-it-great plan was 'prove it.' So we pointed our PARR benchmark at the live deployed fleet for the first time. The build leg works — a real autonomous service in ~23 minutes on the cluster — but first contact surfaced six cross-service seam bugs the per-repo unit tests never could. That's exactly what the benchmark is for. Here's the honest scorecard, and the verify-leg gap we closed the same day."
date: 2026-06-12 07:00:00 +0000
author: Olaf Freund
---

Two days ago we did an [honest review of the whole suite](/blog/2026/06/12/the-honest-scorecard/)
and the verdict stung in a useful way: the PARR pipeline works, we're ahead on
governance and verification — but we had **published zero numbers**. We'd even
built a four-scenario benchmark harness and never run it.

So Phase 1 of the plan is simply: *prove it.* This is the first field report.

## What we ran

The benchmark drives the full PARR spine against the **live deployed fleet**
(`{ai,p,t,c}factory.freundcloud.org.uk`) — PFactory plans and signs, AIFactory
builds, TFactory verifies, CFactory threads it all by correlation key. The first
scenario is a real one: a **FastAPI API gateway with rate limiting**, built from
a brief, on the cluster, end to end.

## The result that matters

**The build leg works.** AIFactory took the api-gateway brief and produced a
complete, QA-passed service in **~23 minutes** (1,397 seconds) on the deployed
cluster — autonomously, no hand on the wheel. That's the proof point we'd never
actually measured: not "it builds locally," but "it builds *on the running
platform*, start to finish, in a quantified time."

## The result that's more interesting

The very first time we pointed the harness at the live fleet, it failed in
**seven seconds**. And every failure was a **cross-service seam bug** — the exact
class of problem that per-repo unit tests never catch, because locally there's no
Cloudflare, no cold start, no months-old registered project, and no version skew
between services.

Six of them, all found and fixed in a day:

1. **Cloudflare blocked the bot.** The harness's default Python user-agent got a
   `403` from the managed challenge in front of the live services. → send a real
   browser user-agent.
2. **A transient `500`.** A factory cold-started mid-request. → retry `5xx` with
   backoff instead of failing the run.
3. **A `409` on re-run.** The deployed factories register repos under derived
   names, so blindly creating the project conflicted every second run. → reuse
   the existing project by URL or name.
4. **Endpoint drift.** TFactory moved to a new ingest contract in a recent
   release and the harness still spoke the old one. → speak the current API.
5. **A `400` on the verify poll.** TFactory's task endpoint wants the composite
   `project_id:spec_id`; the harness polled a bare id and burned a 30-minute
   timeout waiting on a request that could never succeed. → build the composite
   id.
6. **Tokens and cost read zero.** The usage endpoint is `/token-usage` with
   camelCase totals, not `/usage`. → read the right place.

None of these are embarrassing. They're the *point*. A benchmark that drives four
independent services through real network, real auth, and real version skew is, on
day one, the **cross-service integration test we never had**. It found in an
afternoon the class of bug that had been leaking into production one fix at a
time. That's why Phase 1 also adds a nightly end-to-end PARR run that fails loudly
in the cockpit — so these get caught by a gate, not by a user.

## And we closed the verify-leg gap the same day

The one honest weakness the review flagged in the loop itself: when AIFactory
handed a finished build to TFactory *without* a deploy, it passed the spec and the
signed contract — but **not the code**. TFactory generated exactly the right tests
and had nothing to run them against. Verification was test-plan-driven, not real.

Both halves are now fixed:

- **AIFactory** carries a code reference — `{repo, branch, base_ref, head_sha}` —
  resolved from the build worktree on the no-deploy path, not just when a deploy
  ran.
- **TFactory** *materializes* it: on ingest it clones and checks out the built
  branch (pinning the exact commit) into the spec workspace, so the lanes run
  against the **real build**. A failed clone degrades safely to the old behavior.

That turns TFactory from "tests the right things in theory" into "runs the
declared tests against the actual code" — which is what makes the bounded
handback loop meaningful.

## Where this leaves us

- **Build leg:** proven on the live cluster, ~23 min, quantified. ✅
- **Harness:** six seam bugs fixed; a clean green run is back in flight as this
  publishes, and the public results table updates when it lands.
- **Verify leg:** the code-carrying gap is closed on both sides.
- **Plan leg:** hit a known PFactory emit-idempotency issue under GitHub rate
  limits — already tracked, and the build proceeds without it.

We said we'd prove it in the open — numbers, warts, and all. This is the first
installment. The number we care about next is the full green PARR run: plan →
build → deploy → verify the live deployment → merge, with a time and a cost
attached. That run is cooking.
