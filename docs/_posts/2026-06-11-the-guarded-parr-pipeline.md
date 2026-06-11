---
layout: post
title: "The guards behind the pipeline: how Factory turns agents into a process"
subtitle: "A new reference page maps every step and decision from handover to merge — and the fifteen guards that make AI-built code something an enterprise can actually adopt. Plus four real adoption scenarios, from the solo builder to the regulated enterprise."
date: 2026-06-11 12:00:00 +0000
author: Olaf Freund
mermaid: true
---

"Let an agent build it" is a liability until you can answer one question: *what
stops it going wrong?* Unbounded fix loops, leaked secrets, unreviewed merges,
no provenance — that's the gap between a demo and a process you'd run in
production. Today we published a single reference that answers it end to end:

**→ [The Guarded PARR Pipeline](/pipeline/)**

It traces a unit of work from a **handover**, through **PFactory** (plan &
govern), **AIFactory** (build), **TFactory** (verify), to a **reviewed, merged
PR** — and marks every decision gate along the way. Every arrow is cheap; every
diamond is a guard.

## The shape of it

<div class="mermaid">
flowchart LR
    HO["Handover<br/>brief + ACs"] --> PF["PFactory<br/>govern + sign"]
    PF -->|"signed contract"| AF["AIFactory<br/>build"]
    AF -->|"spec + contract"| TF["TFactory<br/>verify"]
    TF -->|"green"| PR["PR endgame<br/>review + merge"]
    TF -. "fail · handback ≤2" .-> AF
    PR -. "conflict / changes / >2" .-> H["Human-stop"]
    PR -->|"approved"| M["Merged"]
    classDef g fill:#b8bb26,stroke:#98971a,color:#1d2021;
    class M g;
</div>

## Fifteen guards, two layers

The reference enumerates fifteen guards — but they fall into two independent
layers, and that independence is the point:

- **A trust chain between factories.** A human approves the plan; PFactory signs
  it with HMAC; AIFactory *verifies the signature* before it will skip planning —
  a forged or edited contract falls back to a full re-plan instead of being
  trusted. The contract then tells TFactory exactly which acceptance criteria to
  test, so verification checks what was *promised*, not what an agent guessed.

- **A sandbox around every agent.** OAuth-only auth (a stray API key is scrubbed
  unless you explicitly opt in), host secrets blanked from the agent
  environment, a per-stack command allowlist, a filesystem jail, and git
  worktree isolation. Even a fully prompt-injected agent is boxed.

On top of both: **bounded loops** (handback and PR auto-fix each cap at two
cycles, then escalate to a human), a **reviewer-gated merge**, and a hard rule
that the automation **never force-merges** — a true conflict always stops for a
person.

## Who it's for

The page closes with four grounded scenarios:

- **The solo builder** who hands off a feature on a subscription and wakes up to
  a green, tested PR — with no surprise API bill and an untouched main branch.
- **The developer in a team** who hands a blocked dependency to PFactory instead
  of context-switching, and gets back a reviewed PR.
- **The squad** running a sprint where four independent stories merge themselves
  overnight and standup is about the *one* exception.
- **The regulated enterprise** adopting the Factory as its governed
  ticket-to-merge process — approval gates, signed provenance, security
  thresholds, sandboxed execution, and an RFC-0001 audit trail an auditor can read.

That last one is the thesis. The Factory isn't "AI that writes code." It's a
pipeline where the *process* — approval, signed provenance, security gates,
sandboxed execution, bounded self-correction, reviewer-gated merge — is enforced
by the tool, not by hope. That's the difference that makes it adoptable.

**Read the full reference, with every diagram and guard: [The Guarded PARR
Pipeline](/pipeline/).**
