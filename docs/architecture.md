---
layout: default
title: Architecture
permalink: /architecture/
mermaid: true
---

# Cross-repo architecture

Factory is a **program / meta repository** — it ships documentation, RFCs and
cross-cutting plans, not running software. Its architecture *is* the **PARR
pipeline**: four independently useful products that hand one unit of work off to
one another, with a fifth concern — **observability** — watching over all of them
from CFactory, the control tower.

**P**repare · **A**ct · **R**eflect · **R**eview — one stage per product.

## The PARR flow

<div class="mermaid">
flowchart LR
    subgraph P["🧭 Prepare"]
        PF["PFactory<br/>:3114 · :3115"]
    end
    subgraph A["🛠️ Act"]
        AF["AIFactory<br/>:3101"]
    end
    subgraph R["🧪 Reflect / Verify"]
        TF["TFactory<br/>:3103"]
    end

    PF -- "governed GitHub issue" --> AF
    AF -- "merge-ready branch / PR" --> TF
    TF -. "handback · failing verdict" .-> AF

    CF["🛰️ CFactory — control tower<br/>:3110 API · :3111 stream"]
    PF -. "completion event" .-> CF
    AF -. "completion event" .-> CF
    TF -. "completion event" .-> CF

    classDef tower fill:#1d2b3a,stroke:#5aa9e6,color:#cde4ff;
    class CF tower;
</div>

Prepare → Act → Reflect run left to right. The dotted return arrow is the
**handback**: when TFactory's verdict fails, it routes a bounded correction
request back to AIFactory's QA fixer. Every stage emits a **completion event** to
CFactory, which observes and steers the whole pipeline from the side.

| Stage | Product | Inputs → Outputs |
|---|---|---|
| Prepare | **PFactory** | plan (docx/pdf/md, MCP, issue) → enrich (live cloud/Backstage) → **reconnoiter the target repo statically** (RFC-0010, code-aware) → review gates (cited) → human approval → **governed GitHub issues** |
| Act | **AIFactory** | governed issue → spec → code in isolated worktree → QA → **merge-ready branch / PR** |
| Reflect | **TFactory** | finished feature on a branch → generate + run tests across modality lanes → **5-signal verdict + triage report** |
| Review | **CFactory** | reads completion events + state from all three → **one cockpit `WorkItem` view + advise-and-confirm copilot** |

## CFactory: the control tower

CFactory never sits *in* the critical path — it watches it. Each product fires
**one** terminal completion event when its stage finishes, best-effort over a
webhook (with a same-host `COMPLETED.json` sentinel as fallback). CFactory dedups
them idempotently and threads them into a single `WorkItem` view.

<div class="mermaid">
flowchart TB
    PF["PFactory"] -- "POST /api/events/completion" --> COL
    AF["AIFactory"] -- "POST /api/events/completion" --> COL
    TF["TFactory"] -- "POST /api/events/completion" --> COL
    TF -. "COMPLETED.json sentinel<br/>(same-host fallback)" .-> COL

    subgraph CF["CFactory control tower · :3110 / :3111"]
        direction TB
        COL["Completion-event collector"]
        IDEM["Idempotent dedup<br/>(service, correlation_key, status)"]
        STORE["WorkItem store<br/>keyed by correlation key"]
        COCKPIT["Cockpit + advise-and-confirm copilot"]
        COL --> IDEM --> STORE --> COCKPIT
    end

    classDef tower fill:#1d2b3a,stroke:#5aa9e6,color:#cde4ff;
    class CF tower;
</div>

Events are **idempotent** by `(service, correlation_key, status)` and consumers
must ignore unknown fields, so adding a new product — or a new field — never forces
a breaking change. See [RFC-0001](rfc/0001-correlation-key-and-completion-event.md).

A successful terminal event must also carry **evidence** that the stage really ran —
issues created (plan), non-zero tokens and completed phases (build), a non-null
verdict and executed tests (verify). Consumers treat a "passed" without satisfying
evidence as **unproven**, never green. This rule is implemented across all three
producers; see
[RFC-0001a — completion-event evidence gates](rfc/0001a-completion-evidence-gates.md).

## The correlation key — the thread through everything

The connective tissue is a single **correlation key: the GitHub issue number** of
the governed work item, threaded end to end. Before an issue exists, services emit
a stable synthetic key (`pf-…`, `af-…`, `tf-…`) and reconcile to the real number
once assigned.

<div class="mermaid">
flowchart LR
    A["pfactory<br/>session_id"] --> B["GitHub<br/>issue #"]
    B --> C["aifactory<br/>task_id"]
    C --> D["branch /<br/>PR #"]
    D --> E["tfactory<br/>spec_id"]

    classDef key fill:#2a2a1a,stroke:#fabd2f,color:#fdf3c5;
    class B key;
</div>

That one key is what lets CFactory show — and steer — `plan → code → branch/PR →
tests` from a single place. It is also what lets the cockpit draw a **live
execution diagram** per unit of work: each producer exposes its subtask graph and
timing on a shared `graph` field of `/api/workitems/{key}/process`, and the
task-detail view animates whichever stage is furthest along (test → code → plan).
See the [live execution diagrams design](plans/2026-06-14-live-execution-diagrams.md).

## Canonical local port map

Fixed, non-overlapping ports let all four products run side by side and let
CFactory reach them all.

| Product | Backend port(s) | Stage |
|---|---|---|
| AIFactory | `3101` | Act |
| TFactory | `3103` | Verify |
| CFactory | `3110` (API) / `3111` (stream) | Cockpit |
| PFactory | `3114` (API) / `3115` (frontend) | Plan |

## Going deeper

- [RFC-0001 — correlation key & completion event](rfc/0001-correlation-key-and-completion-event.md)
- [RFC-0002 — Factory Task Contract v2](rfc/0002-task-contract.md)
- [RFC-0005 — environment manifest & toolchain provisioning](rfc/0005-environment-manifest-and-toolchain-provisioning.md)
- [RFC-0006 — verification assurance levels & honest reporting](rfc/0006-verification-assurance-levels.md)
- [RFC-0007 — access discovery & authenticated-test provisioning](rfc/0007-access-and-credential-provisioning.md)
- [RFC-0010 — code-aware planning over existing repositories](rfc/0010-code-aware-planning-and-behavioral-equivalence.md)
- [How they cooperate](/#cooperation) · [Run locally](run-locally.md) · [Roadmap](roadmap.md)
