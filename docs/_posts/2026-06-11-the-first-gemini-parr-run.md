---
layout: post
title: "Field report: the first end-to-end Gemini PARR run"
subtitle: "We pushed a real job — an EKS Terraform module plus three FastAPI microservices — through the whole factory chain on Gemini: plan, govern, sign, build, hand off, verify. Here's what worked, what broke (and got fixed live), the one gap that's left, and where we go next. An honest field report, not a victory lap."
date: 2026-06-11 10:00:00 +0000
author: Olaf Freund
mermaid: true
---

We set out to answer one question end to end: **can a real, multi-service job
travel the whole PARR pipeline — on Gemini, not just Claude — with every guard
engaged?** Not a toy. The brief was an **AWS EKS Terraform module** (generate +
validate only, no live cloud) plus **three FastAPI microservices** — a
tic-tac-toe frontend, an authenticated scoreboard with a database, and a
Redis-backed leaderboard cache — with six acceptance criteria including a real
auth requirement.

This is what we learned.

## The run

<div class="mermaid">
flowchart LR
    H["EKS brief<br/>6 ACs"] --> P["PFactory<br/>gates 0.96"]
    P -->|"signed contract"| A["AIFactory<br/>8/8 on Gemini"]
    A -->|"spec + contract"| T["TFactory<br/>AC-mapped tests"]
    T -. "no code to run<br/>(gap #547)" .-> X["verdict pending"]
    classDef ok fill:#b8bb26,stroke:#98971a,color:#1d2021;
    classDef gap fill:#fabd2f,stroke:#d79921,color:#1d2021;
    class P,A,T ok;
    class X gap;
</div>

- **PFactory** parsed the criteria, decomposed the epic, and ran its governance
  lenses: **0.96 aggregate, security 1.0**. It correctly flagged the unverified
  AWS IAM actions (`eks:CreateCluster`, `iam:CreateRole`, …) as a soft warning —
  air-gapped, validate-only, so informational rather than blocking. A human
  approved; PFactory signed an RFC-0002 Task Contract.
- **AIFactory** verified the signature, took the **trusted fast path** (skip
  planning — the contract *is* the plan), and **built all 8 subtasks on Gemini**
  (`gemini-2.5-pro` via the Antigravity CLI): the Terraform module, three FastAPI
  services, tests, and CI/CD landed in an isolated worktree.
- **TFactory** received the handoff, persisted the contract, **auto-ran its
  planner**, and generated tests that map *exactly* to the declared criteria —
  `test_scoreboard_auth.py` (the 401 case), `test_scoreboard_sort.py`,
  `frontend-board.spec.ts` (a Playwright browser test), `test_frontend_move.py`,
  and more. Tests inference would never invent for an "API + Terraform" job —
  they came straight from the signed contract.

## What broke — and got fixed, live

The honest part. Getting that clean run required fixing four real things this
week, each found by *running* the thing rather than trusting the green unit
tests:

1. **We were quietly billing the Claude API.** The cluster's OAuth token had
   expired, so every agent silently fell back to an `ANTHROPIC_API_KEY` and
   billed the metered API instead of the subscription. We refreshed OAuth,
   **removed the API key from all four factory pods**, and made direct-key
   billing an explicit opt-in (`AIFACTORY_ALLOW_API_KEY`) for orgs that *want*
   it. Billing the wrong way is now structurally impossible by default.
2. **TFactory ingested specs but never started testing.** A request-time import
   failed only inside the long-lived server (not in any fresh process), and the
   error was swallowed — so specs sat at `pending` forever. Fixed by pinning the
   import at startup; the planner now auto-runs on ingest.
3. **Trusted builds didn't carry their contract to TFactory.** The build rewrote
   the plan file mid-flight, dropping the test profile before the handoff fired.
   We now stash the signed contract in a build-safe location at ingest — so
   TFactory tests the *declared* criteria, not a guess.
4. **You couldn't choose Gemini through the contract.** The execution profile
   hardcoded Claude models. A small `PFACTORY_EXECUTION_MODEL` override makes the
   provider a one-line choice — which is how this entire run went to Gemini.

None of these showed up in CI. All of them showed up the moment we ran a real
job across real services. That's the point of running it.

## The gap that's left

TFactory generated the *right* tests — but it has **no code to run them
against.** Today's handoff carries the spec and the signed contract, but not the
built branch (it's the "no AIFactory branch" path). So the verify leg proves
"we'd test the right things" without yet proving "the build passes them." That's
why this run's verdict is still pending rather than green.

We've filed it as a tracked issue. The fix is concrete: **AIFactory pushes the
build's worktree branch and includes a `{repo, branch, head_sha}` reference in
the handoff; TFactory checks that branch out into the spec workspace before it
runs the lanes.** That single change turns "right tests, no target" into "the
declared tests, run against the real Gemini-built code" — and it's also what
makes the bounded handback loop (TFactory → AIFactory → re-test) meaningful.

## What's working — and why it matters

Everything *except* that last hop is proven, live, on a multi-service job:

- Governed planning with real thresholds, not vibes.
- A **cryptographically signed** handover — downstream trusts content, not the
  caller.
- A **provider choice** (Claude *or* Gemini) that flows through the contract.
- OAuth-only execution, secrets scrubbed from agents, commands allowlisted,
  builds isolated in worktrees.
- **Contract-driven verification** — the tests match what was promised.
- Every transition audited in the CFactory cockpit.

The full map of those guards lives at [**/pipeline/**](/pipeline/).

## What the future holds

- **Close the last hop** — the code-carrying handoff, so the loop runs *and*
  passes against real code, with automatic handback on failure.
- **Provider plurality** — this run proved Gemini; **Ollama / local models are
  next**, so a team can run the whole pipeline on infrastructure they own.
- **Truly autonomous delivery** — plan → build → verify → reviewed PR → merge,
  with humans at the gates that matter and the machine doing the toil in between.
- **Adoption as a process** — not "AI that writes code," but a governed,
  signed, sandboxed, audited path from ticket to merge that an enterprise can
  actually stand behind.

We didn't ship a perfect loop today. We shipped a real one, found its rough
edge by running it, and wrote down exactly how we'll smooth it. That's the
difference between a demo and a product.
