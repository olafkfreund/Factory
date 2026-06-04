---
layout: post
title: "One factory, four products: why we split the SDLC into a chain"
subtitle: "PFactory plans, AIFactory builds, TFactory verifies, CFactory watches. Here's why that's a family, not a monolith."
date: 2026-06-04
author: Factory Team
---

The industry narrative for 2026 is the "autonomous software factory" — agents that
take an idea to production with humans in the loop only where it matters. Most
attempts build that as one big monolith. We bet on the opposite: **a chain of
focused, composable products**, each excellent on its own, each handing off to the
next.

## The PARR loop, as products

- **[PFactory](https://pfactory.freundcloud.com/) — Prepare.** Governed planning,
  grounded in your *real* infrastructure (cloud, Backstage, wikis), with review
  gates that cite their evidence and a human-approval gate before anything ships.
- **[AIFactory](https://aifactory.freundcloud.com/) — Act.** Spec-first execution
  in isolated worktrees, multi-provider, enterprise-grade, able to delegate the
  coding phase to other agents.
- **[TFactory](https://tfactory.freundcloud.com/) — Reflect.** Autonomous tests
  graded on a five-signal verdict — coverage delta, stability, mutation, lint,
  semantic relevance — so you get tests you can *trust*.
- **[CFactory](https://github.com/olafkfreund/CFactory) — Review.** The control
  tower: one cockpit over all three, with an agentic copilot that explains and
  steers.

## Why a chain beats a monolith

Three reasons. **Adoption:** you can take TFactory for QA, or PFactory for governed
planning in front of any coding agent, without buying the whole stack. **Focus:**
each product competes on its own merits — and TFactory's verdict rigor or
PFactory's governance is far sharper than a generalist monolith. **Trust:** the
boundaries between products are exactly where human-in-the-loop gates belong.

## The connective tissue

A chain is only as good as its handoffs. The piece we're building now is the
**spine**: a shared correlation key (the humble GitHub issue number) threading
`plan → code → branch/PR → tests`, a normalized completion-event schema, and a
clean port map. Once that's in place, CFactory can show — and steer — the whole
pipeline from one place.

That's the work. Follow it on the [roadmap](/roadmap/) and across the
[repos]({{ site.repo_url }}).
