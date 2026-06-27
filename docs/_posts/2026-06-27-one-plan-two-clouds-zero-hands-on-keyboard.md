---
layout: post
title: "One plan, two clouds: the Factory ships a live app to GCP and Azure through its own pipeline"
subtitle: "PFactory plans it, AIFactory builds it, a GitHub Actions runner deploys it, TFactory plays the game and checks the score — and we have the screencast to prove it"
date: 2026-06-27
author: Olaf Freund
---

We set out to answer a deceptively simple question: can the Factory take a plan
written as a GitHub issue and carry it all the way to a **running app on a real
cloud**, tested by a real browser, without a human hand-writing the deploy? Not a
mock. Not a dry run. A live HTTPS endpoint you can click, on two different clouds,
each verified by an automated test that actually plays the game and reads the
scoreboard.

The answer is yes. Here is how the pipeline did it — and the receipts.

## The mission: a tiny game with a real backend

The brief was deliberately ordinary, because ordinary is where the seams show: a
browser **tic-tac-toe** game with a **top-players scoreboard**. A FastAPI backend.
**Redis** for the live leaderboard, **Postgres** for durable scores. Deploy it to a
managed platform — **no Kubernetes**, just serverless containers and managed data.
Then prove it works by playing it.

That last clause is the whole point. Anybody can `terraform apply`. The interesting
part is closing the loop: the same system that planned the work also has to walk up
to the deployed thing and beat it at tic-tac-toe.

## PARR: plan, act, review, repeat — across four services

The Factory is four services that hand work to each other, correlated by a GitHub
issue number:

- **PFactory** ingests the plan, runs it through review lenses, and decomposes it
  into a tracked epic plus child issues — including a **test issue routed to
  TFactory**.
- **AIFactory** picks up the signed contract, spins up an isolated git worktree,
  and drives a coding agent through every subtask and a QA gate.
- A **GitHub Actions runner** stands the infrastructure up with Terraform.
- **TFactory** drives a real headless browser against the live URL and renders a
  verdict.

The handoffs are real network calls between real services. The plan that started as
prose came out the other end as a deployed, tested application.

## Win #1: the planner understands "deploy to a PaaS"

When the plan says "deploy to GCP Cloud Run with Redis and Postgres," PFactory now
reads that intent. A new detection pass resolves the managed-platform target and the
data services from the plan text and writes them onto the contract's deployment
block — `managed_services: [postgres, redis]` — so everything downstream knows this
is a managed-platform deploy, not a Kubernetes one. The review lenses scored the
plan 0.97 once it carried an explicit security posture (public-by-design, validated
inputs, least-privilege identity, secrets only in CI). Gates passed. The plan
emitted.

## Win #2: the deploy artifacts are proven, not guessed

The riskiest thing an AI can do is hallucinate infrastructure. So the consuming side
is **deterministic**: AIFactory scaffolds the cloud's Terraform and the GitHub
Actions deploy workflow from a vendored template pack — the exact templates we have
deployed and tested live — rather than letting a model invent a provider block. When
the target repo already carries good infrastructure, the coder **verifies** it
against the acceptance criteria instead of rewriting it. Boring, on purpose. Boring
is what you want holding a `terraform apply`.

## Win #3: it actually plays the game

This is the part that makes it real. TFactory's browser lane opens the deployed URL,
types a player name, and plays three full games to a win — clicking cells, watching
the win banner fire — then reloads and asserts the **top-players scoreboard** shows
that player at number one. Not a screenshot diff. A semantic assertion against live
state served from Postgres and cached in Redis.

Here is the GCP run, on Cloud Run, after the bot won three games:

![The deployed tic-tac-toe scoreboard on GCP Cloud Run, with TFactoryBot at number one]({{ '/assets/screenshots/parr-clouds/gcp-scoreboard.png' | relative_url }})

A won game mid-flight:

![A completed tic-tac-toe game on the deployed GCP app, win detected]({{ '/assets/screenshots/parr-clouds/gcp-game-won.png' | relative_url }})

## Win #4: same plan, different cloud

Then we did it again on Azure — and the only thing that changed was the deploy
template. GCP got **Cloud Run + Cloud SQL + Memorystore**. Azure got **Container
Apps + Postgres Flexible Server + a Redis sidecar**, because that subscription has no
App Service VM quota and the classic managed Redis is retiring — exactly the kind of
real-world wrinkle that separates a demo from a system. The app image was
byte-for-byte identical; the Redis client just learned to speak TLS when the
environment asks for it.

The Azure app, live on Container Apps:

![The deployed tic-tac-toe game on Azure Container Apps]({{ '/assets/screenshots/parr-clouds/azure-landing.png' | relative_url }})

And the Azure scoreboard, same bot, same verdict:

![The deployed scoreboard on Azure Container Apps, TFactoryBot at number one]({{ '/assets/screenshots/parr-clouds/azure-scoreboard.png' | relative_url }})

Every screenshot above was captured by the test itself, alongside a screencast of
the full play-through, and published back into the TFactory portal as a finished,
tracked run against its repo. The evidence lives where the team already looks.

## The honest part

This was not frictionless, and pretending otherwise would be a disservice. Getting
the pipeline to run clean on a live cluster meant fixing a chain of real gaps:
rolling the new planner and scaffolder onto the packed Nix build image, clearing a
review gate with a genuine security criterion, registering each repo as a project so
the cross-service handoff could resolve it, pinning the coding agent to the model
that is actually installed, reaping a failed build job that had wedged a task in a
phantom "running" state, and clearing stale Terraform state that still believed in
torn-down resources. None of those were new features. All of them were the
difference between "works on my laptop" and "works in the factory." Each one is now
written down so the next run doesn't relearn it.

And one more bit of honesty: because both target repos already held a working app,
AIFactory **verified** the code against the plan rather than authoring it from an
empty directory. That proves the whole pipeline end to end — plan, build-verify,
deploy, test, evidence — but it isn't greenfield code generation. So that is exactly
what we are pointing the Factory at next: an empty repository, and a plan, and
nothing else.

## What it adds up to

One plan, written once, became a live application on two clouds, each one played and
scored by an automated browser, each run tracked with screenshots and a screencast
in the portal — and the only manual nudges left are the deliberate safety gates the
Factory is designed to keep. The loop is closed. The test factory tests the factory's
own output, in production, on the cloud, and tells you whether it won.

Next stop: hand it an empty repo and watch it write the whole thing.
