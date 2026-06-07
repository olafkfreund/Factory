---
layout: default
title: PFactory — a guided tour
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

# PFactory — a guided tour

**PFactory** is the planning layer that sits **in front of** the coding agents. It ingests a
plan, enriches it with **live** organizational context (Kubernetes, cloud, Backstage, wikis),
runs architecture / security / feasibility review gates **with citations**, records human
approval, and only then emits governed GitHub issues for AIFactory to build.

<figure class="tour-hero" markdown="0">
  <img src="{{ '/assets/screenshots/pfactory/09-pipeline.png' | relative_url }}" alt="PFactory pipeline — enrich, decompose, review">
  <figcaption>The planning pipeline — enrich → decompose → review, grounded in real infrastructure</figcaption>
</figure>

<div class="tour-sec" markdown="1">

## Plan, ground, govern

Every plan is enriched from real cloud + catalog state, decomposed into governed work, run
through review gates whose every verdict is cited, and gated on explicit human approval before
anything is emitted downstream.

</div>

<div class="gallery" markdown="0">
  <figure><img src="{{ '/assets/screenshots/pfactory/01-portal-list.png' | relative_url }}" alt="PFactory portal"><figcaption><b>Portal</b>Every plan in one place, with status across the planning pipeline.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/pfactory/12-review.png' | relative_url }}" alt="PFactory review gates"><figcaption><b>Review gates</b>Architecture · security · feasibility — hybrid deterministic + LLM, every verdict cited.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/pfactory/14-approval.png' | relative_url }}" alt="PFactory human approval"><figcaption><b>Human approval</b>Nothing is emitted downstream until a person signs off.</figcaption></figure>
</div>

[← Back to the products]({{ '/#products' | relative_url }})
