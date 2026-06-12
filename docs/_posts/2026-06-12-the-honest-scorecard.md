---
layout: post
title: "The honest scorecard: we reviewed all four factories against the market"
subtitle: "A full code review of PFactory, AIFactory, TFactory and CFactory against our goals and against Devin, Factory.ai, OpenHands and the cloud agents. The verdict: the spine is closed and we're ahead on the axis that matters — but we have zero published proof, zero design partners, and one security item we refuse to hand-wave. Here's the plan."
date: 2026-06-12 12:00:00 +0000
author: Olaf Freund
---

This week we stopped and did something uncomfortable: a full review of every
factory — the code, the seams, the open issues — against our stated goals and
against the 2026 market. Not the demo-day version. The honest one.

## What the review found

**The PARR spine is closed.** Plan → signed Task Contract → trusted-plan build →
deploy to real AWS → verify the live endpoints → bounded handback → PR endgame →
completion events → cockpit. Every cross-factory adoption epic (Task Contract
v2, completion-event delivery, the verify leg) is shipped and closed. PFactory
signs with HMAC and AIFactory verifies byte-for-byte. TFactory's planner
auto-runs on ingest and tests against the deployed URL. CFactory threads all of
it into one WorkItem timeline with a tamper-evident audit chain.

**The cores are solid.** AIFactory: 313 test files, eight providers behind one
abstraction, parallel waves in isolated worktrees, near-zero TODO density.
PFactory: the full governance pipeline — live-cloud cost and IAM enrichment,
cited review gates, honour-documents — tested end to end. TFactory: five
verification lanes, five signals per verdict, durable outbox delivery. CFactory:
seven views, idempotent event ingest, advise-and-confirm control, zero open
issues.

**The bugs all lived at the boundaries.** Nearly every fix of the past month was
a seam bug: completion side-effects that never fired, the QA-fixer racing its
own re-review, contracts rejected over payload shape, MCP proxy 500s. Each was
fixed within a day — but each was found by use, not by a gate. Our unit-test
posture is excellent; our risk profile is cross-service. That mismatch is now a
tracked piece of work, not a shrug.

## What the market told us

The 2026 landscape validated the bet more than we expected. Code generation is
commoditizing — the benchmark wars between Droid, Devin, OpenHands and the lab
CLIs are a race we deliberately aren't in. Meanwhile the industry's own surveys
say the quiet part: most organizations can *monitor* their agents but can't
*stop* them, only a minority of developers trust agent output, and the EU AI
Act's high-risk rules land on **August 2, 2026** with logging, human-oversight
and audit-trail obligations. Security vendors spent the spring launching agent
governance products. The bottleneck everyone now names — verification, trust,
auditability — is the thing we've been building for a year.

On that axis, nobody in the comparison set has what the suite has: a pre-code
feasibility and governance gate, an independent multi-lane verification leg that
tests the *deployed* service, deploy-then-verify on real infrastructure, an
HMAC-anchored audit chain, and a cockpit that can actually pause the fleet. And
because we wrap coding agents rather than compete with them, Droid topping
Terminal-Bench isn't a threat — it's a candidate provider.

## Where we're honestly behind

Three places, and none of them are code we haven't written:

1. **Proof.** Factory.ai markets benchmark numbers relentlessly. We built a full
   PARR benchmark harness — four scenarios, four provider configs — and have
   never run it. Our strongest evidence is sitting on a shelf.
2. **Customers.** Zero design partners. Our own roadmap gates Horizon 1 on
   finding 3–5, and the pricing page is still illustrative.
3. **One security item.** The agents still run with an effectively bypassable
   command allowlist instead of a real OS sandbox. Ten of eleven findings from
   the security audit are closed; this is the eleventh, and you cannot sell
   "trust by construction" while it's open.

## The plan

All of it is now tracked in one epic:
[**Factory#42 — Make it great: prove, harden, and sell the PARR spine**](https://github.com/olafkfreund/Factory/issues/42).

- **Phase 1 — Prove it.** Run the benchmark matrix and publish the numbers:
  outcome, time-to-verified-PR, token cost, handback cycles — per scenario, per
  provider. Plus a nightly end-to-end PARR regression that exercises every seam
  and fails loudly in the cockpit, so boundary bugs get caught by a gate instead
  of a user.
- **Phase 2 — Trust.** Close the real OS sandbox. No caveats in the security
  story.
- **Phase 3 — Adversarial validation.** The handback loop and the auto-feedback
  fix loop get proven on deliberately broken builds, and TFactory verifies the
  *built branch*, not just the signed contract.
- **Phase 4 — Sell it.** An EU AI Act audit-pack export, pulled forward from
  Horizon 2 — one click, one self-contained archive a compliance reviewer can
  read without access to our systems. That plus the benchmark numbers is the
  design-partner pitch.
- **Phase 5 — Ops.** Zero-downtime deploys, idempotent emits, the legacy
  envelope cutover. The unglamorous list.

The ordering is deliberate: proof first, because it's days of work and the
highest leverage; then the one trust blocker; then adversarial validation of the
loops we just shipped; then selling with the artifacts the first three phases
produce. Expansion waits until design partners exist.

We spent a year building the part of the agentic SDLC that doesn't commoditize.
The review says it works. Now we prove it in public.
