# The Factory PARR Pipeline — Steps, Decisions & Guards

> How a unit of work travels from a **handover** through **PFactory** (plan &
> govern) → **AIFactory** (build) → **TFactory** (verify) → a **reviewed,
> merged PR** — and exactly where and why execution is *guarded* at every hop.
>
> PARR = **P**lan · **A**ct · **R**eview · **R**elease. Each factory owns one
> stage; a signed contract carries trust between them; humans stay in control at
> the decisions that matter.

---

## 1. The big picture — end to end, with every decision gate

```mermaid
flowchart TD
    Start([Developer / Team / Agent<br/>has a task or plan]) --> HO1

    subgraph HO["1 · Handover"]
        HO1["/handover or /parr-run<br/>plan brief + acceptance criteria"]
    end

    HO1 --> PF1

    subgraph PF["2 · PFactory — Plan &amp; Govern"]
        PF1["ingest: parse ACs,<br/>decompose to epic + child issues"]
        PF1 --> PF2{"Hard readiness checks?<br/>criteria present · AC→child coverage<br/>· deps acyclic · no silent fallback"}
        PF2 -- fail --> PFX["Reject / revise brief"]
        PF2 -- pass --> PF3["process: governance lenses<br/>security · feasibility · cost · architecture"]
        PF3 --> PF4{"aggregate ≥ 0.75<br/>AND no blocking findings?"}
        PF4 -- no --> PFX
        PF4 -- yes --> PF5["Human approve<br/>(approver + plan-hash recorded)"]
        PF5 --> PF6["emit-contract:<br/>RFC-0002 Task Contract v2<br/>+ HMAC-SHA256 signature"]
    end

    PF6 -->|"POST /from-plan<br/>signed contract"| AF1

    subgraph AF["3 · AIFactory — Build"]
        AF1{"Signature verifies?<br/>shared key per authority"}
        AF1 -- no --> AFB["FALLBACK: create-and-run<br/>re-plan from scratch<br/>(contract discarded)"]
        AF1 -- yes --> AF2["TRUSTED fast path:<br/>install plan + spec.md,<br/>persist contract to context/,<br/>SKIP the spec pipeline (~70% time)"]
        AF2 --> AF3["Build in dependency waves<br/>model from contract (Gemini/Claude)<br/>coder implements subtasks"]
        AFB --> AF3
        AF3 --> AF4["QA reviewer → QA fixer loop"]
    end

    AF4 --> AF5{"auto-handover<br/>to TFactory?"}
    AF5 -- no --> DoneB([Stop at build —<br/>human review / manual PR])
    AF5 -- yes --> TF1

    subgraph TF["4 · TFactory — Verify"]
        TF1["ingest spec + contract<br/>→ context/task_contract.json"]
        TF1 --> TF2["Planner AUTO-runs;<br/>reads DECLARED test profile<br/>(lanes · frameworks · ac_to_code_map)"]
        TF2 --> TF3["Generate + run tests"]
        TF3 --> TF4{"Tests pass?"}
        TF4 -- no --> TF5{"handback cycles &lt; 2?"}
        TF5 -- yes --> HB["apply-correction →<br/>AIFactory QA fixer → re-test"]
        HB --> TF3
        TF5 -- no --> NH["needs_human<br/>(RFC-0001 event)"]
    end

    TF4 -- yes --> PR1

    subgraph PRE["5 · PR Endgame"]
        PR1["Open PR<br/>(gh auth setup-git + push)"]
        PR1 --> PR2["Pre-merge reviewer<br/>AIFactory engine / Copilot / any"]
        PR2 --> PR3{"Verdict?"}
        PR3 -- "changes_requested" --> PR4{"fix cycles &lt; 2?"}
        PR4 -- yes --> PR5["auto-fix → push → re-review"]
        PR5 --> PR2
        PR4 -- no --> NH
        PR3 -- "approved / ready_to_merge" --> PR6{"auto-merge<br/>enabled?"}
        PR6 -- no --> DoneR([PR left OPEN —<br/>human merges])
        PR6 -- yes --> PR7{"Mergeable?"}
        PR7 -- "behind base" --> PR8["update-branch + retry"]
        PR8 --> PR7
        PR7 -- "true conflict" --> NH
        PR7 -- clean --> PR9["Merge → re-test on main"]
    end

    PR9 --> EndM([Merged ✅])
    NH --> EndH([Human takes over])

    classDef gate fill:#fff3cd,stroke:#d39e00,color:#000;
    classDef stop fill:#f8d7da,stroke:#c82333,color:#000;
    classDef good fill:#d4edda,stroke:#28a745,color:#000;
    class PF2,PF4,AF1,AF5,TF4,TF5,PR3,PR4,PR6,PR7 gate;
    class PFX,NH,EndH stop;
    class AF2,PR9,EndM good;
```

---

## 2. The guards — what is protected, why, and how

Every arrow above is cheap; every **diamond** is a guard. This is where "vibe
coding" becomes a governed process.

| # | Guard | Why it exists | How it's enforced |
|---|-------|---------------|-------------------|
| G1 | **Acceptance criteria required** | You can't verify what you didn't specify | PFactory `ingest` hard-fails a brief with no `## Acceptance Criteria`; every AC must map to a child issue |
| G2 | **Governance lenses** (security, feasibility, cost, architecture) | Catch risk *before* code exists, not in review | `process` scores each lens; aggregate must clear **0.75** and have **no blocking findings**, or approval is refused |
| G3 | **Live-infra / access checks** | Don't promise cloud actions you can't perform | Readiness check flags unverified IAM/cloud actions (e.g. `eks:CreateCluster`); soft/waivable when air-gapped, surfaced not hidden |
| G4 | **Human approval** | A person owns the go/no-go | `approve` records the approver + a plan-hash; nothing is signed until then |
| G5 | **HMAC-signed Task Contract** | Tamper-proof handover; downstream trusts *content*, not the caller | `emit-contract` signs the canonical plan+approval with a per-authority shared key (RFC-0002 v2) |
| G6 | **Signature verification + fallback** | A forged/edited contract must not skip planning | AIFactory verifies the signature; **valid → trusted fast path**, **invalid → safe fallback** (re-plan from scratch) — never silently trusts |
| G7 | **OAuth-only auth** | Agents must not silently bill a raw API key | `core/auth.py` scrubs `ANTHROPIC_API_KEY` from agents by default; direct-key billing is **opt-in** via `AIFACTORY_ALLOW_API_KEY` |
| G8 | **Agent env scrub** | A prompt-injected agent can't exfiltrate host secrets | Control-plane tokens, DB URLs, cloud creds, provider keys are blanked from the agent's subprocess env |
| G9 | **Command allowlist + filesystem jail** | Limit blast radius of generated/automated commands | Per-stack dynamic allowlist; FS ops restricted to the workspace/worktree; bash isolated by pod boundary (+ sandbox where supported) |
| G10 | **Worktree isolation** | One build can't corrupt another or the user's tree | Each spec builds in its own git worktree on its own branch; merge only on explicit action |
| G11 | **Declared-AC testing** | TFactory tests what was *promised*, not what it guesses | The contract's `tfactory` block (lanes/frameworks/`ac_to_code_map`) drives test generation — authoritative over inference |
| G12 | **Bounded handback loop** | Self-correction must not loop forever / burn budget | TFactory→AIFactory `apply-correction` is capped (default **≤2** cycles) → then terminal `needs_human` + RFC-0001 event |
| G13 | **Reviewer-gated merge** | Nothing merges unreviewed | Merge requires the configured reviewer's verdict (AIFactory engine / Copilot / any); changes-requested triggers a bounded auto-fix loop |
| G14 | **Never force-merge** | Protect `main` from unsafe automation | On a true conflict the bot tries `update-branch` once, then **stops for a human**; it never uses `--force` |
| G15 | **Full audit trail** | Enterprises need provenance | Every transition emits RFC-0001 events aggregated in the CFactory cockpit, keyed by `correlation_key` |

---

## 3. Trust & security — defense in depth around every agent run

```mermaid
flowchart LR
    subgraph TRUST["Trust chain (between factories)"]
        T1["Human approval"] --> T2["HMAC signature"] --> T3["Verify or fallback"] --> T4["Contract drives tests"]
    end

    subgraph EXEC["Execution sandbox (around every agent)"]
        E1["OAuth-only auth<br/>(key scrubbed unless opt-in)"]
        E2["Host-secret scrub"]
        E3["Command allowlist"]
        E4["Filesystem jail +<br/>git worktree"]
        E5["Pod boundary / bash sandbox"]
    end

    subgraph LIMITS["Loop & release limits"]
        L1["Handback ≤ 2"]
        L2["PR auto-fix ≤ 2"]
        L3["Human-stop on<br/>conflict / needs_human"]
        L4["No force-merge"]
    end

    TRUST --> EXEC --> LIMITS
```

**Two independent layers.** The *trust chain* governs what crosses factory
boundaries (a signed, human-approved contract). The *execution sandbox* governs
what a single agent can do on a machine (no secrets, no arbitrary commands, no
escaping its workspace). Even a fully compromised agent prompt is boxed by the
sandbox; even a forged contract is rejected by the trust chain.

---

## 4. The signed handshake + self-correcting verify loop (sequence)

```mermaid
sequenceDiagram
    actor Dev as Developer / Agent
    participant PF as PFactory
    participant AF as AIFactory
    participant TF as TFactory
    participant GH as GitHub

    Dev->>PF: handover (brief + ACs)
    PF->>PF: ingest · readiness checks
    PF->>PF: process · governance lenses (≥0.75)
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
    else changes / conflict / >2 loops
        GH-->>Dev: human-stop
    end
```

---

## 5. Real-life user stories

Each story maps a **scenario** → the **guards that engage** → the **outcome**.

### 5.1 Individual — the solo builder / indie hacker

> **Maya** maintains three side-projects alone. She has a Claude subscription,
> not an API budget.

- **Scenario:** Friday night, Maya types `/handover "add CSV export to the
  reports page, must stream large files, cover with tests"` and goes to dinner.
- **Guards that engage:** OAuth-only auth means her subscription is used, never
  a metered API key (**G7**); the build runs in an isolated worktree so her main
  branch is untouched (**G10**); TFactory tests the streaming AC she declared
  (**G11**); the PR is opened but **left open** because she hasn't enabled
  auto-merge (**G13/G6 default-safe**).
- **Outcome:** Saturday morning there's a green PR with tests waiting for a
  30-second review. No surprise bills, no broken main, no babysitting.

### 5.2 Developer in a team — the feature handoff

> **Raj** is a backend dev on a 6-person squad. He's blocked waiting on a
> frontend change he doesn't have context for.

- **Scenario:** Raj writes a short brief with ACs ("clicking *Retry* re-issues
  the failed request and shows a toast") and hands it to PFactory instead of
  context-switching.
- **Guards that engage:** PFactory forces real ACs (**G1**) so the intent is
  unambiguous; the architecture lens checks it fits the existing component model
  (**G2**); the contract carries an `ac_to_code_map` so TFactory writes the exact
  UI test (**G11**); a bounded handback fixes a flaky selector automatically
  (**G12**) without pulling Raj back in.
- **Outcome:** Raj stays in flow on his own work; the frontend change lands as a
  reviewed PR he can sanity-check, not a half-finished branch he has to adopt.

### 5.3 A team / squad — parallel sprint execution

> **A platform squad** runs a sprint with 12 stories, 4 of them independent.

- **Scenario:** The lead approves a multi-service epic in PFactory; the contract
  declares 4 parallel build waves.
- **Guards that engage:** the readiness check proves the dependency graph is
  **acyclic** before any code (**G1**); workers are capped so parallelism can't
  thrash (**execution profile**); each story builds in its own worktree so they
  can't collide (**G10**); the CFactory cockpit shows every story's live stage by
  `correlation_key` (**G15**); the one story that fails tests cleanly hits
  `needs_human` instead of merging broken (**G12/G13**).
- **Outcome:** Four stories merge themselves with passing tests overnight; the
  squad's standup is about the *one* exception, not status-reporting twelve.

### 5.4 Enterprise — Factory as the governed build process

> **A regulated fintech** wants AI-assisted delivery *without* losing change
> control, auditability, or security posture.

- **Scenario:** Engineering adopts the Factory suite as the standard path from
  ticket to merge. Policy: security gate is mandatory; every change is
  human-approved at the plan stage and reviewer-gated at merge; nothing
  auto-merges to protected branches.
- **Guards that engage:** the **security lens + threshold** blocks risky plans
  before code exists (**G2**); **human approval** with recorded approver +
  plan-hash gives a change-control record (**G4**); the **HMAC contract** makes
  every build traceable to a signed, approved plan (**G5**); **OAuth-only / env
  scrub / allowlist / FS jail** mean agents can't leak secrets or run arbitrary
  commands (**G7–G9**); **never-force-merge** + reviewer gate protect `main`
  (**G13/G14**); the **RFC-0001 audit trail** in CFactory is the evidence for an
  auditor (**G15**).
- **Outcome:** AI does the implementation toil; the *process* — approval gates,
  signed provenance, security thresholds, sandboxed execution, audit trail —
  is enforced by the tool, not by hope. Adoptable as a compliance-friendly SDLC.

### 5.5 Enterprise variant — API-key billing org

> A larger org bills via a direct Anthropic API key (volume contract), not
> individual subscriptions.

- **Scenario:** Platform team sets `AIFACTORY_ALLOW_API_KEY=1` on the deployment.
- **Guards that engage:** the auth gate (**G7**) flips from *scrub* to *permit*
  — the key becomes a valid auth source and is passed through to agents — while
  every *other* guard (signing, sandbox, gates, audit) is unchanged.
- **Outcome:** the same governed pipeline, billed the way the enterprise's
  contract requires — a one-flag policy choice, not a fork.

---

## 6. Why this matters

Without the guards, "let an agent build it" is a liability: unbounded loops,
leaked secrets, unreviewed merges, no provenance. The Factory turns it into a
**process**: a human-approved, cryptographically-signed plan; sandboxed,
OAuth-only execution; declared-AC verification with bounded self-correction; and
a reviewer-gated, never-force merge — all audited end to end. That is the
difference between *AI that writes code* and *AI you can adopt as how you ship*.
