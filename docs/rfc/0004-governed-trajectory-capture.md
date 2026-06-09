---
layout: default
title: "RFC-0004: Governed-Trajectory Capture"
permalink: /rfc/trajectory-capture/
---

# RFC-0004 — Governed-Trajectory Capture

> **Status:** Proposed (research / exploratory — not yet scheduled) · **Version:** 0.1 ·
> **Created:** 2026-06-09
> Builds on [RFC-0001](./0001-correlation-key-and-completion-event.md) (correlation
> key + completion-event envelope) and [RFC-0002](./0002-task-contract.md) (Task
> Contract v2). Where RFC-0001/0002 define how the family *threads and contracts*
> one unit of work, this RFC asks what we can do with the **complete, threaded,
> verified record** that thread leaves behind.
>
> Research origin: reading [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
> (commit `b5f8996`) — see the blog post
> [*What the Hermes agent taught us*](/blog/2026/06/09/what-the-hermes-agent-taught-us/).
> This RFC is the durable home for the idea tracked in Factory issue #30.

## Why this RFC exists

Hermes captures every agent run as a **trajectory** — a ShareGPT-format JSONL record
(`trajectory_samples.jsonl`, `failed_trajectories.jsonl`, written by
`save_trajectory()`) — explicitly to train the next generation of tool-calling
models. It is a single self-improving process, so its trajectories are
*self-labelled*: the agent decides what "good" looks like.

Factory already produces something Hermes structurally cannot: a **governed,
verified** trajectory. Every PARR run threads `plan → code → branch/PR → tests →
verdict`, keyed by the correlation key (the GitHub issue number, RFC-0001), gated by
human approval (PFactory) and a signed Task Contract (RFC-0002), and graded by an
*independent* 5-signal verdict (TFactory). That is an unusually high-signal dataset:
each record carries a third-party label, not the actor's own opinion of its work.

The question this RFC frames — deliberately without yet answering all of it — is
whether to treat that record as a **first-class Factory output**: an opt-in,
privacy-reviewed corpus of *verified software-delivery trajectories*, usable first
as a regression/eval harness for our own agents and, later, potentially for
training.

## What makes a Factory trajectory different

| Property | Hermes trajectory | Factory PARR trajectory |
|---|---|---|
| Label source | self-assessed by the agent | **independent** — TFactory's 5-signal verdict |
| Governance | none (single process) | human approval (PFactory) + signed contract (RFC-0002) |
| Threading | per-process turns | cross-product, keyed by one correlation key (RFC-0001) |
| Boundaries | one model's tool calls | plan ↔ code ↔ verify ↔ review, each a separate service |
| Failure signal | `failed_trajectories.jsonl` | the TFactory handback loop — *why* it failed and the correction |

The handback loop is the part worth emphasizing: a Factory failure record is not just
"this run failed", it is "verification rejected it for reason X, the correction was
Y, and re-verification passed". That is a labelled repair trajectory — rare and
high-value for both eval and training.

## Proposal (sketch)

1. **Record shape.** Define a trajectory record keyed by the correlation key that
   captures the full PARR thread — the approved plan, the Task Contract, the
   resulting branch/PR diff, the test set, and the TFactory verdict as the **label**
   (pass/fail + the 5 signals + any handback). Align the envelope with the existing
   RFC-0001 completion-event so capture is additive, not a parallel schema.
2. **Where capture lives.** Most likely **CFactory**, which already assembles the
   whole WorkItem (it ingests completion events from all four stages and owns the
   correlation store + timeline). The alternative is per-product emit + join; the
   open questions below decide this.
3. **Treatment.** Emit as an **opt-in, privacy-reviewed, additive** artifact — inert
   when unconfigured, exactly like every other cross-cutting integration (RFC-0003
   design principle 1). It is never required for the pipeline to run.
4. **First use is eval, not training.** Stand it up first as a regression/eval
   harness for our *own* agents (does AIFactory still solve last month's tasks; does
   TFactory's verdict stay stable). Training use, if any, comes later and behind a
   separate governance review.

## Design principles (inherited)

- **Additive and opt-in.** No capture unless explicitly enabled and consented.
  (RFC-0003 §Design principles.)
- **One correlation key still rules.** A trajectory is just another view of the same
  WorkItem, threaded by the same GitHub-issue key (RFC-0001).
- **Reuse the envelope.** Extend / reference the RFC-0001 completion-event rather
  than inventing a second event schema.

## Open questions (must be resolved before this leaves Proposed)

- [ ] **Capture location** — CFactory (sees all stages) vs per-product emit + join.
- [ ] **Privacy / governance** — redaction strategy, opt-in scope, and the *license*
      of captured code. Customer code cannot be captured without explicit, scoped
      consent; this is the gating question.
- [ ] **Format** — align with an open standard (ShareGPT / agent-skills-adjacent) for
      portability, or a Factory-native schema that maps to one on export?
- [ ] **First eval use** — define the regression harness concretely (task set,
      cadence, what regression means) before any training conversation.
- [ ] **Retention** — how long are trajectories kept, and where, under what controls?

## Relationship to other RFCs

- **RFC-0001** — the correlation key is the trajectory's primary key; the
  completion-event envelope is the basis for the record shape.
- **RFC-0002** — the signed Task Contract is part of the captured record (it is the
  *intent* the trajectory is graded against).
- **RFC-0003** — same additive / opt-in posture; capture would ride the same
  cross-product conventions.

## Status & next step

This RFC is **Proposed / exploratory**. It exists to give the idea a durable home and
to make the open questions explicit. It is intentionally **not scheduled**: the
governance and privacy questions (especially captured-code licensing and consent)
must be answered first. When they are, this RFC moves to *Accepted* with a concrete
record schema and a named owning service.
