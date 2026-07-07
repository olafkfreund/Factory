---
layout: post
title: "Four portals, one product: the Factory becomes a single shell"
subtitle: "A unified cross-portal shell, one sign-on, fleet-wide search, and the whole factory moved to the latest models — with a one-page showcase for each service, ready to download."
date: 2026-07-07 06:00:00
author: Olaf Freund
---

The Factory has always been four services working as one pipeline: PFactory plans
it, AIFactory builds it, TFactory verifies it, and CFactory watches the whole
thing from the cockpit. This round of work made them *feel* like one product, and
moved the entire fleet onto the latest models.

## One shell across four portals

Until now, each portal was its own island. That changed:

- **A portal switcher** in every top bar turns Plan, Build, Test, and Cockpit into
  one product you move between with a click.
- **A global command palette** — Cmd-K anywhere — searches every portal's work at
  once and jumps straight to it, backed by a federated search index in the cockpit.
- **A fleet "needs you" inbox and badge** collect every task blocked on a human —
  approvals, review gates, stalls — into one prioritised queue, surfaced in all
  four portals.
- **Silent single sign-on**: one Keycloak login now hands you between portals
  without signing in again.

Underneath, a shared `@factory/ui` package keeps the portal chrome byte-identical
across the repos, enforced by a drift gate — so consistency is guaranteed by
construction, not convention.

![CFactory Mission Control]({{ '/assets/blog/2026-07-07/mission-control.png' | relative_url }})

## The latest models, everywhere

The whole fleet moved to the current model lineup. Every stage now defaults to
**Claude Opus 4.8**, with **Claude Sonnet 5** and the current OpenAI Codex, Google
Gemini, and GitHub Copilot models selectable per task. GitHub Copilot joins Claude
and Codex as a coding runtime, baked into the build image. Along the way we fixed
the cockpit's cost reporting, which had been over-stating Opus spend three-fold.

## See it for yourself

Each portal now has a one-page showcase, captured from the live, authenticated
product and ready to download:

- **[The Factory — one-page showcase (PDF)]({{ '/assets/factory-showcase.pdf' | relative_url }})**
- PFactory, AIFactory, TFactory, and CFactory each publish their own on their
  documentation sites.

<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0;">
  <img src="{{ '/assets/blog/2026-07-07/planning-portal.png' | relative_url }}" alt="PFactory planning portal" style="width:100%;border-radius:6px;">
  <img src="{{ '/assets/blog/2026-07-07/build-workspace.png' | relative_url }}" alt="AIFactory build workspace" style="width:100%;border-radius:6px;">
</div>

![TFactory verify pipeline]({{ '/assets/blog/2026-07-07/verify-pipeline.png' | relative_url }})

## The path forward

Next we bring the Copilot runtime fully live, expand the guided demos, and keep
hardening the pipeline that plans, builds, and verifies software with a human in
the loop only where it matters. As ever, the Factory ships these changes through
its own pipeline.
