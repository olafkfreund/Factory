---
layout: post
title: "Only claim it when you can prove it"
subtitle: "Three weeks of hub work in one sentence: we stopped trusting prose. Canonicals are registered in drift gates, protection is code, watchdogs catch the pins that rot, and a new standards rule says a control that would look identical having done nothing is not evidence."
date: 2026-08-10 09:00:00
author: Olaf Freund
---

One of our pull-request titles from the last three weeks reads: *"export OTLP
traces, and only claim it when a span lands."* It appears, almost word for word,
in four different repositories. That sentence turned out to be the theme of the
whole period, and this post is about what it cost us to learn it and what we
built once we had.

The Factory hub does not run anything. It holds the contracts, the shared code
every service vendors, the standards, and the gates that keep those honest. When
the hub is wrong, four services are quietly wrong with it.

## The defect that has a name now

On one day in early August, three people working on unrelated issues each hit the
same shape and filed it as three separate bugs. Laid side by side there were
seven instances, and they were one defect:

> A control reports whether it **ran**, when the question is what it
> **produced**. The absence looks exactly like success.

A signature check that could not read the registry reported `unverified image` —
indistinguishable from an unsigned image. An admission webhook that was skipped
during a rollout reported an admit. A policy-test case that evaluated nothing
scored as a pass. A commit that never reached the branch showed as merged with
green CI.

The severity ordering was set by visibility rather than by risk. The one that
failed loudly was fixed the same day; the six quiet ones sat.

That is now **rule 4.10** in the shared coding standards, next to rule 4.7 ("a
gate that cannot run must fail, never pass"), which is its other half. 4.7 covers
a gate that could not reach its input. 4.10 covers one that ran fine and measured
the wrong thing. The rule carries a table of eight instances naming, for each,
what not to trust and what to read instead — because the memorable question is
cheap to quote and expensive to apply, and a rule with no per-instance mapping is
quotable and unactionable.

We got the eighth instance four days after writing the rule, which is the best
argument for it we could have asked for: a CI step that ran
`curl -sSfL "$SERVER/cli/install.sh" | sh` and reported success having installed
nothing. GitHub Actions runs `run:` under `bash -e` with no `pipefail`, so curl's
failure is discarded and `sh` reading empty stdin exits zero. The path was a 404.
The step was green for as long as anyone had been looking at it.

## Shared code is now registered, not just shared

The hub owns canonical implementations that the services vendor. The failure mode
is not that a copy diverges — it is that a copy diverges and nothing says so.

Over three weeks we registered the remaining unguarded canonicals in the
verification-core drift gate: the Job dispatch rules, the job-side OpenTelemetry
bootstrap, the planning-card schema, `tsconfig.base.json`, and the
factory-contracts pin. Each registration is byte-exact and fails closed.

Two of those needed more than a byte comparison. A service had forked a hub file
and left a citation in the comment explaining why — structurally invisible to a
diff of file contents against a pin, because the pin had moved. So we added a
watchdog for pins that gate against a canonical that has since changed, and a
second one that alerts when a fix has been merged to `dev` but is missing from
the `main` that is actually deployed.

## Branch protection is code, and the gate that called itself blocking now blocks

`scripts/apply_branch_protection.sh` declares the intended protection for every
repository and every protected branch, and **checks by default**. Applying needs
an explicit `--apply`, because a tool whose default action is "silently overwrite
production configuration" is the wrong shape for something CONTRIBUTING.md tells
a stranger to run after a fresh clone.

Three things landed on it. The default branch is now part of the declared intent,
because the default branch *is* the branching model. A drift gate whose own
header had called it "blocking" since February — while it was required nowhere —
is now actually required. And commit signing arrived as an opt-in `--signatures`
mode that is dry-run by default and prints a per-repository signer pre-flight,
because enabling required signatures rejects the next unsigned push from every
identity, including the deploy bot.

That last one has an honest gap attached. The four-eyes segregation-of-duties
half needs two distinct humans, and this is a single-maintainer fleet. Rather
than ship a check that can never go green — which trains everyone to ignore a red
check — it is documented as absent and tracked. An unmet control recorded as
unmet is an audit finding; an unmet control recorded as met is a misstatement.

## Traces that cross the Job boundary

Work runs in Kubernetes Jobs, and a Job is a new process with a new context. A
trace that stops at the dispatch boundary tells you a Job started, not what it
did. The dispatch path now carries trace context across that boundary and the
job-side bootstrap is a hub canonical, so all four services emit from inside the
Job rather than around it — and each service only claims tracing works when a span
actually lands in the collector.

## Compliance, with the measurements attached

The compliance program produced its policy set earlier in the summer. This month
it started producing evidence.

The disaster-recovery runbook is the clearest example. The backups existed and
had run nightly for weeks. Nobody had ever restored one. So we did: 52 of 52
tables across all five databases, roles intact, zero errors, every row count
matching except one row written after the dump was taken — which is recovery
point objective made visible, not data loss. Restore took 17 seconds.

The drill earned its keep by failing first. `pg_dumpall` carries the source
cluster's role definitions, so partway through a restore an `ALTER ROLE ...
PASSWORD` replaces the target's password with production's, and every subsequent
connection in the same restore fails. The restore stops **after** the databases
have been dropped and recreated, leaving a half-rebuilt cluster, and it presents
as an authentication error that reads like a misconfiguration. That instruction
existed nowhere, because nobody had run it.

It also found something worse than the gap it was closing. The nightly dumps
upload into the same object store that sits on the same node and the same storage
class as the database they protect, and nothing backs that store up. There is no
second failure domain in the cluster at all — the RWX storage class is served by
an in-cluster provisioner whose own export is a node-local volume. One host loss
takes the database, every backup of it, and the audit evidence together. Fixing
that needs somewhere off the box, which is a decision about hardware rather than
code, and it is on the issue rather than quietly absent from it.

While reconciling that, we found a compliance document asserting "no backups
exist today". It had concluded that from *"the only CronJob in the repo is
cred-broker"* — searching the hub repository, while every CronJob in the fleet
lives in the GitOps repository. Absence proved in the wrong place. The correction
carries the methodology note, because a control matrix claiming a control does
not exist sends the next person to build what is already there.

## What this adds up to

Not a feature list. A change in what counts as done.

Three weeks ago a gate was done when it was written. Now it is done when someone
has watched it fail on purpose, and when the thing it reports on is the artefact
rather than its own exit code. That is slower, and it is the only version of this
work that survives contact with an auditor, an outage, or a Tuesday.
