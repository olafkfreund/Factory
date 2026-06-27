---
layout: default
title: Home
mermaid: true
---

<style>
.hero{position:relative;padding:2.6rem 0 1.2rem;text-align:left}
.hero .eyebrow{font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.22em;text-transform:uppercase;color:#fe8019;opacity:.95;margin-bottom:.7rem}
.hero h1{font-size:clamp(2rem,5vw,3.4rem);line-height:1.05;font-weight:800;margin:.2rem 0 .6rem;
  background:linear-gradient(100deg,#b8bb26 0%,#83a598 38%,#fabd2f 70%,#fe8019 100%);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
  background-size:200% auto;animation:heroSheen 7s linear infinite}
@keyframes heroSheen{to{background-position:200% center}}
.hero .lede{font-size:1.12rem;max-width:46rem;opacity:.92}
.hero .lede b{color:#ebdbb2}
.hero .chips{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:1rem}
.hero .chips span{font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.06em;
  border:1px solid rgba(255,255,255,.16);border-radius:999px;padding:.28rem .7rem;background:rgba(255,255,255,.03)}
.hero .chips span.p{color:#83a598}.hero .chips span.a{color:#fe8019}.hero .chips span.r{color:#b8bb26}.hero .chips span.v{color:#fabd2f}
.prod-shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin:1.4rem 0}
.prod-shots img{width:100%;height:auto;border-radius:10px;border:1px solid rgba(255,255,255,.10);box-shadow:0 8px 28px rgba(0,0,0,.35)}
.prod-shots figure{margin:0}
.prod-shots figcaption{font-size:.8rem;opacity:.7;margin-top:.35rem;font-family:'JetBrains Mono',monospace}
.prod{padding:1.4rem 0;border-top:1px solid rgba(255,255,255,.08)}
.prod-head{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap}
.prod-head img{height:34px;width:auto}
.prod-tag{font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;opacity:.7;border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:.18rem .6rem}
.parr{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:14px;margin:1.6rem 0}
.parr .step{position:relative;border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:1.05rem 1rem 1.05rem 1.15rem;
  background:rgba(255,255,255,.02);overflow:hidden;isolation:isolate;
  animation:parrRise .55s cubic-bezier(.2,.7,.3,1) both;transition:transform .25s ease,border-color .25s ease,box-shadow .25s ease}
.parr .step::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--c);box-shadow:0 0 12px var(--c)}
.parr .step::after{content:"";position:absolute;inset:0;z-index:-1;opacity:0;
  background:radial-gradient(130% 90% at 0% 0%,var(--c) 0%,transparent 58%);
  animation:parrFlow 5.2s ease-in-out infinite}
.parr .step .pill{display:inline-flex;align-items:center;justify-content:center;width:1.55rem;height:1.55rem;border-radius:7px;
  font-family:'JetBrains Mono',monospace;font-weight:700;font-size:.84rem;color:#1b1b1b;background:var(--c);margin-bottom:.55rem;
  box-shadow:0 0 14px color-mix(in srgb,var(--c) 55%,transparent)}
.parr .step b{display:block;font-size:1.06rem;margin-bottom:.22rem;color:var(--c)}
.parr .step span{font-size:.8rem;opacity:.72;line-height:1.35}
.parr .step:hover{transform:translateY(-4px);border-color:var(--c);box-shadow:0 10px 30px rgba(0,0,0,.4)}
.parr .step:nth-child(1){--c:#83a598;animation-delay:.00s}
.parr .step:nth-child(2){--c:#fe8019;animation-delay:.10s}
.parr .step:nth-child(3){--c:#b8bb26;animation-delay:.20s}
.parr .step:nth-child(4){--c:#fabd2f;animation-delay:.30s}
.parr .step:nth-child(1)::after{animation-delay:0s}
.parr .step:nth-child(2)::after{animation-delay:1.3s}
.parr .step:nth-child(3)::after{animation-delay:2.6s}
.parr .step:nth-child(4)::after{animation-delay:3.9s}
@keyframes parrRise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
@keyframes parrFlow{0%{opacity:0}4%{opacity:.24}16%{opacity:.05}24%,100%{opacity:0}}
@media (prefers-reduced-motion:reduce){.parr .step,.parr .step::after,.hero h1{animation:none}}
</style>

<div class="hero" markdown="0">
  <div class="eyebrow">An idea in. Shipped, tested software out.</div>
  <h1>One factory.<br>Four products.<br>A pipeline you can govern.</h1>
  <p class="lede">The <b>Factory</b> family turns a plan into <b>merge-ready, verified</b> software
  through a chain of autonomous services — each useful on its own, each built to hand off to the
  next, all following the <b>PARR</b> loop.</p>
  <div class="chips">
    <span class="p">PFactory · Prepare</span>
    <span class="a">AIFactory · Act</span>
    <span class="r">TFactory · Reflect</span>
    <span class="v">CFactory · Review</span>
  </div>
</div>

<div class="parr">
  <div class="step"><span class="pill">P</span><b>Prepare</b><span>PFactory plans &amp; governs — grounded in your real infrastructure.</span></div>
  <div class="step"><span class="pill">A</span><b>Act</b><span>AIFactory turns governed issues into merge-ready code.</span></div>
  <div class="step"><span class="pill">R</span><b>Reflect</b><span>TFactory generates &amp; grades tests on a 5-signal verdict.</span></div>
  <div class="step"><span class="pill">R</span><b>Review</b><span>CFactory observes the whole pipeline and steers it — with you in the loop.</span></div>
</div>

```mermaid
flowchart LR
    P["PFactory<br/>Prepare · Plan"] --> A["AIFactory<br/>Act · Code"]
    A --> T["TFactory<br/>Reflect · Verify"]
    T --> S(["Shipped"])
    C["CFactory · Review<br/>observe &amp; steer"] -.-> P
    C -.-> A
    C -.-> T
    classDef pf fill:#83a598,stroke:#5f8175,color:#1b1b1b,font-weight:bold;
    classDef af fill:#fe8019,stroke:#c4641a,color:#1b1b1b,font-weight:bold;
    classDef tf fill:#b8bb26,stroke:#8d9020,color:#1b1b1b,font-weight:bold;
    classDef cf fill:#fabd2f,stroke:#c69526,color:#1b1b1b,font-weight:bold;
    classDef sh fill:#1b1b1b,stroke:#b8bb26,color:#b8bb26,font-weight:bold;
    class P pf; class A af; class T tf; class C cf; class S sh;
```

This is the repository for the **whole program** — cross-cutting plans, the shared
pipeline, and the place the four products come together.

 **New:** [**The Guarded PARR Pipeline**](/pipeline/) — every step and decision
from handover to merge, the sixteen guards that protect task & execution, and
real adoption scenarios from solo builders to regulated enterprises.

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

The **swappable execution core** — the Act stage of the pipeline. A planner writes a
reviewable spec, a coder implements it in an isolated git worktree, and a QA agent
validates against the spec — multi-provider, able to **delegate** to GitHub Copilot
or GitLab Duo, and enterprise-grade. Because Prepare, Reflect and Review live in
separate products, the engine that actually writes code can be replaced without
touching the governance, verification or observability around it.

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

<div class="mermaid">
flowchart LR
    PF["PFactory"] -- "issue #" --> AF["AIFactory"]
    AF -- "branch / PR · issue #" --> TF["TFactory"]
    TF -. "handback" .-> AF
    C["CFactory<br/>observes every step ·<br/>threads by issue #"] -.-> PF
    C -.-> AF
    C -.-> TF
    classDef pf fill:#83a598,stroke:#5f8175,color:#1b1b1b,font-weight:bold;
    classDef af fill:#fe8019,stroke:#c4641a,color:#1b1b1b,font-weight:bold;
    classDef tf fill:#b8bb26,stroke:#8d9020,color:#1b1b1b,font-weight:bold;
    classDef cf fill:#fabd2f,stroke:#c69526,color:#1b1b1b,font-weight:bold;
    class PF pf; class AF af; class TF tf; class C cf;
</div>

The connective tissue — a shared correlation key, a normalized completion-event
schema, and a canonical local port map — is tracked as the **PARR-spine epic** in
this repo.

[See the full architecture →](/architecture/) · [Program roadmap →](/roadmap/) · [Follow the blog →](/blog/)
