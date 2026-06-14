---
layout: default
title: CFactory — the cockpit tour
---

<style>
.tour-hero{margin:1.6rem 0 0.4rem}
.tour-hero img{width:100%;height:auto;border-radius:14px;border:1px solid rgba(255,255,255,.12);box-shadow:0 14px 50px rgba(0,0,0,.45)}
.tour-hero figcaption{font-size:.82rem;opacity:.7;margin-top:.5rem;font-family:'JetBrains Mono',monospace;text-align:center}
.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px;margin:1.4rem 0 2rem}
.gallery figure{margin:0;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.10);border-radius:12px;overflow:hidden;transition:transform .18s ease,box-shadow .18s ease}
.gallery figure:hover{transform:translateY(-3px);box-shadow:0 12px 34px rgba(0,0,0,.4)}
.gallery img{display:block;width:100%;height:auto}
.gallery figcaption{padding:.7rem .9rem;font-size:.85rem;line-height:1.4;opacity:.85}
.gallery figcaption b{display:block;font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;opacity:.65;margin-bottom:.2rem}
.tour-sec{padding-top:1.2rem;border-top:1px solid rgba(255,255,255,.08);margin-top:1.6rem}
</style>

# CFactory — the cockpit tour

**CFactory** is the control tower over the whole suite. It threads every unit of work across
**PFactory → AIFactory → TFactory** into one `WorkItem` — keyed by the GitHub issue — and puts
it on a single live cockpit, with an agentic copilot and an HMAC-chained audit trail. Here's
the cockpit, tab by tab.

<figure class="tour-hero" markdown="0">
  <img src="{{ '/assets/screenshots/cfactory/mission-control.png' | relative_url }}" alt="CFactory Mission Control — the whole factory at a glance">
  <figcaption>Mission Control — the whole factory at a glance: Plan · Code · Test, live</figcaption>
</figure>

<div class="tour-sec" markdown="1">

## One pane of glass

The cockpit reads the three upstream services in real time — work-item counts at each PARR
stage, a live agent roster, and an anomaly feed — so you always know where every feature is.

</div>

<div class="gallery" markdown="0">
  <figure><img src="{{ '/assets/screenshots/cfactory/pipeline.png' | relative_url }}" alt="CFactory Pipeline"><figcaption><b>Pipeline</b>Every work item threaded across Plan → Code → Test by GitHub issue — click any card for live detail.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/cfactory/running-tasks.png' | relative_url }}" alt="CFactory Running tasks"><figcaption><b>Running tasks</b>Live progress across every factory sibling — what's running, how far, what failed.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/cfactory/services.png' | relative_url }}" alt="CFactory Services"><figcaption><b>Services</b>The cockpit and the three upstreams it threads together — health and endpoints, editable.</figcaption></figure>
</div>

<div class="tour-sec" markdown="1">

## Steer, with a human in the loop

An agentic copilot explains pipeline state from real cross-service data and proposes actions —
but a human always confirms. Every confirmed write is recorded in an HMAC-chained audit log,
and token spend is tracked across the whole pipeline. As a consumer of the completion event,
the cockpit also enforces the
[RFC-0001a evidence gates](rfc/0001a-completion-evidence-gates.md): a terminal "passed" that
carries no proof (a zero-token build, a verify with a null verdict) is rendered as unproven,
never green.

</div>

<div class="gallery" markdown="0">
  <figure><img src="{{ '/assets/screenshots/cfactory/copilot.png' | relative_url }}" alt="CFactory Copilot"><figcaption><b>Copilot</b>Ask "where is #142 and why is it stuck?" — answered from live state, with insights and recent actions alongside.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/cfactory/audit.png' | relative_url }}" alt="CFactory Audit"><figcaption><b>Audit</b>Live pipeline activity plus every confirmed action executed against an upstream — HMAC-chained.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/cfactory/tokens.png' | relative_url }}" alt="CFactory Tokens &amp; cost"><figcaption><b>Tokens &amp; cost</b>LLM usage across the pipeline, per stage, from the RFC-0001 usage block.</figcaption></figure>
</div>

<div class="tour-sec" markdown="1">

## Live execution diagrams — one map per unit of work

Click any plan, coding, or testing task and the task-detail view opens an
**animated dependency graph (DAG)** of that work. It renders whichever stage is
furthest along — **test, then code, then plan** — from a shared `graph` field on
`GET /api/workitems/{key}/process`. Nodes light up as workers pick them up
(active pulse), fill green with a robot stamp when done, shake red on failure,
and go amber when stalled; the edge to the next eligible node animates so "what
runs next" is unmistakable, and each node shows live `mm:ss` time spent. The
producers feed it directly: AIFactory exposes per-subtask `depends_on` and
timing for the code stage, TFactory exposes per-subtask lane and timing for a
lane pipeline (unit → browser → api → integration → mutation), and PFactory's
`epic.children` DAG drives the plan view. The renderer is hand-rolled SVG plus
framer-motion in the cockpit's own gruvbox language — no graph library. See the
[live execution diagrams design](plans/2026-06-14-live-execution-diagrams.md)
(shipped v1).

</div>

<div class="tour-sec" markdown="1">

## Watch the build cost accrue, live

The cockpit now carries a **live per-task cost stamp with a ticking graph** —
you watch a build's cost rise in real time as its workers report in, then
**drill down per worker** to see which provider and model spent what. AIFactory
already ran heterogeneous parallel coders (Claude, Gemini, Ollama); the cockpit
makes that parallelism visible and accountable. For the fleet-wide view, a link
takes you straight to **OpenObserve** — bundled as the OTLP backend behind
CFactory's own ingress (Keycloak SSO + Cloudflare tunnel), so the cockpit stays
the one pane of glass without growing a time-series database of its own.

</div>

[← Back to the products]({{ '/#products' | relative_url }})
