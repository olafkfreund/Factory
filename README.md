<div align="center">

<img src="docs/assets/logo.svg" width="84" alt="Factory">

# Factory

**The governance, verification & observability layer for the agentic SDLC.**

Move at AI speed — and still trust, prove and audit what ships.

[Website](https://factory.freundcloud.com/) ·
[Why Factory](https://factory.freundcloud.com/why/) ·
[Roadmap](https://factory.freundcloud.com/roadmap/) ·
[Blog](https://factory.freundcloud.com/blog/)

</div>

---

This is the **program/meta repository** for the Factory family — cross-cutting plans,
epics, and the shared **PARR pipeline** (Prepare · Act · Reflect · Review) that spans
all the products. Work that touches a single product lives in that product's repo;
work that spans the family lives here.

## The family

| Stage | Product | What it does |
|------|---------|--------------|
| 🧭 **Prepare / Plan + Review** | [PFactory](https://github.com/olafkfreund/PFactory) | Governed planning grounded in live cloud/Backstage context, review gates with citations, human approval → governed GitHub issues |
| 🛠️ **Act** | [AIFactory](https://github.com/olafkfreund/AIFactory) | Spec-first plan → code → QA in isolated worktrees; multi-provider; can delegate to other coding agents |
| 🧪 **Reflect / Review** | [TFactory](https://github.com/olafkfreund/TFactory) | Autonomous test generation + execution, graded on a 5-signal verdict (coverage delta, stability, mutation, lint, semantic relevance) |
| 🛰️ **Review / Observe** | [CFactory](https://github.com/olafkfreund/CFactory) | The control tower — one cockpit threading plan→code→test, with an advise-and-confirm copilot |

```
PFactory ──▶ AIFactory ──▶ TFactory          … all observed & steered by …  CFactory
 (Plan)        (Act)        (Verify)                                          (Cockpit)
```

## Where we sit in the market

AI code generation is commoditizing fast — and Factory deliberately does **not**
compete there. We sit in the layer *around* the coding agents: **govern → build →
verify → observe.**

The market is large and growing (AI code tools ≈ **$8–10B in 2025–26 → $30–91B by
2033–35**), but the value is migrating from *writing* code to **trusting, governing
and verifying** it. The 2026 signal is stark: **84% of developers use AI coding tools,
but only 29% trust the output**; verification is the bottleneck; and the **EU AI Act**
(high-risk rules from **Aug 2, 2026**) makes logging, human oversight and audit
mandatory. That trust-and-governance gap is the layer Factory occupies.

> **Honest note:** Factory is an early, open project — no market-share or revenue claims.
> We claim a *position*: the trust/governance/observability layer for the agentic SDLC.

## Why choose us

- **Complement, don't replace** — wrap the coding agents you already use (Copilot,
  Cursor, Claude Code, Codex, Devin) rather than competing with them.
- **Trust by construction** — review gates + human approval (PFactory), a 5-signal test
  verdict (TFactory), and cross-pipeline observability (CFactory).
- **Audit-ready** — human-approval gates, HMAC-anchored audit logs and completion-event
  records: the evidence the EU AI Act asks for.
- **Model-agnostic & future-proof** — a multi-provider factory (Claude, OpenAI, Gemini,
  Ollama, vLLM, Codex, Copilot CLI), MCP interop, executor delegation, and BYO/air-gapped
  models. A new model or agent is a small adapter, not a rewrite.

→ Full positioning, real-life scenarios (solo dev → regulated enterprise), and the
integration story: **[factory.freundcloud.com/why](https://factory.freundcloud.com/why/)**

## Repository layout

- `docs/` — the Jekyll site published at [factory.freundcloud.com](https://factory.freundcloud.com/)
- Program planning & cross-cutting epics — see [Issues](https://github.com/olafkfreund/Factory/issues)
  and the [Factory Program board](https://github.com/users/olafkfreund/projects/1)

## Project management

The family is managed as one program across five repos on a single
[GitHub Project](https://github.com/users/olafkfreund/projects/1). Cross-cutting epics
live here in `Factory`; product-specific work lives in each product repo and is linked
up via cross-repo sub-issues. The current focus is the **PARR spine** (a shared
correlation key, a normalized completion-event schema, and a canonical port map) that
lets the four products cooperate — and lets CFactory observe them.
