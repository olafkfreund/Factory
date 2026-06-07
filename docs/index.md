---
layout: default
title: Home
---

<style>
.prod-shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin:1.4rem 0}
.prod-shots img{width:100%;height:auto;border-radius:10px;border:1px solid rgba(255,255,255,.10);box-shadow:0 8px 28px rgba(0,0,0,.35)}
.prod-shots figure{margin:0}
.prod-shots figcaption{font-size:.8rem;opacity:.7;margin-top:.35rem;font-family:'JetBrains Mono',monospace}
.prod{padding:1.4rem 0;border-top:1px solid rgba(255,255,255,.08)}
.prod-head{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap}
.prod-head img{height:34px;width:auto}
.prod-tag{font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;opacity:.7;border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:.18rem .6rem}
.parr{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:1.4rem 0}
.parr .step{border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:1rem;background:rgba(255,255,255,.02)}
.parr .step b{display:block;font-size:1.05rem;margin-bottom:.2rem}
.parr .step span{font-size:.8rem;opacity:.7}
</style>

# One factory. Four products. A pipeline you can govern, verify and watch.

The **Factory** family turns an idea into shipped, tested software through a chain
of autonomous services — each useful on its own, each designed to hand off to the
next, all following the **PARR** loop: **P**repare · **A**ct · **R**eflect ·
**R**eview.

<div class="parr">
  <div class="step"><b>🧭 Prepare</b><span>PFactory plans &amp; governs — grounded in your real infrastructure.</span></div>
  <div class="step"><b>🛠️ Act</b><span>AIFactory turns governed issues into merge-ready code.</span></div>
  <div class="step"><b>🧪 Reflect</b><span>TFactory generates &amp; grades tests on a 5-signal verdict.</span></div>
  <div class="step"><b>🛰️ Review</b><span>CFactory observes the whole pipeline and steers it — with you in the loop.</span></div>
</div>

```
PFactory  ──▶  AIFactory  ──▶  TFactory
 (Plan)         (Act)          (Verify)
    └───────────── observed & steered by ─────────────┘
                        CFactory
```

This is the repository for the **whole program** — cross-cutting plans, the shared
pipeline, and the place the four products come together.

---

## The products {#products}

<div class="prod" markdown="1">
<div class="prod-head"><img src="{{ '/assets/logos/pfactory.svg' | relative_url }}" alt="PFactory"><span class="prod-tag">Prepare / Plan + Review</span></div>

### PFactory — governed planning, grounded in your infrastructure

The planning layer that sits **in front of** coding agents. It ingests plans,
enriches them with **live** organizational context (Kubernetes, AWS/Azure/GCP,
Backstage, internal wikis), runs architecture / security / feasibility review
gates **with citations**, records human approval, and emits governed GitHub issues.

- Context-grounded planning from real cloud + catalog state
- Hybrid deterministic + LLM review gates, every verdict cited
- Human-approval gate before any work is emitted
- Kanban board, feasibility &amp; cost estimates, living templates

<div class="prod-shots">
  <figure><img src="{{ '/assets/screenshots/pfactory/01-portal-list.png' | relative_url }}" alt="PFactory portal"><figcaption>portal — plans overview</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/pfactory/09-pipeline.png' | relative_url }}" alt="PFactory pipeline"><figcaption>enrich → decompose → review pipeline</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/pfactory/12-review.png' | relative_url }}" alt="PFactory review gates"><figcaption>review gates with citations</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/pfactory/14-approval.png' | relative_url }}" alt="PFactory approval"><figcaption>human approval gate</figcaption></figure>
</div>

[See the full PFactory tour →]({{ '/pfactory/' | relative_url }}) · [Visit PFactory →](https://pfactory.freundcloud.com/) · [GitHub](https://github.com/olafkfreund/PFactory)
</div>

<div class="prod" markdown="1">
<div class="prod-head"><img src="{{ '/assets/logos/aifactory.png' | relative_url }}" alt="AIFactory"><span class="prod-tag">Act</span></div>

### AIFactory — spec-first execution that ships merge-ready code

The execution engine. A planner writes a reviewable spec, a coder implements it in
an isolated git worktree, and a QA agent validates against the spec — multi-provider,
able to **delegate** to GitHub Copilot or GitLab Duo, and enterprise-grade.

- Spec-first: every run starts from a written, editable spec
- Isolated worktrees — nothing touches main until you merge
- Multi-provider, per-phase model selection; MCP control plane
- Enterprise: SAML/SCIM, tenant isolation, audit, LiteLLM gateway

<div class="prod-shots">
  <figure><img src="{{ '/assets/screenshots/aifactory/board-parr-pipeline.png' | relative_url }}" alt="AIFactory mission control"><figcaption>mission control — the PARR pipeline over the board</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/task-logs.png' | relative_url }}" alt="AIFactory PARR logs"><figcaption>the PARR loop, streamed live</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/task-observability.png' | relative_url }}" alt="AIFactory observability"><figcaption>per-task token &amp; resource observability</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/task-live-console-tests.png' | relative_url }}" alt="AIFactory live console"><figcaption>live agent console — QA suite passing</figcaption></figure>
</div>

[See the full AIFactory tour →]({{ '/aifactory/' | relative_url }}) · [Visit AIFactory →](https://aifactory.freundcloud.com/) · [GitHub](https://github.com/olafkfreund/AIFactory)
</div>

<div class="prod" markdown="1">
<div class="prod-head"><img src="{{ '/assets/logos/tfactory.svg' | relative_url }}" alt="TFactory"><span class="prod-tag">Reflect / Review</span></div>

### TFactory — tests you can trust, not just a green bar

Autonomous test generation + execution across modality lanes (unit, browser, API,
integration, mutation). It grades every generated test on a **5-signal verdict** —
coverage delta, stability re-runs, mutation kills, lint, semantic relevance — and
posts a ranked triage report to your PR.

- Five-signal verdict: meaningful tests, not coverage theatre
- Modality lanes with real evidence (screenshots, video, HAR, mutants)
- Bidirectional handback: failures route back to AIFactory's QA fixer
- Works from any AC source (markdown / Gherkin / EARS) or MCP

<div class="prod-shots">
  <figure><img src="{{ '/assets/screenshots/tfactory/python-unit.gif' | relative_url }}" alt="TFactory unit run"><figcaption>unit lane — generate, run, grade</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/tfactory/polyglot.gif' | relative_url }}" alt="TFactory polyglot run"><figcaption>polyglot — one spec, many languages</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/tfactory/api-gateway.png' | relative_url }}" alt="TFactory API lane"><figcaption>API lane with HAR evidence</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/tfactory/python-unit.png' | relative_url }}" alt="TFactory verdict"><figcaption>graded, ranked triage report</figcaption></figure>
</div>

[See the full TFactory tour →]({{ '/tfactory/' | relative_url }}) · [Visit TFactory →](https://tfactory.freundcloud.com/) · [GitHub](https://github.com/olafkfreund/TFactory)
</div>

<div class="prod" markdown="1">
<div class="prod-head"><img src="{{ '/assets/logos/cfactory.svg' | relative_url }}" alt="CFactory"><span class="prod-tag">Review / Observe &amp; Steer — new</span></div>

### CFactory — the control tower over all three

The newest member and the piece that turns the others into a **suite**. CFactory
threads every unit of work across the three services into one `WorkItem` (keyed by
GitHub issue), shows it on a single live cockpit, and adds an **agentic copilot**
that explains pipeline state and proposes human-confirmed actions.

- One pane of glass: where is every feature across plan → code → test
- Agentic copilot: "why is #182 stuck?", answered from real cross-service state
- Advise + confirm: the copilot prepares actions; a human always clicks
- Built on the family skeleton; reuses AIFactory's enterprise security

<div class="prod-shots">
  <figure><img src="{{ '/assets/screenshots/cfactory/mission-control.png' | relative_url }}" alt="CFactory mission control"><figcaption>mission control — Plan · Code · Test, live</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/cfactory/pipeline.png' | relative_url }}" alt="CFactory pipeline"><figcaption>one work item threaded by GitHub issue</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/cfactory/copilot.png' | relative_url }}" alt="CFactory copilot"><figcaption>agentic copilot — advise &amp; confirm</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/cfactory/audit.png' | relative_url }}" alt="CFactory audit"><figcaption>HMAC-chained audit of every action</figcaption></figure>
</div>

[See the full CFactory tour →]({{ '/cfactory/' | relative_url }}) · [CFactory on GitHub →](https://github.com/olafkfreund/CFactory)
</div>

---

## How they cooperate {#cooperation}

The products are independently useful, but their real power is the **handoff
chain** — the cooperation we're building out:

1. **PFactory → AIFactory.** PFactory emits governed GitHub issues; AIFactory picks
   them up and builds, carrying the issue number as provenance.
2. **AIFactory → TFactory.** A finished feature on a branch is handed to TFactory,
   which generates and grades a test suite against the acceptance criteria.
3. **TFactory → AIFactory (handback).** When tests fail, TFactory routes a
   correction request back to AIFactory's QA fixer — a bounded, closed loop.
4. **CFactory over everything.** A shared **correlation key — the GitHub issue
   number** — threads `plan → code → branch/PR → tests`, so CFactory can show and
   steer the whole pipeline from one place.

```
   PFactory ──issues──▶ AIFactory ──branch/PR──▶ TFactory
       ▲                    │  ▲                     │
       │                    │  └──── handback ───────┘
       └─ correlation key (GitHub issue #) ──────────┘
                    every step observed by CFactory
```

The connective tissue — a shared correlation key, a normalized completion-event
schema, and a canonical local port map — is tracked as the **PARR-spine epic** in
this repo.

[See the program roadmap →](/roadmap/) · [Follow the blog →](/blog/)
