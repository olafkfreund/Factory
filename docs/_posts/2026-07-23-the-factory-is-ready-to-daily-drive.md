---
layout: post
title: "The Factory earns its keep: ready to daily-drive"
subtitle: "A full-fleet test pass, a live plan-build-verify run on real infrastructure, and the features that got us here: baked toolchains, cached code graphs, per-spec isolation, and verdicts you can trust."
date: 2026-07-23 12:00:00
author: Olaf Freund
---

For months the claim has been that the Factory takes a plain issue and returns a
tested pull request with no human in the loop. This week we stopped asserting it
and measured it, end to end, against the deployed fleet. This post is the
readiness report and a tour of the features that made it possible.

The shape is still PARR: **P**lan, build, verify, report. PFactory plans against
your actual code, AIFactory builds, TFactory verifies with real tests, and
CFactory watches the whole line.

## What we verified

Three things had to hold at once for "daily driver" to mean anything: every
service's own test suite has to be green, the live fleet has to be healthy, and a
real task has to flow all the way through the pipeline and produce a genuine
verdict.

Every repository's suite is green, with no failures: PFactory (over five thousand
backend and web-server tests plus its critical lane), AIFactory (over five
thousand across three suites), TFactory (over five thousand backend, web-server,
and critical), and CFactory (backend, frontend, and a clean production build).
The only tests that do not run locally are the ones that need a live Redis, an S3
endpoint, or a sandbox — those run in CI where those services exist.

The live fleet answers on every service, authenticated, through the edge. Our
cross-service seam gate drives the deployed pipeline and asserts at each boundary
in turn: reachability and auth, the plan-leg ingest contract, the verify-leg
ingest contract, and the cockpit API. All green.

Then the real proof: we handed the pipeline a plain request to add a health
endpoint, and it planned, wrote the code, wrote a test, and ran that test to
confirm — an end-to-end build on the live cluster that reached a terminal
success with a correct, tested diff. Not a fixture. A running pipeline producing
working software.

## The features that got us here

**Baked toolchains.** The build and verify images used to install their agent
CLIs at pod start over the network. On a slow registry that stalled rollouts for
minutes and stranded in-flight work. Every provider CLI is now baked into the
image, so a pod is ready the moment it schedules. No per-pod fetch remains
anywhere in the fleet.

**Cached code graphs.** AIFactory can hand the coding agent a scoped map of the
repository instead of making it read blindly, and an A/B measured a meaningful
reduction in input tokens with no loss in quality. The graph is now cached in
object storage, keyed by repository and commit, so a per-task job reuses it
instead of rebuilding it. The build itself is token-free; caching makes the tool
practical at scale.

**Per-spec isolation.** Each verification spec now runs in its own git worktree.
Two specs verifying the same project no longer fight over one checkout, which was
a subtle source of a verifier reading the wrong tree. We caught this working live
during the readiness run: a probe branch could not be deleted because its own
task worktree still held it. That is the isolation doing its job.

**Verdicts you can trust.** A green checkbox is worthless if the test would pass
even with the feature removed. Every accepted test is mutation-checked: we break
the code under test and confirm the test goes red. Verdicts carry stability,
mutation, semantic, and CI-parity signals, not just a pass count.

**Planning that reads your code.** PFactory clones the target and plans against
the symbols that actually exist, informed by the deployment target and any
project constitution or SpecKit assets it finds. The plan is about your code, not
a guess from the issue text.

**Security hardened where it counts.** Path-traversal barriers across the plan
service, SSRF guards on outbound URLs, and custom static-analysis queries that
recognize our own sanitizers so the scanner stops crying wolf and starts catching
the real thing.

## The honest caveat

The readiness run exercised planning, coding, and the coding agent writing and
running its own tests in one continuous flow. The independent verification leg —
TFactory generating and committing its own tests to a real verdict — is proven on
real repositories in prior runs and validated here at the health, contract, and
full-suite level. Supervised daily-driver use is ready now. The remaining work is
throughput and polish, not correctness.

## One bug, found by the gate

Fittingly, the readiness gate caught a real defect: it misread one service's
project-list response shape and reported no project where one existed. That is
exactly the class of boundary bug per-repo unit tests cannot see, and exactly why
the seam gate exists. Fixed, and the fixed gate is what produced the green run.

The Factory is not a demo any more. It is a tool we are ready to use on our own
work, with a human reviewing the design and the diff. That was the whole point.
