---
layout: default
title: AIFactory — a guided tour
---

<style>
.tour-hero{margin:1.6rem 0 0.4rem}
.tour-hero img{width:100%;height:auto;border-radius:14px;border:1px solid rgba(255,255,255,.12);box-shadow:0 14px 50px rgba(0,0,0,.45)}
.tour-hero figcaption{font-size:.82rem;opacity:.7;margin-top:.5rem;font-family:'JetBrains Mono',monospace;text-align:center}
.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin:1.4rem 0 2rem}
.gallery figure{margin:0;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.10);border-radius:12px;overflow:hidden;transition:transform .18s ease,box-shadow .18s ease}
.gallery figure:hover{transform:translateY(-3px);box-shadow:0 12px 34px rgba(0,0,0,.4)}
.gallery img{display:block;width:100%;height:auto}
.gallery figcaption{padding:.7rem .9rem;font-size:.85rem;line-height:1.4;opacity:.85}
.gallery figcaption b{display:block;font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;opacity:.65;margin-bottom:.2rem}
.tour-sec{padding-top:1.2rem;border-top:1px solid rgba(255,255,255,.08);margin-top:1.6rem}
.tour-lead{opacity:.85;max-width:62ch}
</style>

# AIFactory — a guided tour

**AIFactory** turns a written spec into merge-ready code through the **PARR** loop —
**P**repare · **A**ct · **R**eflect · **R**eview — in an isolated git worktree, with you in
control at every gate. Here's what that looks like in the product.

<figure class="tour-hero" markdown="0">
  <img src="{{ '/assets/screenshots/aifactory/board-parr-pipeline.png' | relative_url }}" alt="AIFactory mission control — PARR pipeline over the kanban board">
  <figcaption>Mission control — the PARR pipeline (Plan · Code · Test) sitting above the board</figcaption>
</figure>

<div class="tour-sec" markdown="1">

## Mission control

Every unit of work moves left-to-right across a board you can read at a glance — from
**Backlog** through **In Progress**, **AI Review**, **Human Review**, and **Done** — with live
PARR-stage dots and progress on each card.

</div>

<div class="gallery" markdown="0">
  <figure><img src="{{ '/assets/screenshots/aifactory/board-columns.png' | relative_url }}" alt="Board columns"><figcaption><b>The board</b>Backlog → In Progress → AI Review → Human Review → Done, at a glance.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/board-review.png' | relative_url }}" alt="Work flowing into review"><figcaption><b>Flow</b>Runs land in Human Review and Done as they complete.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/board-human-review.png' | relative_url }}" alt="Human review column"><figcaption><b>Human review</b>Completed and errored runs wait for your verdict — nothing merges itself.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/task-card-progress.png' | relative_url }}" alt="A task card mid-flight"><figcaption><b>Live progress</b>A card mid-flight: PARR stage dots and a coding progress bar.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/board-stuck-recover.png' | relative_url }}" alt="Stuck task recovery"><figcaption><b>Self-healing</b>A stalled run is detected and offered a one-click Recover.</figcaption></figure>
</div>

<div class="tour-sec" markdown="1">

## Inside a task

Open any task for the full story: the intent, the decomposed plan, the generated spec, the
streamed PARR log, live resource/token observability, and a read-only mirror of the agent's
terminal you can attach to at any time.

</div>

<div class="gallery" markdown="0">
  <figure><img src="{{ '/assets/screenshots/aifactory/task-overview.png' | relative_url }}" alt="Task overview"><figcaption><b>Overview</b>The one-line intent and timeline for the run.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/task-subtasks.png' | relative_url }}" alt="Task subtasks"><figcaption><b>Subtasks</b>The plan decomposed into independently verifiable units.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/task-files.png' | relative_url }}" alt="Generated spec file"><figcaption><b>Files</b>The generated, editable spec — every run starts spec-first.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/task-logs.png' | relative_url }}" alt="PARR logs"><figcaption><b>Logs</b>The PARR loop in the open — Prepare, Act, Reflect, every step streamed.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/task-observability.png' | relative_url }}" alt="Task observability"><figcaption><b>Observability</b>Live token spend by bucket, CPU/memory, and a channel to message the agent.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/task-live-console.png' | relative_url }}" alt="Live agent console"><figcaption><b>Live console</b>A read-only mirror of the agent's terminal — click Attach to take control.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/task-live-console-tests.png' | relative_url }}" alt="QA test run"><figcaption><b>Verify</b>The QA phase: the full pytest suite running and passing live.</figcaption></figure>
  <figure><img src="{{ '/assets/screenshots/aifactory/task-subtasks-stuck.png' | relative_url }}" alt="Stuck task subtasks"><figcaption><b>Recovery</b>6/7 subtasks done and a clean Recover &amp; Restart when a run stalls.</figcaption></figure>
</div>

<div class="tour-sec" markdown="1">

## Per-worker, per-provider observability

AIFactory runs **parallel coding workers across providers** — Claude, Gemini,
and local Ollama models side by side. Now it emits **real OpenTelemetry
per-worker metrics** from the web-server (labelled by provider and model, with
bounded cardinality), streams **live worker events** with a 10-second heartbeat,
and reports cost per worker through the v1.3 completion event
(`workers[]` / `by_provider` / `by_model`) instead of collapsing it to a single
model string. A **soft, observe-only budget alert** surfaces when a task crosses
a threshold without ever killing the run. The result: you can finally answer, per
task and live, what a build cost, on which model, and where the time went.

</div>

<div class="tour-sec" markdown="1">

## Memory &amp; settings

AIFactory keeps **persistent cross-session memory** so agents carry context forward — backed by
an embedded knowledge graph with selectable, local-first embedding models.

</div>

<div class="gallery" markdown="0">
  <figure><img src="{{ '/assets/screenshots/aifactory/settings-memory.png' | relative_url }}" alt="Memory and embeddings settings"><figcaption><b>Agent memory</b>Persistent cross-session memory via MCP, with local-first embedding models — semantic search optional, keyword search always works.</figcaption></figure>
</div>

[← Back to the products]({{ '/#products' | relative_url }})
