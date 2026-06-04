---
layout: default
title: Why Factory
permalink: /why/
---

<style>
.lead{font-size:1.12rem;opacity:.92}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:1.4rem 0}
.kpi .k{border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:1rem;background:rgba(255,255,255,.02)}
.kpi .k b{display:block;font-size:1.5rem;font-family:'JetBrains Mono',monospace;color:#fabd2f}
.kpi .k span{font-size:.82rem;opacity:.72}
.scn{border-top:1px solid rgba(255,255,255,.08);padding:1.3rem 0}
.scn .who{font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:#83a598}
.cmp{width:100%;border-collapse:collapse;margin:1.3rem 0;font-size:.92rem}
.cmp th,.cmp td{border:1px solid rgba(255,255,255,.12);padding:.6rem .7rem;text-align:left;vertical-align:top}
.cmp th{background:rgba(255,255,255,.04);font-family:'JetBrains Mono',monospace;font-size:.78rem;letter-spacing:.04em}
.cmp td b{color:#8ec07c}
.pill{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:.72rem;border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:.15rem .55rem;opacity:.8;margin-left:.4rem}
</style>

# Why Factory

<p class="lead">AI can write code faster than ever. The hard part is no longer
generation — it's <strong>trusting</strong> what was generated, <strong>governing</strong>
how it was decided, and <strong>proving</strong> it works. Factory is the layer that
does that, around whatever coding agent you use.</p>

## Where we sit

The AI software-development market is splitting into layers. Most money and noise
is in **code generation** — and it's commoditizing fast (Copilot, Cursor, Claude
Code, Codex, Devin). Factory deliberately does **not** compete there. We sit in the
layer *around* the coding agents:

<div class="parr">
  <div class="step"><b>🧭 Govern</b><span>PFactory — plan with live-infra context + review gates + human approval</span></div>
  <div class="step"><b>🛠️ Build</b><span>AIFactory — spec-first execution; or delegate to any coding agent</span></div>
  <div class="step"><b>🧪 Verify</b><span>TFactory — generate &amp; grade tests on a 5-signal verdict</span></div>
  <div class="step"><b>🛰️ Observe</b><span>CFactory — thread, watch and steer the whole pipeline</span></div>
</div>

The opportunity is real and growing: the AI code-tools market is roughly
**$8–10B in 2025–26, heading to $30–91B by 2033–35** (~25–28% CAGR), and the
*agentic* slice grows fastest (~52% CAGR). But the value is migrating from "write
the code" to **"can I trust, govern and verify the code"** — which is exactly the
layer Factory occupies.

> **Honest note:** Factory is an early, open project. We don't claim market share or
> revenue — we claim a *position*: the trust, governance and observability layer for
> the agentic SDLC, built as composable open products.

## The problem we solve

The 2026 data is blunt about where the pain is:

<div class="kpi">
  <div class="k"><b>84% / 29%</b><span>developers <em>using</em> AI coding tools vs those who <em>trust</em> their output (trust down from ~70% in 2023)</span></div>
  <div class="k"><b>66%</b><span>frustrated by AI output that's "almost right, but not quite"</span></div>
  <div class="k"><b>45%</b><span>say debugging AI-generated code takes longer than writing it</span></div>
  <div class="k"><b>Aug 2 2026</b><span>EU AI Act high-risk rules: logging, human oversight &amp; audit become mandatory</span></div>
</div>

The bottleneck has moved from writing to **verifying and governing**. That maps
directly onto the family:

| The pain | What addresses it |
|---|---|
| "Almost-right" code, rework, low trust | **TFactory** — tests graded on coverage delta, stability, mutation, lint & semantic relevance: meaningful tests, not a green bar |
| Ungoverned, context-blind planning ("shadow AI") | **PFactory** — planning grounded in live cloud/Backstage context, review gates with citations, human approval before work is emitted |
| No view of what agents are doing across the SDLC | **CFactory** — one cockpit threading plan → code → test, with an advise-and-confirm copilot |
| Compliance: logging, human oversight, audit trail | **The spine** — human-approval gates, HMAC-anchored audit logs, completion-event records — the evidence the EU AI Act asks for |

## Where we're going

**Near term:** finish the **PARR spine** (one shared correlation key — the GitHub
issue — threading plan→code→test, a normalized event schema, a clean port map),
then ship the **CFactory cockpit** in phases (read-only board → agentic copilot →
advise-and-confirm actions → multi-tenant hardening). See the [roadmap](/roadmap/).

**The bet:** code generation will keep commoditizing; the durable advantage is being
the **governance + verification + observability** layer that makes agentic
development *trustworthy and auditable*. That's where we're investing.

## Real-life scenarios

<p class="lead" style="font-size:.95rem;opacity:.7">Illustrative — these show how a team
would use Factory, not named customers.</p>

<div class="scn" markdown="1">
<span class="who">Solo dev / tiny startup</span>
### Ship fast, but don't ship blind
A founder building an MVP wants AI speed without a trail of untested code. They run
**AIFactory** to turn issues into branches, and **TFactory** to auto-generate and
*grade* tests on every feature — so "done" means "verified," not "it compiled."
Local/BYO models keep cost and data under control. <span class="pill">AIFactory + TFactory</span>
</div>

<div class="scn" markdown="1">
<span class="who">Scale-up · 10–40 engineers</span>
### Keep velocity as the team grows
Merge conflicts, inconsistent specs and "where is this feature?" chaos creep in. They
add **PFactory** so every work item starts from a reviewed, context-grounded plan, and
**CFactory** so the whole team sees plan→code→test on one board. The lead steers
stuck work from the cockpit instead of chasing three dashboards.
<span class="pill">+ PFactory + CFactory</span>
</div>

<div class="scn" markdown="1">
<span class="who">Mid-market · platform team</span>
### Make the golden path the easy path
A platform team encodes standards once: **PFactory** reads their **Backstage** catalog
and golden-path templates, grounding plans in real infrastructure and flagging drift.
Engineers keep their existing editors — Factory plugs in over **MCP** — and the team
**delegates** the coding phase to the agent they already pay for, while keeping
governance and verification in-house. <span class="pill">PFactory + MCP + delegation</span>
</div>

<div class="scn" markdown="1">
<span class="who">Large regulated enterprise · bank / health</span>
### AI velocity that passes audit
Under the **EU AI Act**, AI-assisted delivery needs human oversight, logging and
evidence on demand. Factory provides the controls: **human-approval gates** before
code is emitted, **HMAC-anchored audit logs** and completion-event records, **tenant
isolation** and **SAML/SCIM**, **BYO / air-gapped LLMs** with egress auditing, and a
**credential broker** (Vault / cloud secret managers). CFactory gives risk and
engineering one auditable view of every AI action. <span class="pill">full family + governance spine</span>
</div>

## How we use LLMs &amp; AI

Factory is **model-agnostic by design** — the intelligence is in the *workflow*, not a
single model:

- **Claude Agent SDK** at the core, with a **multi-provider factory** routing by model
  string across Claude, OpenAI, Gemini, Ollama, vLLM, Codex and the Copilot CLI.
- **Per-phase model selection** — a heavy reasoning model to plan, a fast one to code
  or run QA — so you spend tokens where they matter.
- **Patterns over vibes** — spec-first execution, review gates with citations, and
  TFactory's 5-signal verdict turn raw model output into governed, verified work.
- **Enterprise controls** — a LiteLLM gateway for per-org budgets, rate limits,
  allow-lists and PII-redacted audit logs; **BYO / air-gapped** models with an
  egress-audit badge for sensitive environments.

## Integrating newcomers — and adding the next one

The AI tool landscape changes monthly. Factory is built so a **new model or agent is a
small adapter, not a rewrite.** Four extension seams:

1. **New model provider** → a thin adapter in the provider factory; route to it by
   model string. No pipeline changes.
2. **MCP interop** → any MCP-aware editor or agent (Claude Code, Cursor, Continue, …)
   plugs into the control plane today — stdio locally, plus a remote HTTP+SSE server
   with scoped API keys.
3. **Executor delegation** → slot a new coding agent (e.g. GitHub Copilot Coding
   Agent, GitLab Duo) in as AIFactory's builder while keeping governance and
   verification in the family.
4. **BYO / local** → point at your own endpoint through the credential broker
   (Vault, Azure Key Vault, AWS/GCP secret managers, sops/age).

When the next breakout model or agent ships, you adopt it by configuration — and keep
the trust layer you already have.

## Why choose us

We **complement** the coding agents you already use — we don't ask you to replace them:

<table class="cmp">
  <thead><tr><th>Layer</th><th>Tools in this layer</th><th>Factory's role</th></tr></thead>
  <tbody>
    <tr><td>Code generation</td><td>Copilot, Cursor, Claude Code, Codex, Devin</td><td><b>Orchestrate &amp; wrap them</b> — AIFactory runs or delegates to them, spec-first and isolated</td></tr>
    <tr><td>Spec / planning</td><td>Spec-Kit, Kiro, Tessl, BMAD</td><td><b>PFactory</b> adds live-infra grounding, review gates with citations, and a human-approval gate</td></tr>
    <tr><td>Test / QA</td><td>XBOW, Momentic, self-healing test tools</td><td><b>TFactory</b> grades tests on a 5-signal verdict — meaningful coverage, not a green bar</td></tr>
    <tr><td>Observability</td><td>LangSmith, Langfuse, AgentOps</td><td><b>CFactory</b> threads the cross-product pipeline and adds advise-and-confirm control</td></tr>
    <tr><td>Governance / audit</td><td>(mostly manual today)</td><td><b>The spine</b> — human gates, audit logs, EU AI Act-ready evidence</td></tr>
  </tbody>
</table>

**The one-liner:** *Factory is the governance, verification and observability layer for
the agentic SDLC — so you can move at AI speed and still trust, prove and audit what
ships.*

[Meet the products →](/#products) &nbsp;·&nbsp; [See the roadmap →](/roadmap/) &nbsp;·&nbsp; [Read the blog →](/blog/)

---

### Sources

Market size: [SkyQuest](https://www.skyquestt.com/report/ai-code-tools-market) ·
[Precedence Research](https://www.precedenceresearch.com/ai-code-tools-market) ·
[Gartner — enterprise AI coding agents](https://www.gartner.com/en/articles/enterprise-ai-coding-agent-market).
Trust / verification gap: [Uvik](https://uvik.net/blog/ai-coding-assistant-statistics/) ·
[Sonar State of Code 2026](https://www.sonarsource.com/state-of-code-developer-survey-report.pdf) ·
[DigitalApplied](https://www.digitalapplied.com/blog/ai-coding-adoption-statistics-2026-50-data-points).
EU AI Act: [European Commission](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai) ·
[artificialintelligenceact.eu](https://artificialintelligenceact.eu/).
Agentic SDLC: [HCLTech](https://www.hcltech.com/trends-and-insights/autonomous-software-factory-agentic-ai-sdlc) ·
[Microsoft](https://techcommunity.microsoft.com/blog/appsonazureblog/an-ai-led-sdlc-building-an-end-to-end-agentic-software-development-lifecycle-wit/4491896).
Autonomous QA: [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/08/momentic-autonomous-qa-agent-testing-market-2026).
