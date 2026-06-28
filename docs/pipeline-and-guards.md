---
layout: default
title: The Guarded PARR Pipeline
permalink: /pipeline/
mermaid: true
---

# The Guarded PARR Pipeline

How a unit of work travels from a **handover** through **PFactory** (plan &
govern) → **AIFactory** (build) → **TFactory** (verify) → a **reviewed, merged
PR** — and exactly where, why and how execution is *guarded* at every hop.

> PARR = **P**repare · **A**ct · **R**eflect · **R**eview. Each factory owns one
> stage; a cryptographically-signed contract carries trust between them; humans
> stay in control at the decisions that matter.

---

## End to end — every step and decision gate

Every arrow is cheap; every **diamond** is a guard. This is where "let an agent
build it" becomes a governed process.

<div class="mermaid">
flowchart TD
    Start([Developer / Team / Agent<br/>has a task or plan]) --> HO1

    subgraph HO["1 · Handover"]
        HO1["/handover or /parr-run<br/>plan brief + acceptance criteria"]
    end

    HO1 --> PF1

    subgraph PF["2 · PFactory — Plan and Govern"]
        PF1["ingest: parse ACs,<br/>decompose to epic + child issues"]
        PF1 --> PF2{"Hard readiness checks?<br/>criteria present · AC to child coverage<br/>· deps acyclic · no silent fallback"}
        PF2 -- fail --> PFX["Reject / revise brief"]
        PF2 -- pass --> PF3["process: governance lenses<br/>security · feasibility · cost · architecture"]
        PF3 --> PF4{"aggregate over 0.75<br/>AND no blocking findings?"}
        PF4 -- no --> PFX
        PF4 -- yes --> PF5["Human approve<br/>(approver + plan-hash recorded)"]
        PF5 --> PF6["emit-contract:<br/>RFC-0002 Task Contract v2<br/>+ HMAC-SHA256 signature"]
    end

    PF6 -->|"POST /from-plan<br/>signed contract"| AF1

    subgraph AF["3 · AIFactory — Build"]
        AF1{"Signature verifies?<br/>shared key per authority"}
        AF1 -- no --> AFB["FALLBACK: create-and-run<br/>re-plan from scratch<br/>(contract discarded)"]
        AF1 -- yes --> AF2["TRUSTED fast path:<br/>install plan + spec.md,<br/>persist contract to context/,<br/>SKIP the spec pipeline"]
        AF2 --> AF3["Build in dependency waves<br/>model from contract (Gemini/Claude)<br/>coder implements subtasks"]
        AFB --> AF3
        AF3 --> AF4["QA reviewer to QA fixer loop"]
    end

    AF4 --> AF5{"auto-handover<br/>to TFactory?"}
    AF5 -- no --> DoneB([Stop at build —<br/>human review / manual PR])
    AF5 -- yes --> TF1

    subgraph TF["4 · TFactory — Verify"]
        TF1["ingest spec + contract<br/>to context/task_contract.json"]
        TF1 --> TF2["Planner AUTO-runs;<br/>reads DECLARED test profile<br/>(lanes · frameworks · ac_to_code_map)"]
        TF2 --> TF3["Generate + run tests"]
        TF3 --> TF4{"Tests pass?"}
        TF4 -- no --> TF5{"handback cycles under 2?"}
        TF5 -- yes --> HB["apply-correction to<br/>AIFactory QA fixer to re-test"]
        HB --> TF3
        TF5 -- no --> NH["needs_human<br/>(RFC-0001 event)"]
    end

    TF4 -- yes --> PR1

    subgraph PRE["5 · PR Endgame"]
        PR1["Open PR<br/>(gh auth setup-git + push)"]
        PR1 --> PR2["Pre-merge reviewer<br/>AIFactory engine / Copilot / any"]
        PR2 --> PR3{"Verdict?"}
        PR3 -- "changes requested" --> PR4{"fix cycles under 2?"}
        PR4 -- yes --> PR5["auto-fix to push to re-review"]
        PR5 --> PR2
        PR4 -- no --> NH
        PR3 -- "approved / ready" --> PR6{"auto-merge<br/>enabled?"}
        PR6 -- no --> DoneR([PR left OPEN —<br/>human merges])
        PR6 -- yes --> PR7{"Mergeable?"}
        PR7 -- "behind base" --> PR8["update-branch + retry"]
        PR8 --> PR7
        PR7 -- "true conflict" --> NH
        PR7 -- clean --> PR9["Merge to re-test on main"]
    end

    PR9 --> EndM([Merged])
    NH --> EndH([Human takes over])

    classDef gate fill:#fabd2f,stroke:#d79921,color:#1d2021;
    classDef stop fill:#fb4934,stroke:#cc241d,color:#1d2021;
    classDef good fill:#b8bb26,stroke:#98971a,color:#1d2021;
    class PF2,PF4,AF1,AF5,TF4,TF5,PR3,PR4,PR6,PR7 gate;
    class PFX,NH,EndH stop;
    class AF2,PR9,EndM good;
    classDef pf fill:#83a598,stroke:#5f8175,color:#1b1b1b,font-weight:bold;
    classDef af fill:#fe8019,stroke:#c4641a,color:#1b1b1b,font-weight:bold;
    classDef tf fill:#b8bb26,stroke:#8d9020,color:#1b1b1b,font-weight:bold;
    classDef cf fill:#fabd2f,stroke:#c69526,color:#1b1b1b,font-weight:bold;
    classDef pfbox fill:#32302f,stroke:#83a598,stroke-width:2px,color:#83a598;
    classDef afbox fill:#32302f,stroke:#fe8019,stroke-width:2px,color:#fe8019;
    classDef tfbox fill:#32302f,stroke:#b8bb26,stroke-width:2px,color:#b8bb26;
        class PF pfbox;
        class PF1 pf;
        class PF3 pf;
        class PF5 pf;
        class PF6 pf;
        class AF afbox;
        class AFB af;
        class AF3 af;
        class AF4 af;
        class HB af;
        class PR2 af;
        class TF tfbox;
        class TF1 tf;
        class TF2 tf;
        class TF3 tf;
</div>

---

## The guards — what is protected, why, and how

| # | Guard | Why it exists | How it's enforced |
|---|-------|---------------|-------------------|
| G1 | **Acceptance criteria required** | You can't verify what you didn't specify | PFactory hard-fails a brief with no `## Acceptance Criteria`; every AC maps to a child issue |
| G2 | **Governance lenses** | Catch risk *before* code exists | `process` scores security · feasibility · cost · architecture; aggregate must clear **0.75** with no blocking findings |
| G3 | **Live-infra / access checks** | Don't promise cloud actions you can't perform | Unverified IAM/cloud actions are flagged (surfaced, not hidden); soft/waivable when air-gapped |
| G4 | **Human approval** | A person owns the go/no-go | `approve` records approver + plan-hash; nothing is signed until then |
| G5 | **HMAC-signed contract** | Tamper-proof handover; downstream trusts *content*, not the caller | RFC-0002 v2, signed with a per-authority shared key |
| G6 | **Verify or fallback** | A forged/edited contract must not skip planning | Valid signature → trusted fast path; invalid → safe re-plan fallback |
| G7 | **OAuth-only auth** | Agents must not silently bill a raw API key | API key scrubbed by default; direct-key billing is opt-in (`AIFACTORY_ALLOW_API_KEY`) |
| G8 | **Agent env scrub** | A prompt-injected agent can't exfiltrate host secrets | Control-plane tokens, DB URLs, cloud creds, provider keys blanked from the agent env |
| G9 | **Allowlist + FS jail** | Limit blast radius of generated commands | Per-stack command allowlist; filesystem restricted to the workspace; bash isolated by the pod boundary |
| G10 | **Worktree isolation** | One build can't corrupt another or your tree | Each spec builds in its own git worktree/branch; merge only on explicit action |
| G11 | **Declared-AC testing** | Test what was *promised*, not a guess | The contract's `tfactory` block (lanes/frameworks/`ac_to_code_map`) drives test generation |
| G12 | **Bounded handback** | Self-correction must not loop forever | TFactory→AIFactory correction capped (≤2) → terminal `needs_human` |
| G13 | **Reviewer-gated merge** | Nothing merges unreviewed | Merge needs the configured reviewer's verdict; changes-requested → bounded auto-fix |
| G14 | **Never force-merge** | Protect `main` from unsafe automation | On a true conflict: `update-branch` once, then **human-stop** — never `--force` |
| G15 | **Full audit trail** | Enterprises need provenance | Every transition emits RFC-0001 events in the CFactory cockpit, keyed by `correlation_key` |
| G16 | **Completion evidence gates** | "Reached a terminal state" must not be mistaken for "did the work" | A stage claims success only with proof — issues created (plan), non-zero tokens + completed phases (build), non-null verdict + executed tests (verify); consumers render success-without-evidence as unproven. [RFC-0001a](rfc/0001a-completion-evidence-gates.md) |

---

## Two independent layers of defense

<div class="mermaid">
flowchart LR
    subgraph TRUST["Trust chain (between factories)"]
        T1["Human approval"] --> T2["HMAC signature"] --> T3["Verify or fallback"] --> T4["Contract drives tests"]
    end
    subgraph EXEC["Execution sandbox (around every agent)"]
        E1["OAuth-only auth"]
        E2["Host-secret scrub"]
        E3["Command allowlist"]
        E4["Filesystem jail + worktree"]
        E5["Pod boundary / bash sandbox"]
    end
    subgraph LIMITS["Loop and release limits"]
        L1["Handback ≤ 2"]
        L2["PR auto-fix ≤ 2"]
        L3["Human-stop on conflict / needs_human"]
        L4["No force-merge"]
    end
    TRUST --> EXEC --> LIMITS
</div>

The *trust chain* governs what crosses factory boundaries (a signed,
human-approved contract). The *execution sandbox* governs what a single agent
can do on a machine. Even a fully compromised agent prompt is boxed by the
sandbox; even a forged contract is rejected by the trust chain.

---

## The signed handshake + self-correcting verify loop

<div class="mermaid">
sequenceDiagram
    actor Dev as Developer / Agent
    participant PF as PFactory
    participant AF as AIFactory
    participant TF as TFactory
    participant GH as GitHub
    Dev->>PF: handover (brief + ACs)
    PF->>PF: ingest · readiness checks
    PF->>PF: process · governance lenses
    PF-->>Dev: approve? (human gate)
    Dev->>PF: approve
    PF->>AF: signed Task Contract (HMAC)
    AF->>AF: verify signature
    alt valid
        AF->>AF: trusted fast path — skip planning
    else invalid
        AF->>AF: fallback — re-plan from scratch
    end
    AF->>AF: build waves (OAuth-only, scrubbed env)
    AF->>TF: handoff spec + contract
    TF->>TF: test the DECLARED ACs
    loop up to 2 handbacks
        TF--xAF: tests fail → apply-correction
        AF->>AF: QA fixer
        AF->>TF: re-test
    end
    TF->>GH: open PR
    GH->>GH: reviewer verdict
    alt approved + auto-merge
        GH->>GH: merge → re-test on main
    else changes / conflict / over 2 loops
        GH-->>Dev: human-stop
    end
</div>

---

## Who it's for — real scenarios

### The solo builder
**Maya** maintains side-projects alone on a subscription, no API budget. She
`/handover`s a feature with ACs and goes to dinner. **OAuth-only** auth uses her
subscription (never a metered key); the build runs in an **isolated worktree**;
TFactory tests the AC she declared; the PR is **left open** because she hasn't
enabled auto-merge. Saturday morning: a green, tested PR awaiting a 30-second
review. No surprise bills, no broken main.

### The developer in a team
**Raj** is blocked on a frontend change he lacks context for. He hands a short
brief to PFactory instead of context-switching. **Required ACs** make the intent
unambiguous; the **architecture lens** checks it fits; the **`ac_to_code_map`**
makes TFactory write the exact test; a **bounded handback** fixes a flaky
selector automatically. Raj stays in flow; the change lands as a reviewed PR.

### The squad
A platform squad runs a sprint with 12 stories, 4 independent. The lead approves
a multi-service epic; the **acyclic dependency check** proves the graph is safe
before any code; each story builds in its **own worktree**; the **CFactory
cockpit** shows every story's live stage. Four merge themselves overnight with
passing tests; standup is about the *one* exception, not status-reporting twelve.

### The enterprise
A regulated org adopts the Factory as its standard ticket-to-merge process. The
**security lens + threshold** blocks risky plans before code; **human approval**
with recorded approver + plan-hash is the change-control record; the **HMAC
contract** ties every build to a signed, approved plan; **scrub + allowlist + FS
jail** mean agents can't leak secrets or run arbitrary commands;
**never-force-merge** + the reviewer gate protect `main`; the **RFC-0001 audit
trail** is the auditor's evidence. AI does the toil; the *process* is enforced by
the tool, not by hope.

---

*Source: [`AIFactory/guides/parr-pipeline-and-guards.md`](https://github.com/olafkfreund/AIFactory/blob/main/guides/parr-pipeline-and-guards.md). Every guard here is implemented and verified in the running cluster.*
