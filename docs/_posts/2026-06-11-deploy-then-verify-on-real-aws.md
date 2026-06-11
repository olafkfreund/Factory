---
layout: post
title: "Watch it deploy: from a CLI to a live, tested API on real AWS — and torn down"
subtitle: "We closed the last gap in the PARR verify leg. This screencast shows the Factory taking services from a command line, deploying them to real AWS App Runner with deterministic Terraform, proving the live API works, running the acceptance tests against the live endpoints, and tearing everything down — cost-guarded, scoped, repeatable."
date: 2026-06-11 13:30:00 +0000
author: Olaf Freund
---

The open question from the [last field report](/blog/2026/06/11/the-first-gemini-parr-run/)
was the verify leg: TFactory generated exactly the right tests, but had no
running target to point them at. Tests with no deployment aren't verification.

So we built **deploy-then-verify**: after the build, the Factory ships the
services to **real AWS**, proves the live API works, runs the acceptance tests
against the live endpoints, and tears it all down. Here it is, end to end:

![Deploy-then-verify on real AWS](/assets/demos/parr-deploy-then-verify.gif)

## What you're watching

A single CLI conductor, against a real AWS account (`eu-west-2`):

1. **Render deterministic infrastructure.** The Factory generates the App Runner
   Terraform — not an LLM guess. Every resource is tagged `factory-ephemeral`
   and `spec_id`, and `destroy.yml` is emitted *with* `deploy.yml`, never without.
2. **Create ECR repos + IAM role**, build the two FastAPI services
   (a tic-tac-toe frontend and an auth-protected scoreboard), and push the images.
3. **`terraform apply` → AWS App Runner** stands up two live HTTPS services.
4. **The live API works:** `POST /move` returns `win:X`; `POST /scores` without a
   bearer token returns `401`. Real requests to real endpoints.
5. **Verification against the live endpoints:** the acceptance-criteria tests —
   move logic, win detection, auth rejection, leaderboard sort — run against the
   deployed URLs (via `TFACTORY_TARGET_URL`, exactly how TFactory resolves a
   deployed target). **6 passed.**
6. **Teardown.** `terraform destroy` — 6 resources gone, App Runner empty. We
   verified the account's *existing* repos were untouched; the `factory-*`
   naming + `factory-ephemeral` tag mean teardown can never reach beyond what the
   Factory created.

## Why the teardown matters most

Real provisioning is only safe if it reliably un-provisions. The teardown is the
load-bearing guard here, so it's built three ways: `destroy.yml` always ships
with `deploy.yml` (there's no code path that produces one without the other), the
deploy orchestrator fires teardown automatically on *any* failed or timed-out
deploy, and a tagged sweeper catches anything that ever slips through. In the
run above, six resources came up and six came down — and the account's existing
infrastructure never moved.

## What this unlocks

The PARR loop now has a real verify leg: **plan → build → deploy → test the live
deployment → tear down → merge**. The deployment engine is deterministic and
cost-guarded; the tests run against software that is actually running, not a
diff. That's the difference between "the tests would pass" and "the deployed
service passes the tests."

Next we wire this deploy stage into the autonomous pipeline so it runs without a
hand on the CLI — and let the reviewed PR auto-merge on a green live verification.
The hard part — real cloud, proven safe to tear down — is done.

*Every step above is real: real AWS account, real App Runner endpoints, real
teardown. The run took ~6½ minutes; the recording is time-compressed for viewing.*
