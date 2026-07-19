---
layout: post
title: "A factory that builds software: one live run, end to end"
subtitle: "A plain GitHub issue went in and a tested pull request came out, with no human in the loop. Here is the run, the four stages, the real verdict numbers, and the moment the tests refused to lie."
date: 2026-07-19 12:00:00
author: Olaf Freund
---

Factory is four cooperating services that behave as one delivery pipeline:
PFactory plans, AIFactory builds, TFactory verifies, and CFactory watches. We
call the shape PARR: Plan, build, verify, report. The claim we care about is
narrow and testable. You file a GitHub issue, and the fleet produces a tested
pull request, unattended. On 2026-07-19, against a remote k3d cluster we call
"factory", we did exactly that and watched every stage.

## The run

A plain issue asked for a `clamp(value, low, high)` helper on a demo repository.
No human wrote the plan, the code, or the tests. PFactory planned it, AIFactory
built it inside an ephemeral Kubernetes Job and opened its own pull request
(aifactory-demo PR #387), TFactory generated and ran the tests, and the verdict
came back graded. Alongside it we drove a second, code-aware planning session
(session 003) for a `slugify` helper, which is where the most interesting thing
happened. More on that below.

## Plan: the plan is about your code, not a guess

PFactory does not plan from the issue text alone. It clones the target repo
read-only and builds a RepoMap: the languages, frameworks, package managers, and
infrastructure present, pinned to an exact commit. It classifies the change
(`change_mode = modify`), grounds the plan in the repository's own delivery
history, and runs a house-standards and Backstage enrichment pass so the plan
inherits the catalog's knowledge of the service. It runs an injection scan over
the issue, and it scores review lenses for feasibility and architecture, both
1.0 out of 1.0 on this run. The output is a signed contract about this specific
codebase.

## Build: every task gets a throwaway factory floor

AIFactory does not keep a long-lived workspace. Every task builds inside its own
disposable Kubernetes Job, refreshed to the current tip of main, then opens its
own pull request. When the Job finishes, it is gone. Nothing leaks between tasks.

Underneath the build sits a control we lean on hard: a tamper-evident
test-evidence gate. A green "tests pass" checkbox is impossible to produce unless
a real test runner actually executed. The build cannot mark its own homework
complete by asserting success; it has to show the run.

## Verify: five signals and an assurance level computed from the truth

TFactory generates tests, runs them in a per-task Nix sandbox, and grades on five
signals: coverage, stability, mutation, semantic relevance, and CI parity. From
those it assigns a Verification Assurance Level. The number is recomputed from
what actually happened, not asserted. A failing lower lane caps the ceiling. An
untested dimension is reported as an honest gap, never a silent pass. Mutation
testing on the hard lane exists to prove the assertions actually bite.

For the clamp run the verdict was: Verified to VAL-1, 5 of 5 acceptance criteria
met, 9 tests generated and kept, 0 rejected, the mutation probe killed, and
confidence 0.96 across 3 stable runs. VAL-2 and VAL-3 were correctly reported as
`not_run`, because no API, integration, or browser lane applies to a pure
function. It did not invent coverage it could not earn.

## The centerpiece: tests that refuse to lie

Minutes before the clean clamp run, the `slugify` build finished and looked fine.
Then TFactory ran its verdicts, and the code failed one of twelve on a unicode
edge case. The VAL gate did not round up. It capped the build at VAL-0 and
auto-filed a handback to fix it. It refused to certify a build that had a failing
test.

This is the part worth pausing on. Most automated coding demos are optimized to
succeed on camera. The interesting behavior is not the success; it is the
refusal. A pipeline that will not certify its own broken output is worth more
than one that always turns green, because only the first kind can be trusted when
you are not watching. The failing verdict was the capability working, not a bug.

## The honest gap we found in ourselves

The run surfaced one real rough edge. The verify verdict is computed correctly,
but its automatic post back onto the pull request is currently gated by a fix we
have now tracked as an issue. So the verdict is right; the last mile of threading
it onto the PR is not yet automatic in every path. We are naming it here rather
than editing it out of the story. The factory found the last loose edge in its
own feature, and it said so. That is the same honesty the VAL gate enforces,
applied to us.

## Why this shape

Two design choices carry the weight. First, every service is agent-native: each
exposes a REST API, an MCP server, and installable skills, so an agent operates
the factory the same way a person does. Second, all five components are registered
as Backstage catalog entries, and the planner reads that catalog during
enrichment, so plans are grounded in the same source of truth the humans use.
CFactory threads plan, build, and verify into a single correlation with a live
pipeline strip, an event feed, anomalies, token and cost accounting, and a
human-review queue, so the whole run is one object you can watch, not four logs
you have to reconcile.

A live walkthrough of all four portals is available on request.

We are not claiming the factory writes every kind of software unattended. We are
claiming something smaller and more durable: on this run, a plain issue became a
tested pull request with no hands on the keyboard, and when one build was wrong,
the system said so instead of shipping it. That is the bar we are building to.
