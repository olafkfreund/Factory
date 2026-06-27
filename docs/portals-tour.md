---
layout: default
title: Portal tour
permalink: /tour/
---

<style>
.tour-intro{max-width:46rem;opacity:.9}
.tour-sec{padding:1.6rem 0 .6rem;border-top:1px solid rgba(255,255,255,.08);margin-top:1.6rem}
.tour-sec h2{display:flex;align-items:baseline;gap:.6rem;font-size:1.7rem;margin:.2rem 0}
.tour-sec .tag{font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;
  border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:.16rem .6rem}
.tour-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;margin:1.2rem 0}
.tour-grid figure{margin:0;border:1px solid rgba(255,255,255,.10);border-radius:12px;overflow:hidden;background:rgba(255,255,255,.02)}
.tour-grid img{width:100%;height:auto;display:block;border-bottom:1px solid rgba(255,255,255,.07)}
.tour-grid figcaption{font-size:.82rem;opacity:.8;padding:.6rem .75rem;line-height:1.35}
</style>

# The Factory portals — a visual tour

<p class="tour-intro">Every menu and dialog across the four products, captured live from the
running portals. Each product is useful on its own and hands off to the next along the
<b>PARR</b> loop — Prepare, Act, Reflect, Review.</p>

<div class="tour-sec" markdown="0">
  <h2>One task, end to end <span class="tag" style="color:#fe8019">PARR in flight</span></h2>
  <p class="tour-intro">A single task — <b>"Add a /version endpoint"</b> — driven live through the whole
  pipeline: planned and decomposed, coded subtask by subtask, verified, and watched from the cockpit.</p>
  <div class="tour-grid">
    <figure><img src="{{ '/assets/screenshots/tour/flow/01-pfactory-plan.png' | relative_url }}" alt="PFactory plan detail" loading="lazy"><figcaption><b style="color:#83a598">1 · Prepare</b> — PFactory decomposes the plan into criteria and child issues; gates pass.</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/flow/02-aifactory-subtasks.png' | relative_url }}" alt="AIFactory subtasks" loading="lazy"><figcaption><b style="color:#fe8019">2 · Act</b> — AIFactory breaks it into subtasks: endpoint, version string, unit test.</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/flow/03-aifactory-logs.png' | relative_url }}" alt="AIFactory live agent log" loading="lazy"><figcaption><b style="color:#fe8019">2 · Act</b> — the live agent log as the coder works the repo.</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/flow/04-tfactory-report.png' | relative_url }}" alt="TFactory verdict report" loading="lazy"><figcaption><b style="color:#b8bb26">3 · Reflect</b> — TFactory's verdict and report from a real run (PASS, with evidence).</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/flow/05-cfactory-dag.png' | relative_url }}" alt="CFactory task DAG" loading="lazy"><figcaption><b style="color:#fabd2f">4 · Review</b> — CFactory threads it as one work item with a live execution DAG.</figcaption></figure>
  </div>
</div>


<div class="tour-sec" markdown="0">
  <h2 style="color:#83a598">PFactory <span class="tag" style="color:#83a598">Prepare</span></h2>
  <div class="tour-grid">
    <figure><img src="{{ '/assets/screenshots/tour/pfactory/planning.png' | relative_url }}" alt="PFactory — Planning Portal — the plan board (Plans ready → Human Review → Done)" loading="lazy"><figcaption>Planning Portal — the plan board (Plans ready → Human Review → Done)</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/pfactory/dialog-new-plan.png' | relative_url }}" alt="PFactory — New plan — ingest a document or paste text" loading="lazy"><figcaption>New plan — ingest a document or paste text</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/pfactory/files.png' | relative_url }}" alt="PFactory — Files — the project workspace" loading="lazy"><figcaption>Files — the project workspace</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/pfactory/index-memory.png' | relative_url }}" alt="PFactory — Index & Memory — AI-discovered project knowledge" loading="lazy"><figcaption>Index & Memory — AI-discovered project knowledge</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/pfactory/mcp.png' | relative_url }}" alt="PFactory — MCP — connected tools and servers" loading="lazy"><figcaption>MCP — connected tools and servers</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/pfactory/skills.png' | relative_url }}" alt="PFactory — Skills — reusable planning skills" loading="lazy"><figcaption>Skills — reusable planning skills</figcaption></figure>
  </div>
</div>

<div class="tour-sec" markdown="0">
  <h2 style="color:#fe8019">AIFactory <span class="tag" style="color:#fe8019">Act</span></h2>
  <div class="tour-grid">
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/tasks.png' | relative_url }}" alt="AIFactory — Tasks — the PARR board (Plan → Code → Review → Done)" loading="lazy"><figcaption>Tasks — the PARR board (Plan → Code → Review → Done)</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/dialog-new-task.png' | relative_url }}" alt="AIFactory — New task — the build wizard" loading="lazy"><figcaption>New task — the build wizard</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/dialog-settings.png' | relative_url }}" alt="AIFactory — Settings — agent profiles and per-phase model selection" loading="lazy"><figcaption>Settings — agent profiles and per-phase model selection</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/chat.png' | relative_url }}" alt="AIFactory — Chat — converse with the coding agent" loading="lazy"><figcaption>Chat — converse with the coding agent</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/terminal.png' | relative_url }}" alt="AIFactory — Terminal — the live agent shell" loading="lazy"><figcaption>Terminal — the live agent shell</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/files.png' | relative_url }}" alt="AIFactory — Files — the worktree browser" loading="lazy"><figcaption>Files — the worktree browser</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/worktrees.png' | relative_url }}" alt="AIFactory — Worktrees — isolated build workspaces" loading="lazy"><figcaption>Worktrees — isolated build workspaces</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/index-memory.png' | relative_url }}" alt="AIFactory — Index & Memory — codebase knowledge" loading="lazy"><figcaption>Index & Memory — codebase knowledge</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/changelog.png' | relative_url }}" alt="AIFactory — Changelog" loading="lazy"><figcaption>Changelog</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/github-issues.png' | relative_url }}" alt="AIFactory — GitHub Issues" loading="lazy"><figcaption>GitHub Issues</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/github-prs.png' | relative_url }}" alt="AIFactory — GitHub PRs" loading="lazy"><figcaption>GitHub PRs</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/mcp.png' | relative_url }}" alt="AIFactory — MCP — connected tools" loading="lazy"><figcaption>MCP — connected tools</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/aifactory/skills.png' | relative_url }}" alt="AIFactory — Skills" loading="lazy"><figcaption>Skills</figcaption></figure>
  </div>
</div>

<div class="tour-sec" markdown="0">
  <h2 style="color:#b8bb26">TFactory <span class="tag" style="color:#b8bb26">Reflect</span></h2>
  <div class="tour-grid">
    <figure><img src="{{ '/assets/screenshots/tour/tfactory/tests.png' | relative_url }}" alt="TFactory — TFactory Pipeline (Plan → Generate → Execute → Report)" loading="lazy"><figcaption>TFactory Pipeline (Plan → Generate → Execute → Report)</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/tfactory/dialog-new-task.png' | relative_url }}" alt="TFactory — New test task" loading="lazy"><figcaption>New test task</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/tfactory/dialog-new-test-plan.png' | relative_url }}" alt="TFactory — New test plan" loading="lazy"><figcaption>New test plan</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/tfactory/cloud-reports.png' | relative_url }}" alt="TFactory — Cloud Reports — live deployment test runs" loading="lazy"><figcaption>Cloud Reports — live deployment test runs</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/tfactory/visual-reports.png' | relative_url }}" alt="TFactory — Visual Reports — browser screenshots and recordings" loading="lazy"><figcaption>Visual Reports — browser screenshots and recordings</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/tfactory/test-plans.png' | relative_url }}" alt="TFactory — Test Plans" loading="lazy"><figcaption>Test Plans</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/tfactory/files.png' | relative_url }}" alt="TFactory — Files" loading="lazy"><figcaption>Files</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/tfactory/changelog.png' | relative_url }}" alt="TFactory — Changelog" loading="lazy"><figcaption>Changelog</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/tfactory/github-prs.png' | relative_url }}" alt="TFactory — GitHub PRs" loading="lazy"><figcaption>GitHub PRs</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/tfactory/mcp.png' | relative_url }}" alt="TFactory — MCP — connected tools" loading="lazy"><figcaption>MCP — connected tools</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/tfactory/skills.png' | relative_url }}" alt="TFactory — Skills" loading="lazy"><figcaption>Skills</figcaption></figure>
  </div>
</div>

<div class="tour-sec" markdown="0">
  <h2 style="color:#fabd2f">CFactory <span class="tag" style="color:#fabd2f">Review</span></h2>
  <div class="tour-grid">
    <figure><img src="{{ '/assets/screenshots/tour/cfactory/mission-control.png' | relative_url }}" alt="CFactory — Mission Control — the cockpit over the whole pipeline" loading="lazy"><figcaption>Mission Control — the cockpit over the whole pipeline</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/cfactory/dialog-copilot.png' | relative_url }}" alt="CFactory — Copilot — the advise-and-confirm assistant" loading="lazy"><figcaption>Copilot — the advise-and-confirm assistant</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/cfactory/pipeline.png' | relative_url }}" alt="CFactory — Pipeline — plan → code → test across every sibling" loading="lazy"><figcaption>Pipeline — plan → code → test across every sibling</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/cfactory/active-tasks.png' | relative_url }}" alt="CFactory — Active tasks — in-flight work, every factory" loading="lazy"><figcaption>Active tasks — in-flight work, every factory</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/cfactory/audit.png' | relative_url }}" alt="CFactory — Audit — HMAC-chained activity and confirmed actions" loading="lazy"><figcaption>Audit — HMAC-chained activity and confirmed actions</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/cfactory/tokens.png' | relative_url }}" alt="CFactory — Tokens & Cost — LLM usage across the pipeline" loading="lazy"><figcaption>Tokens & Cost — LLM usage across the pipeline</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/cfactory/services.png' | relative_url }}" alt="CFactory — Services — upstream health and endpoints" loading="lazy"><figcaption>Services — upstream health and endpoints</figcaption></figure>
    <figure><img src="{{ '/assets/screenshots/tour/cfactory/settings.png' | relative_url }}" alt="CFactory — Settings" loading="lazy"><figcaption>Settings</figcaption></figure>
  </div>
</div>
