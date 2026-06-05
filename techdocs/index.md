# Factory

**The governance, verification & observability layer for the agentic SDLC.**

This is the **program / meta repository** for the Factory family — cross-cutting
plans, epics, RFCs, and the shared **PARR pipeline** (Prepare · Act · Reflect ·
Review) that spans all the products. Work that touches a single product lives in that
product's own repo; work that spans the family lives here. There are **no services
and no API** in this repo — it is documentation and program coordination.

## The family

| Stage | Product | What it does |
|---|---|---|
| 🧭 **Prepare / Plan + Review** | [PFactory](https://github.com/olafkfreund/PFactory) | Governed planning grounded in live cloud/Backstage context, review gates with citations, human approval → governed GitHub issues |
| 🛠️ **Act** | [AIFactory](https://github.com/olafkfreund/AIFactory) | Spec-first plan → code → QA in isolated worktrees; multi-provider; can delegate to other coding agents |
| 🧪 **Reflect / Verify** | [TFactory](https://github.com/olafkfreund/TFactory) | Autonomous test generation + execution, graded on a 5-signal verdict (coverage delta, stability, mutation, lint, semantic relevance) |
| 🛰️ **Review / Observe** | [CFactory](https://github.com/olafkfreund/CFactory) | The control tower — one cockpit threading plan → code → test, with an advise-and-confirm copilot |

## The PARR pipeline

```
PFactory  ──▶  AIFactory  ──▶  TFactory
 (Plan)         (Act)          (Verify)
    └───────── observed & steered by ─────────┘
                     CFactory
```

The four products are independently useful, but their real power is the **handoff
chain**. A shared **correlation key — the GitHub issue number** — threads
`plan → code → branch/PR → tests` end to end, so CFactory can show and steer the
whole pipeline from one place. That connective tissue (a shared correlation key, a
normalized completion-event schema, and a canonical local port map) is the
**PARR spine**, tracked as the program's current focus.

## Where Factory sits in the market

AI code generation is commoditizing fast — and Factory deliberately does **not**
compete there. It sits in the layer *around* the coding agents: **govern → build →
verify → observe.** The 2026 signal is stark — 84% of developers use AI coding tools
but only 29% trust the output, and the EU AI Act's high-risk rules (from Aug 2, 2026)
make logging, human oversight and audit mandatory. That trust-and-governance gap is
the layer Factory occupies.

> **Honest note:** Factory is an early, open project — no market-share or revenue
> claims. We claim a *position*: the trust / governance / observability layer for the
> agentic SDLC, built as composable open products.

See [Architecture](architecture.md), [Dependencies](dependencies.md),
[Decisions](decisions.md) and [API & Contracts](api.md).
