---
layout: post
title: "Earning the right to run unattended: the hardening behind the AWS demo"
subtitle: "A real OS sandbox, seven autonomous-completion fixes, and more verification surface — the trust work that let one brief reach a live EKS cluster"
date: 2026-06-20
author: Olaf Freund
---

The previous post showed a three-tier app going from a one-paragraph brief to a live AWS
EKS cluster and back to nothing, through the PARR pipeline. That run is only believable
because of a less glamorous body of work that came first: closing the gaps that, in earlier
runs, quietly required a human to step in. This post is about that hardening — the
unglamorous trust work — because a pipeline you can leave alone is the whole point.

## The honest starting position

An earlier flagship run worked end to end, but it needed a human at five separate moments:
an expired model token that produced an empty build, a provider CLI that hung and escalated,
a build with passing tests but no runnable entrypoint, a missing test dependency, and a
verify environment that couldn't run the generated tests. Separately, there was one
credibility-critical security gap: the coding agent ran with broad permissions and **no
verified OS boundary**. You cannot honestly say "trust by construction" with that open.

So before chasing a bigger demo, we closed those.

## A real OS sandbox for the agent

The agent now executes its commands inside a **bubblewrap OS sandbox**: the task worktree is
the only writable path, everything else is read-only, with private IPC/UTS namespaces and a
tmpfs. The interesting part was making it real **on the cluster**. The earlier sandbox mode
needed a privilege an unprivileged Kubernetes pod does not have, so it had silently fallen
back to a passthrough in production. We made the default unprivileged-safe (keeping the host
PID namespace with a read-only `/proc`), turned it on by default in the chart, and proved it
inside the live pod: an attempt to write outside the worktree is rejected, and a host secret
outside the mount is unreadable. The two escape tests that used to be skipped are now live
assertions. The command allowlist and secret-scrub remain as defense in depth — not the
perimeter.

## Seven fixes so a build can finish itself

The autonomy gaps became a single tracked piece of work, shipped as small changes:

- **Auth pre-flight** — a cheap, generation-free credential probe before each build, so an
  expired token fails fast with a named error instead of producing an empty build.
- **A non-expiring key for headless runs** — opt-in, so unattended runs don't depend on an
  interactive token expiring mid-flight.
- **Declare your test dependencies** — the coder now treats a used-but-undeclared package
  (the classic `TestClient` needs `httpx`) as a hard requirement.
- **QA smoke-boot** — verification now boots the artifact and probes it, so "tests pass but
  nothing runs" is a rejection, not a pass.
- **Provider bounded-retry and failover** — a stalled provider now fails over to the next in
  a chain within a deadline, instead of retrying the same hung process and escalating.
- **qa_fixer auto-repairs mechanics** — a missing entrypoint or dependency is repaired
  directly rather than escalated to a human.
- **A safety-net commit** — agent-written files are committed before any post-run bookkeeping
  can abort, so work is never lost to a teardown.

Each one removes a place a human used to have to stand.

## More ways to verify

We also widened what the verifier can check: **Selenium, Cucumber, and Karate** joined the
framework registry alongside Playwright, Cypress, Jest, Pytest and the rest, with their runner
images now built and published to the registry and a real lane run proving they execute. And
we kept ourselves honest about the edges: the verify leg's test *generator* still thrashes on
hard assertions and has no Go support yet — both filed, both visible, neither hidden.

## The payoff

With the boundary enforced and the autonomy gaps closed, the AWS run in the previous post is
what "unattended-capable" actually buys you: a brief became a tested, containerised three-tier
service on real managed infrastructure, and the only human steps left were the genuinely
human ones — reviewing the plan, and the handful of cloud-engineering fixes any first deploy
needs. That is the bar we hold the Factory to: not a flawless demo, but a legible pipeline you
can increasingly leave to run, with every weakness named out loud.
