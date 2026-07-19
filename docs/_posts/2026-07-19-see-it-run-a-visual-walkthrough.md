---
layout: post
title: "See it run: a visual walkthrough of one autonomous build"
subtitle: "The same live run, in pictures and one continuous video. A plain issue in, a tested pull request out, across four portals and one cockpit."
date: 2026-07-19 12:30:00
author: Olaf Freund
---

We keep saying the Factory takes a GitHub issue and produces a tested pull
request with no human in the loop. This post shows it. Every image below is a
live, MFA-authenticated capture of the running portals, taken minutes after a
real run on 2026-07-19. The video at the end is one continuous walkthrough of all
four portals with that run's own data.

The shape is PARR: **P**lan, build, verify, report. PFactory plans, AIFactory
builds, TFactory verifies, and CFactory watches over the whole line.

## Plan: the plan is about your code, not a guess

PFactory does not plan from the issue text alone. It clones the target repo
read-only and builds a RepoMap — the languages, frameworks, package managers, and
infrastructure present, pinned to an exact commit — classifies the change
(`change_mode = modify`), grounds the plan in the repository's own delivery
history, and runs a house-standards and Backstage enrichment pass. It scans the
issue for injection, and scores review lenses for feasibility and architecture,
both 1.0 out of 1.0 on this run. The result is a signed contract about this
specific codebase.

![PFactory code-aware planning]({{ '/assets/blog/2026-07-19/plan-planning.png' | relative_url }})

## Build: every task gets a throwaway factory floor

AIFactory keeps no long-lived workspace. Every task builds inside its own
disposable Kubernetes Job, refreshed to the current tip of main, then opens its
own pull request. When the Job finishes, it is gone — nothing leaks between tasks.
Underneath sits a tamper-evident test-evidence gate: a green "tests pass" checkbox
is impossible to produce unless a real test runner actually executed. The build
cannot mark its own homework complete.

![AIFactory task board]({{ '/assets/blog/2026-07-19/build-tasks.png' | relative_url }})

And you can watch the agents work. Every running agent streams its terminal into
the portal and the cockpit as it goes — spawn several and watch them side by side.

![AIFactory live agent terminals]({{ '/assets/blog/2026-07-19/build-terminal.png' | relative_url }})

## Verify: an assurance level computed from the truth

TFactory generates tests, runs them in a per-task Nix sandbox, and grades them on
five signals: coverage, stability, mutation, semantic relevance, and CI parity.
From those it assigns a Verification Assurance Level (VAL) — recomputed from what
actually happened, never asserted. A failing lower lane caps the ceiling; an
untested dimension is reported as an honest gap, not a silent pass. Mutation
testing on the hard lane exists to prove the assertions actually bite.

![TFactory verification workspace]({{ '/assets/blog/2026-07-19/test-tests.png' | relative_url }})

For the featured task — a `clamp(value, low, high)` helper — the verdict was:
**Verified to VAL-1, 5 of 5 acceptance criteria met, 9 tests generated and kept,
0 rejected, the mutation probe killed, confidence 0.96 across 3 stable runs.**
VAL-2 and VAL-3 were correctly reported as `not_run` — no api, integration, or
browser lane applies to a pure function, and it does not pretend otherwise. For UI
work, the same verifier captures screenshots, recordings, and diffs.

![TFactory visual-inspection reports]({{ '/assets/blog/2026-07-19/test-visual.png' | relative_url }})

## The moment the tests refused to lie

This is the part we are proudest of. Minutes before the clean clamp run, we drove
a `slugify` helper. It built and looked fine — but one of twelve test verdicts
failed on a unicode edge case. The never-overclaim gate **capped the run at
VAL-0** and automatically filed a handback to fix it. It refused to certify a
build with a failing test. That is the capability, not a bug. A system that will
tell you "no" is the only kind you can trust when it says "yes."

## Cockpit: one control tower over the whole line

CFactory threads plan, build, and verify into a single correlation you can watch
live. The pipeline strip counts work at each stage; the event feed shows this
run's real completions; the live agent terminals surface here too, alongside
anomalies, token and cost, and a human-review queue.

![CFactory Mission Control]({{ '/assets/blog/2026-07-19/cockpit-mission-control.png' | relative_url }})

![CFactory pipeline board]({{ '/assets/blog/2026-07-19/cockpit-pipeline.png' | relative_url }})

## Watch the whole thing

One continuous walkthrough of all four live portals — plan, build, test, cockpit —
carrying this run's own data:

<video controls preload="metadata" style="width:100%;max-width:960px;border-radius:8px;border:1px solid #2b2820" src="{{ '/assets/blog/2026-07-19/factory-walkthrough.mp4' | relative_url }}">
  Your browser does not support embedded video.
  <a href="{{ '/assets/blog/2026-07-19/factory-walkthrough.mp4' | relative_url }}">Download the walkthrough</a>.
</video>

## Built for agents and humans to share

Every service is reachable three ways — a REST API, an MCP server, and installable
skills — so an agent operates the Factory exactly as a person does in the portal.

![AIFactory MCP surface]({{ '/assets/blog/2026-07-19/agent-mcp.png' | relative_url }})

The services also register as Backstage components. As of this run the live catalog
holds all five — `tfactory` at production lifecycle, `pfactory`, `aifactory`, and
`cfactory` as experimental services, and `factory` as documentation — and the
planner pulls catalog and best-practice knowledge from Backstage during its
enrichment pass.

## One honest caveat

The run also surfaced a real gap: the verify verdict is computed correctly, but its
automatic posting back onto the pull request is gated by a fix we have now tracked
as an issue. We name it rather than hide it. The Factory found the last rough edge
in its own feature — and said so. That is exactly the posture we want.
