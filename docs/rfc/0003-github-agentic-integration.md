---
layout: default
title: "RFC-0003: GitHub Agentic Integration"
permalink: /rfc/github-agentic/
---

# RFC-0003 — GitHub Agentic Integration

> **Status:** Accepted (documents shipped implementations) · **Version:** 1.0 ·
> **Created:** 2026-06-09
> Companion to [RFC-0001](./0001-correlation-key-and-completion-event.md)
> (correlation key + completion-event envelope) and
> [RFC-0002](./0002-task-contract.md) (Task Contract v2). This RFC is the
> cross-factory blueprint for how every Factory product integrates with GitHub's
> native agentic surface. It is written **after** the product teams shipped, so it
> documents reality and standardizes the conventions they converged on.

## Why this RFC exists

GitHub now ships a first-class **agentic surface**: a cloud coding agent you can
assign issues to, a free OpenAI-compatible inference API, MCP servers the cloud
agent can call mid-task, schedulable Copilot automations, and the Copilot CLI
inside Actions. Each Factory product (AIFactory, PFactory, TFactory) adopted these
independently — and converged on the same shapes. RFC-0003 names those shapes once
so they stay consistent: the same label taxonomy, the same `github-models/*` model
strings, the same `/mcp` call-home pattern, and the same Actions trigger contract.

This is deliberately a **documentation-and-convention** RFC, not new runtime. The
products already implement it; the value is a single canonical reference so the
fourth product (CFactory) and any future repo integrate the same way.

## The GitHub agentic surface (as of 2026-06)

| Feature | Surface | Trigger / endpoint |
|---|---|---|
| **Copilot Cloud Agent** | GitHub Issues + cloud infra | Assign `copilot-swe-agent[bot]` (UI or `PATCH /repos/{owner}/{repo}/issues/{n}` assignee) |
| **GitHub Models API** | `models.github.ai` | `POST /inference/chat/completions`, OpenAI-compatible, auth via `GITHUB_TOKEN` (in Actions) or a `models:read` PAT |
| **MCP for cloud agent** | Repo Settings → Copilot → MCP servers | JSON config (`http`/`sse`/`stdio`); secrets via `COPILOT_MCP_*` |
| **Copilot Automations** | Repo Settings → Copilot → Automations | `issue.created`, `pr.created/updated`, schedule (GA 2026-06-02) |
| **Copilot CLI in Actions** | `npm i -g @github/copilot` | `copilot -p "…" --allow-all-tools`, auth via `COPILOT_GITHUB_TOKEN` |

## Design principles

1. **Additive and opt-in.** Every integration point is inert when its config is
   absent. Existing tasks, providers and workflows are unaffected. No product is
   forced onto GitHub's surface.
2. **Reuse, don't reinvent.** `github-models` is an *alias* that routes through the
   existing `openai-compatible` provider — no new provider class. The cloud agent
   reuses each product's existing engines (AIFactory's PR-review engine, TFactory's
   test generator) rather than new code paths.
3. **One correlation key still rules.** A Copilot-authored PR and an
   AIFactory-authored PR are the same kind of work item, threaded by the same
   GitHub-issue correlation key from [RFC-0001](./0001-correlation-key-and-completion-event.md).
4. **Don't shadow `gh`.** `github-models` / `gh-models` are the only aliases; never
   register a bare `github` alias — it would collide with the `gh` CLI and
   `runners/github/` paths used throughout the products.

## The shared label taxonomy

The trigger contract is a small, stable set of labels. A label is the unit of
delegation — applying it to an issue or PR routes the work.

| Label | Applied to | Meaning |
|---|---|---|
| `copilot:delegate` | Issue | Hand this issue to GitHub's `copilot-swe-agent[bot]`; the originating product then watches for the resulting PR. |
| `aifactory:run` | Issue | AIFactory picks up the issue and runs its build pipeline. |
| `aifactory:review` | PR | AIFactory's PR-review engine reviews this PR. |
| `pfactory:run` | Issue | PFactory enriches/decomposes the issue into a governed plan. |
| `tfactory:run` | Issue / PR | TFactory generates and grades tests for the change. |

Labels are the public contract; the workflows below are the private wiring. A
product may add internal labels, but these five are reserved and mean the same
thing in every repo.

## Per-feature contract

### 1. GitHub Models provider

A canonical `github-models` provider alias routes through the product's existing
OpenAI-compatible backend with GitHub defaults injected: `base_url =
https://models.github.ai/inference`, `api_key = $GITHUB_TOKEN` (falling back to
`$GH_TOKEN`), and the `github-models/` prefix stripped from the model string
(`github-models/openai/gpt-4.1` → `openai/gpt-4.1`). In Actions this is free
inference with no extra billing.

### 2. Copilot cloud agent dispatch

Applying `copilot:delegate` to an issue assigns `copilot-swe-agent[bot]`. The
originating product moves the task to a `copilot_running` state, watches for the
bot's PR, and on PR-open transitions to `copilot_pr_opened` and triggers its own
review/verify engine. The cloud agent is treated as one more coding backend — its
output re-enters the normal PARR flow.

### 3. Product as MCP server (call-home)

Each product exposes an MCP router (e.g. AIFactory `POST /mcp`) so the cloud agent
can call home **during** its coding session for context it would otherwise lack:

- **AIFactory** — `aifactory_get_spec`, `aifactory_get_plan`, `aifactory_record_discovery`
- **PFactory** — planning-context tools (enriched plan, governance constraints)
- **TFactory** — test-context tools (acceptance criteria, the `tfactory` block from
  [RFC-0002](./0002-task-contract.md))

This is the same MCP surface already catalogued as each product's `*-mcp` API; the
cloud-agent config simply points GitHub at it.

### 4. GitHub Actions workflows

Three workflow shapes per product, keyed on the label taxonomy:

- `on: issues.labeled [{product}:run]` → call the product's `from-github-issue` entry.
- `on: pull_request.opened` where `actor == copilot-swe-agent[bot]` → trigger the
  product's review/verify engine on the Copilot PR.
- `on: pull_request.labeled [{product}:review]` → run the review engine on demand.

Supplemented by GitHub's native **Copilot Automations** (GA 2026-06-02) for
scheduled and event-triggered runs that don't need a custom workflow.

## Per-product adoption (shipped)

All three adoption epics are **closed**; this RFC documents what they built.

| Product | Epic | Components |
|---|---|---|
| **AIFactory** | [#456](https://github.com/olafkfreund/AIFactory/issues/456) | Models provider (#457), Copilot dispatch (#458), `/mcp` server (#459), Actions workflows (#460), UI (#461) |
| **PFactory** | [#87](https://github.com/olafkfreund/PFactory/issues/87) | Models provider + Copilot dispatch (#88), MCP planning-context server (#89), Actions workflows (#90) |
| **TFactory** | [#277](https://github.com/olafkfreund/TFactory/issues/277) | Models provider + Copilot dispatch for test writing (#278), MCP test-context server (#279), Actions `tfactory:run` + Copilot-PR test trigger (#280) |

Source design: [AIFactory GitHub Agentic Integration design](https://github.com/olafkfreund/AIFactory/blob/dev/docs/plans/2026-06-07-github-agentic-integration-design.md).

## How it relates to RFC-0001 / RFC-0002

- **RFC-0001** still threads every item by the GitHub-issue correlation key — a
  Copilot PR is threaded exactly like an AIFactory PR, and terminal status flows
  back over the same completion-event envelope.
- **RFC-0002** is what the cloud agent reads through the `/mcp` call-home tools: the
  signed Task Contract's `tfactory` block, execution profile and plan are the
  context that keeps a delegated coding session on-spec.

## Out of scope

- CFactory adoption (cockpit visualization of Copilot-delegated work) — a natural
  follow-up, not required here.
- Replacing any product's primary providers; `github-models` is additive.
- Security hardening of the cloud-agent MCP exposure beyond the existing
  `COPILOT_MCP_*` secret model — tracked per product.
