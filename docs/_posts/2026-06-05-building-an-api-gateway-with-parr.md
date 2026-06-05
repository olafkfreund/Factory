---
layout: post
title: "From Backstage to verified code: building an API gateway with the Factory PARR pipeline"
subtitle: "One governed unit of work flowing through PFactory → AIFactory → TFactory, watched in the CFactory cockpit"
date: 2026-06-05
author: Olaf Freund
---

We talk about the Factory suite as four products — **PFactory**, **AIFactory**,
**TFactory**, and **CFactory** — but the point was never four tools. The point is one
**governed path** from an idea to a verified change, with a human in the loop only where
it matters. This post walks that path on a deliberately small unit of work: a **simple
FastAPI API gateway**. Everything below is a real run — including the parts that didn't go
to plan, because that's the honest version and it's more useful than a varnished one.

The spine that makes it work is boring on purpose: a shared **correlation key** (the GitHub
issue number) and a normalized **completion event** every service emits. No orchestrator, no
queue — just choreography. That key threads the whole story:

```
pfactory.session → issue #1 → aifactory.task → branch/PR #10 → tests → cockpit
```

## 0. It starts in Backstage

The service already exists. We scaffolded `factory-demo-api-gateway` from a golden-path
**Backstage** template (`python-service`): FastAPI + uv, Pydantic v2, GitHub Actions CI, a
Nix flake, mkdocs/TechDocs, and a pre-wired `catalog-info.yaml`. Out of the box it exposes
`GET /health` and `POST /echo`. We're not here to show Backstage — we're here to show what
happens *after* the repo exists.

## 1. PFactory — plan, then govern

PFactory turns a plain-English brief into a **governed** plan. We handed it a paragraph and
six acceptance criteria — including a strict one:

> Exceeding the rate limit returns HTTP 429 with a correct integer `Retry-After` header.

PFactory decomposed that into an **epic plus eight child tasks** and ran it through four
**review gates**, each scored 0–1 with citations:

| Lens | Score |
|------|------:|
| Architecture | 1.0 |
| Security | 1.0 |
| Best-practices | 1.0 |
| Feasibility | 1.0 |
| **Aggregate** (threshold 0.75) | **1.0** |

This is the part people underestimate. With **live cloud enrichment** on, PFactory scanned
the connected AWS account and *failed the security lens at 0.6* — flagging real
internet-open security groups and a budget overrun — and **refused to let the plan be
approved** until a human signed off. No plan ships ungoverned. Our gateway has no cloud
infra, so evaluated on its own merits the gates go green, a human approves (recorded and
attributable), and PFactory **emits governed GitHub issues**: epic **#1** and children
**#2–#9**, each tagged `handoff:aifactory`. That `#1` is the correlation key for everything
that follows.

## 2. AIFactory — act

AIFactory picked up the governed issue, cloned the repo into an isolated git worktree, and
ran a **planner → coder → QA** pipeline. It decomposed the build into 19 subtasks and
implemented them across 14 files (**+1766 lines**): `app/config.py` (Pydantic settings), a
config-driven `httpx` proxy router, a rolling-window rate limiter that returns
`429` **with a correct integer `Retry-After`**, `GET /health/upstreams`, structured logging,
and pytest suites for each. It opened **[PR #10](https://github.com/olafkfreund/factory-demo-api-gateway/pull/10)**.

**A real cost note (and a fix).** That build ran the 19 subtasks **serially** on
`claude-sonnet-4-6` — ~70 minutes and ~$11.46 / ~18.7M cumulative input tokens. It's
thorough, but the throughput is a problem, so we filed
[AIFactory#376](https://github.com/olafkfreund/AIFactory/issues/376): parallelize
independent subtasks (`workers`), enable prompt caching on the stable context prefix, and
default small specs to `mode:"quick"`. The `/demo` workflow now starts builds in
quick + parallel mode.

## 3. Verify — and an honest detour

TFactory grades tests on **five signals** — coverage, stability, mutation score, lint, and
semantic relevance — so a pass means *meaningful* tests, not a green checkmark. On this run,
TFactory's autonomous lane hit a real bug: its agent CLI fails to import a missing
`qa_loop` module, so test planning never starts
([TFactory#226](https://github.com/olafkfreund/TFactory/issues/226), filed with the
traceback + a CI guard so a missing top-level module fails CI instead of at runtime).

Rather than fake a verdict, we **ran the suite AIFactory generated** against the PR branch:

```
38 passed in 0.68s
ruff: All checks passed!
mypy --strict: Success: no issues found in 9 source files
```

All six acceptance criteria met — including the strict 429 + `Retry-After` behaviour. The
TFactory **handback loop** (failing test → routed back to AIFactory's QA fixer → re-pass) is
the capability we most wanted to show on camera; it's blocked behind #226 and will be the
star of the follow-up once that lands.

## 4. CFactory — review, the whole time

Throughout, the **CFactory cockpit** is the single pane of glass: each service emits a
completion event and CFactory threads them onto **WorkItems**, aggregating spend (tokens and
cost) across services, with an advise-and-confirm copilot that *prepares* an action for a
human to confirm. One honest detail from this run: because we drove AIFactory directly via
its API, its events were keyed by the **task id** rather than epic **#1** — so the cockpit
showed the build, but fully automatic plan→code→test threading under a single key needs each
service's completion webhook pointed at CFactory's ingress. That's a wiring step, documented
in the `/demo` runbook.

## Why this matters

- **Governance is built in, not bolted on** — the plan can't proceed until it passes review and a human approves.
- **Verification means meaningful tests**, not a green checkmark — five signals, including mutation and semantic relevance.
- **The pipeline is honest about itself** — a slow build and a broken module became tracked issues (#376, #226), not hidden corners.
- **One key, one cockpit** ties idea, code, tests, and spend together.

## Reproduce it

The whole run is packaged as a reusable `/demo` command and a `factory-demo` skill —
pre-flight discovery, the PARR drive sequence (with every gotcha we hit), the handback seed,
and the publish steps. Two screencast storyboards accompany this post: **(A)** the PFactory
planning portal, and **(B)** the cockpit + API view of the same run.
