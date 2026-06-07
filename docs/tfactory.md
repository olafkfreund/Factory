---
layout: default
title: TFactory — a guided tour
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

# TFactory — a guided tour

**TFactory** generates and runs tests across modality lanes (unit, browser, API, integration,
mutation) and grades every generated test on a **5-signal verdict** — coverage delta, stability
re-runs, mutation kills, lint, and semantic relevance — then posts a ranked triage report to
your PR. Meaningful tests, not a green bar.

<figure class="tour-hero" markdown="0">
  <img src="{{ '/assets/screenshots/tfactory/python-unit.gif' | relative_url }}" alt="TFactory unit lane — generate, run, grade">
  <figcaption>The unit lane in motion — generate, run, and grade tests on the 5-signal verdict</figcaption>
</figure>

<div class="tour-sec" markdown="1">

## Tests you can trust

Each modality lane produces real evidence — screenshots, video, HAR, mutants — and every
generated test is scored, so what lands on your PR is a ranked, explained verdict rather than a
coverage number.

</div>

<div class="gallery" markdown="0">
  <figure><img src="{{ '/assets/screenshots/tfactory/polyglot.gif' | relative_url }}" alt="TFactory polyglot run"><figcaption><b>Polyglot</b>One spec, many languages — the same lane across stacks.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/tfactory/api-gateway.png' | relative_url }}" alt="TFactory API lane"><figcaption><b>API lane</b>Generated API tests with real HAR evidence.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/tfactory/python-unit.png' | relative_url }}" alt="TFactory graded triage report"><figcaption><b>Verdict</b>A graded, ranked triage report — the 5-signal score, not coverage theatre.</figcaption></figure>
</div>

[← Back to the products]({{ '/#products' | relative_url }})
