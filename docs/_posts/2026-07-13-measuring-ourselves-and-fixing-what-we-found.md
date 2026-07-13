---
layout: post
title: "Measuring ourselves against the field, then fixing what we found"
subtitle: "A July 2026 cycle report: the first external benchmark number, the honest failure it exposed, and the cost-aware routing we shipped and proved as a result."
date: 2026-07-13 12:00:00
author: Olaf Freund
---

Factory is the hub of a four-service software factory: PFactory plans, AIFactory
builds, TFactory verifies, and CFactory watches. This repository is not one of
those services. It is the place where the shared contract lives: the RFCs, the
Task Contract schema, the benchmark harness, and the standards every service
holds itself to. This cycle was about using that hub for what it is for, which
is to point the whole fleet at a hard question and then act on the answer.

## Why: a demo is not a product

It is easy to make an autonomous coding pipeline look good on a curated example.
It is much harder to say, in a number a stranger can reproduce, how often it is
actually right. Until this cycle we had no external benchmark for our scaffold.
We had confidence, which is not the same thing. So the first job was to stop
grading our own homework.

## What: an external number, honestly reported

We built a driver that pushes a real SWE-bench Verified task through the live
PFactory to AIFactory to TFactory pipeline and scores the result with the
official harness, never with our own judgment. The first 50-task baseline
resolved 38 percent overall. That headline number matters less than what sat
underneath it: when the pipeline emitted a scorable patch, it was right about 79
percent of the time, but 22 of 50 runs produced no patch at all. Almost half of
our failures were not wrong answers. They were silence.

That is exactly the kind of finding a benchmark is supposed to surface, and
exactly the kind a marketing slide would bury.

## How: the contract turns a finding into fleet-wide fixes

Because the fleet is built around a shared contract rather than four independent
tools, a diagnosis in one place becomes a fix everywhere. Two threads came out
of the baseline:

- The empty-patch gap was root-caused to a coder session that could stall on
  startup and burn silently to the build deadline. AIFactory now defends against
  it three ways. That work is written up on the AIFactory blog.
- The benchmark also gave RFC-0014, our cost-aware model routing spec, something
  it never had before: a measurement to justify it. We promoted the spec to a
  concrete per-stage routing contract, then implemented and measured it.

The routing result is the one to hold onto. On three identical tasks, turning
routing on cut cost from 6.48 to 2.91 US dollars, a 55 percent reduction, at
essentially identical token volume. The saving is pure model mix, not less work.
More importantly, we caught ourselves along the way: the first measurement showed
no difference, which turned out to be a real bug where the difficulty tier was
silently overriding the router. We fixed the precedence, re-measured, and only
then believed the number.

## What this proves

Three things, and they are the things that separate a defensible product from a
good demo.

First, we will measure ourselves against the outside world and publish the
result even when it is unflattering. The baseline report and its predictions are
in this repository, re-runnable as a regression yardstick.

Second, failures are treated as data, not embarrassment. The most valuable
output of the whole cycle was a measurement that looked like a failure and was
actually a map to two real fixes.

Third, the contract-first structure pays for itself: one spec change propagates as
coordinated fixes across four services, with the audit trail to prove what
changed and why.

## What is next

The benchmark becomes a standing matrix rather than a one-off: routing on versus
off, provider by provider, tracked over time. The scored-resolve confirmation for
the routing runs is now unblocked. And the honest gaps we have written down,
including cluster-scale proof and a flaky test we have refused to paper over, stay
on the board in public. That last part is the point. The whole reason to have a
factory instead of a magic box is that you can see inside it.
