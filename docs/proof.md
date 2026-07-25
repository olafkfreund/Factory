---
layout: default
title: Proof
permalink: /proof/
mermaid: true
---

<style>
.lead{font-size:1.12rem;opacity:.92;max-width:48rem}
.lead b{color:#ebdbb2}
.oneliner{border-left:3px solid #fe8019;padding:.4rem 0 .4rem 1rem;margin:1.4rem 0;font-size:1.05rem;opacity:.95}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:1.4rem 0}
.kpi .k{border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:1rem;background:rgba(255,255,255,.02)}
.kpi .k b{display:block;font-size:1.5rem;font-family:'JetBrains Mono',monospace;color:#fabd2f}
.kpi .k span{font-size:.82rem;opacity:.72}
.cmp{width:100%;border-collapse:collapse;margin:1.3rem 0;font-size:.9rem;display:block;overflow-x:auto}
.cmp th,.cmp td{border:1px solid rgba(255,255,255,.12);padding:.55rem .65rem;text-align:left;vertical-align:top}
.cmp th{background:rgba(255,255,255,.04);font-family:'JetBrains Mono',monospace;font-size:.76rem;letter-spacing:.03em}
.cmp td.dim{font-family:'JetBrains Mono',monospace;font-size:.8rem;opacity:.85;white-space:nowrap}
.cmp .yes{color:#8ec07c;font-weight:600}
.cmp .no{color:#fb4934}
.cmp .part{color:#fabd2f}
.proof-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;margin:1.2rem 0}
.proof-grid figure{margin:0;border:1px solid rgba(255,255,255,.10);border-radius:12px;overflow:hidden;background:rgba(255,255,255,.02)}
.proof-grid img{width:100%;height:auto;display:block;border-bottom:1px solid rgba(255,255,255,.07)}
.proof-grid figcaption{font-size:.82rem;opacity:.82;padding:.6rem .75rem;line-height:1.4}
.proof-grid figcaption b{color:#83a598}
.flagship{margin:1.4rem 0;border:1px solid rgba(254,128,25,.35);border-radius:14px;overflow:hidden;background:rgba(255,255,255,.02)}
.flagship img{width:100%;height:auto;display:block}
.flagship figcaption{font-size:.86rem;opacity:.85;padding:.7rem .9rem;line-height:1.45}
.flagship figcaption b{color:#fe8019}
.honest{border:1px solid rgba(250,189,47,.3);border-radius:12px;padding:1rem 1.2rem;margin:1.4rem 0;background:rgba(250,189,47,.04)}
.honest ul{margin:.5rem 0 0;padding-left:1.1rem}
.honest li{margin:.35rem 0;font-size:.92rem}
.deep{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin:1.2rem 0}
.deep a{display:block;border:1px solid rgba(255,255,255,.12);border-radius:10px;padding:.7rem .9rem;text-decoration:none;background:rgba(255,255,255,.02)}
.deep a b{display:block;color:#8ec07c;font-size:.95rem}
.deep a span{font-size:.78rem;opacity:.68}
</style>

# Proof

<p class="lead">If you distrust demos, start here. This page is the position, the
proof, and the honesty in one place — with the caveats left in. Everything below
either links to a running product doc or embeds a recording captured from the live
fleet. <b>We claim a position, not market share.</b></p>

<p class="oneliner">The self-hosted governance and verification layer for autonomous
coding: the factory that <b>runs your agents' code</b>, <b>tests it for real</b>, and
<b>refuses to overclaim</b>. Trust-verified, not code-faster.</p>

## The gap we sit in

The 2026 data says buyers already have agents — what they lack is a way to trust them.

<div class="kpi">
  <div class="k"><b>84% / 29%</b><span>developers using AI coding tools vs those who trust the output</span></div>
  <div class="k"><b>81% / 14.4%</b><span>teams with agents deployed vs teams with security approval for them</span></div>
  <div class="k"><b>53%</b><span>of deployed agents run unmonitored</span></div>
  <div class="k"><b>25–45%</b><span>the gap between SWE-bench scores and real production reliability</span></div>
  <div class="k"><b>Aug 2 2026</b><span>EU AI Act high-risk rules: logging, human oversight and audit become mandatory</span></div>
</div>

Two axes decide the market: **where the code runs** (someone else's cloud vs your
own infrastructure) and **what the product optimizes for** (writing code faster vs
proving the code is trustworthy). Almost every vendor clusters in the SaaS +
code-faster corner. The self-hosted **and** verification-first quadrant is nearly
empty. That is where Factory sits.

<div class="mermaid">
quadrantChart
    title Where the tools cluster
    x-axis "SaaS / vendor cloud" --> "Self-hosted / your infra"
    y-axis "Optimize: code faster" --> "Optimize: trust and verify"
    quadrant-1 "Empty quadrant"
    quadrant-2 "Compliance suites"
    quadrant-3 "SaaS agent platforms"
    quadrant-4 "Self-hosted coding agents"
    "SWE-bench vendors": [0.22, 0.18]
    "SaaS agent platforms": [0.30, 0.34]
    "Local coding agents": [0.74, 0.28]
    "Factory": [0.80, 0.82]
</div>

<p style="font-size:.82rem;opacity:.65">The upper-right quadrant — self-hosted and
verification-first — is the position. Dot placement is illustrative of category, not
a benchmarked score.</p>

## Factory vs the alternatives

Scored on the dimensions a skeptical engineering buyer actually asks about. We only
mark <span class="yes">Yes</span> where the fleet does the thing today.

<table class="cmp">
  <thead>
    <tr>
      <th>Dimension</th>
      <th>Factory</th>
      <th>SWE-bench-score vendors</th>
      <th>SaaS agent platforms</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td class="dim">Self-hosted</td>
      <td class="yes">Yes — runs on your own k8s; local models via Ollama</td>
      <td class="no">No — hosted service</td>
      <td class="part">Rarely — cloud-first, some enterprise VPC</td>
    </tr>
    <tr>
      <td class="dim">Independent verification</td>
      <td class="yes">Yes — TFactory is a separate product that grades AIFactory's output; builder never signs its own homework</td>
      <td class="no">No — vendor reports its own benchmark score</td>
      <td class="no">No — the system that writes also declares "done"</td>
    </tr>
    <tr>
      <td class="dim">Real test execution</td>
      <td class="yes">Yes — tests generated and run in a per-task sandbox (Nix env), graded on a 5-signal verdict</td>
      <td class="part">Benchmark harness only — not your repo</td>
      <td class="part">Varies — often lint/build, not a graded test verdict</td>
    </tr>
    <tr>
      <td class="dim">Governance / HITL</td>
      <td class="yes">Yes — PFactory review gates with citations; human approval before code is emitted; approve/merge in the cockpit</td>
      <td class="no">No — score in, patch out</td>
      <td class="part">Some — PR review after the fact, not a gate before work</td>
    </tr>
    <tr>
      <td class="dim">Audit / evidence</td>
      <td class="yes">Yes — HMAC-anchored audit log, completion-event records, screenshot evidence for browser tests</td>
      <td class="no">No</td>
      <td class="part">Limited — activity logs, rarely tamper-evident</td>
    </tr>
    <tr>
      <td class="dim">Data-egress control</td>
      <td class="yes">Yes — self-hosted with local models; code and prompts need never leave your cluster</td>
      <td class="no">No — code goes to the vendor</td>
      <td class="no">No — cloud by default</td>
    </tr>
    <tr>
      <td class="dim">Refuses to overclaim</td>
      <td class="yes">Yes — verification-core drift guard on the never-overclaim path; VAL assurance levels; false-failed builds fixed rather than hidden</td>
      <td class="no">No — optimized to the leaderboard</td>
      <td class="no">No — "done" is asserted, not proven</td>
    </tr>
  </tbody>
</table>

## The proof, recorded

Captured from the running fleet. Nothing here is a mockup.

<figure class="flagship">
  <img src="{{ '/assets/demos/parr-deploy-then-verify.gif' | relative_url }}" alt="PARR pipeline deploying a service and then verifying it against the live endpoint" loading="lazy">
  <figcaption><b>Flagship — deploy, then verify.</b> One task driven through the whole
  PARR pipeline: planned and governed, built, deployed, then <b>tested against the live
  endpoint</b>. This is the core claim in motion — the factory runs the code it wrote and
  checks it for real, rather than declaring success on a green build.</figcaption>
</figure>

<div class="proof-grid">
  <figure>
    <img src="{{ '/assets/screenshots/tfactory/python-unit.gif' | relative_url }}" alt="TFactory generating and running Python unit tests" loading="lazy">
    <figcaption><b>Real test execution.</b> TFactory generating and running unit tests in a
    sandbox, then grading them — coverage delta, stability, mutation, lint and semantic
    relevance — not just a passing bar.</figcaption>
  </figure>
  <figure>
    <img src="{{ '/assets/screenshots/tfactory/polyglot.gif' | relative_url }}" alt="TFactory verifying multiple languages" loading="lazy">
    <figcaption><b>Polyglot, same verdict.</b> The same graded verification across
    languages — the test lane is language-aware, provisioned per task via Nix.</figcaption>
  </figure>
  <figure>
    <img src="{{ '/assets/screenshots/evidence/mfa-otp-challenge.png' | relative_url }}" alt="Browser test solving an MFA one-time-password challenge" loading="lazy">
    <figcaption><b>Evidence, not assertion.</b> A browser test logging in through a real
    MFA one-time-password challenge — proof the agent exercised the authenticated UI, not a
    stubbed page.</figcaption>
  </figure>
  <figure>
    <img src="{{ '/assets/screenshots/evidence/mfa-authenticated-account.png' | relative_url }}" alt="Authenticated account page reached after MFA login" loading="lazy">
    <figcaption><b>The authenticated result.</b> The account page the browser test reached
    after passing MFA — captured as a screenshot artifact attached to the run.</figcaption>
  </figure>
  <figure>
    <img src="{{ '/assets/screenshots/cfactory/mission-control.png' | relative_url }}" alt="CFactory cockpit mission control view" loading="lazy">
    <figcaption><b>You can watch it.</b> The CFactory cockpit threads plan to code to test
    for every task — the observability the "53% run unmonitored" statistic is missing.</figcaption>
  </figure>
  <figure>
    <img src="{{ '/assets/screenshots/cfactory/audit.png' | relative_url }}" alt="CFactory audit log view" loading="lazy">
    <figcaption><b>Audit trail.</b> Human-approval gates and completion events land in an
    HMAC-anchored audit log — the logging and oversight the EU AI Act asks for.</figcaption>
  </figure>
</div>

### One task, end to end

<div class="proof-grid">
  <figure>
    <img src="{{ '/assets/screenshots/tour/flow/01-pfactory-plan.png' | relative_url }}" alt="PFactory plan detail" loading="lazy">
    <figcaption><b>Prepare.</b> PFactory decomposes the plan into acceptance criteria and
    child issues; review gates pass before any code is emitted.</figcaption>
  </figure>
  <figure>
    <img src="{{ '/assets/screenshots/tour/flow/02-aifactory-subtasks.png' | relative_url }}" alt="AIFactory subtasks" loading="lazy">
    <figcaption><b>Act.</b> AIFactory builds it subtask by subtask against the signed plan.</figcaption>
  </figure>
  <figure>
    <img src="{{ '/assets/screenshots/tour/flow/04-tfactory-report.png' | relative_url }}" alt="TFactory verification report" loading="lazy">
    <figcaption><b>Reflect.</b> TFactory verifies the build and returns a graded verdict —
    with a bounded handback to the coder on failure.</figcaption>
  </figure>
  <figure>
    <img src="{{ '/assets/screenshots/tour/flow/05-cfactory-dag.png' | relative_url }}" alt="CFactory execution DAG" loading="lazy">
    <figcaption><b>Review.</b> The whole run as a live execution DAG in the cockpit, one
    correlation key threading plan to code to test.</figcaption>
  </figure>
</div>

### Proven on real clouds

<div class="proof-grid">
  <figure>
    <img src="{{ '/assets/screenshots/parr-clouds/azure-landing.png' | relative_url }}" alt="Service deployed to Azure" loading="lazy">
    <figcaption><b>Azure.</b> A factory-built service running on real Azure infrastructure,
    then torn down.</figcaption>
  </figure>
  <figure>
    <img src="{{ '/assets/screenshots/parr-clouds/gcp-game-won.png' | relative_url }}" alt="Service deployed to GCP" loading="lazy">
    <figcaption><b>GCP.</b> The same pipeline deploying and verifying against live Google
    Cloud, provider-agnostic through the plan.</figcaption>
  </figure>
</div>

## What we do NOT claim yet

The caps are the trust signal. We would rather show you the ceiling than let a demo
imply we cleared it.

<div class="honest" markdown="0">
  <ul>
    <li><b>Verification assurance is capped at VAL-2.</b> Higher assurance levels are
    designed but not yet the default — we do not claim VAL-3 evidence.</li>
    <li><b>Deployment is dry-run first.</b> The deploy lane plans and dry-runs real
    infrastructure; full unattended production rollout is deliberately gated, not "click
    once and ship."</li>
    <li><b>Concurrency is bounded.</b> Per-task Nix environments on a single node cap
    throughput at roughly a handful of concurrent tasks today — scaling is in progress,
    not finished.</li>
    <li><b>It is an early, open project.</b> No revenue, market-share or named-customer
    claims. The scenarios in these docs are illustrative of how a team would use Factory.</li>
  </ul>
</div>

## Go deeper

<div class="deep" markdown="0">
  <a href="{{ '/why/' | relative_url }}"><b>Why Factory</b><span>The position and the market thesis</span></a>
  <a href="{{ '/architecture/' | relative_url }}"><b>Architecture</b><span>The cross-repo PARR pipeline</span></a>
  <a href="{{ '/pipeline/' | relative_url }}"><b>Pipeline and guards</b><span>How work moves and where the gates are</span></a>
  <a href="{{ '/tour/' | relative_url }}"><b>Portal tour</b><span>Every portal captured live</span></a>
  <a href="{{ '/tfactory/' | relative_url }}"><b>TFactory</b><span>The verification product in depth</span></a>
  <a href="{{ '/pfactory/' | relative_url }}"><b>PFactory</b><span>Governed, context-aware planning</span></a>
</div>
