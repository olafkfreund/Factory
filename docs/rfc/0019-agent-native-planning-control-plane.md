---
layout: default
title: "RFC-0019: Agent-Native Planning Control Plane — one board humans and the factory's agents share"
permalink: /rfc/agent-native-planning-control-plane/
---

# RFC-0019 — Agent-Native Planning Control Plane

> **Status:** Proposed · **Created:** 2026-07-19 · **Owner:** CFactory ·
> **Extends:**
> [RFC-0001](./0001-correlation-key-and-completion-event.md) (correlation key — the board is the human-facing home of a correlation),
> [RFC-0003](./0003-github-agentic-integration.md) (GitHub integration — the board augments, never replaces, GitHub as the record of truth),
> [RFC-0011](./0011-label-driven-intake-and-difficulty-tiers.md) (intake — a board card becomes an intake source alongside a labelled issue) ·
> **Affects:** CFactory (new planning surface + write APIs + skills manifest); light additive endpoints on PFactory/AIFactory/TFactory. No task-contract changes.

## 1. Motivation

The Factory is already substantially agent-native: every service exposes a REST
API and an MCP server, the fleet ships installable skills (`.claude/skills`),
and CFactory threads a correlation across plan -> build -> test via `work_items`.
But the **work surface is fragmented and read-mostly**:

- **Intake is a single GitHub issue.** You file an issue, label it `factory:low`,
  and hope. There is no place to *plan* a body of work — to hold a backlog,
  prioritise it, group it into a milestone, and let the factory pull from it.
- **CFactory is a cockpit, not a control plane.** It *observes* runs (the
  work-item timeline) but you cannot create, prioritise, or re-sequence work in
  it. Planning happens in GitHub, in issues, in someone's head.
- **Four portals + a cockpit + GitHub** is five surfaces. Humans and the
  factory's own agents have no single, editable board they both read and write.

The competitor scan that prompted this RFC (utter.ae — an agent-native project
manager) crystallised the gap. Its thesis is one design law: **"everything a
human can do has a programmatic equivalent."** Humans and agents share the same
workspaces -> projects -> issues, with stable IDs, reachable identically via UI,
REST, MCP, and a discoverable skills manifest. We already have the plumbing for
this; what we lack is (a) a shared editable planning surface and (b) the
discipline and discovery layer on top.

This RFC proposes the thin coordination layer that closes both — **not** a
Linear/Jira rebuild, and **not** a replacement for GitHub.

## 2. What we already have (and what is missing)

| Primitive | Today | Gap this RFC closes |
|---|---|---|
| REST APIs | Every service has one | No unified, editable planning resource |
| MCP servers | CFactory / PFactory / AIFactory / TFactory | No board an agent can plan *into* |
| Work tracking | CFactory `work_items` (read-mostly, correlation-keyed) | Not human-editable; no backlog/priority/milestone |
| Skills | `.claude/skills` dirs, service-local | No fleet-level discovery manifest |
| Intake | GitHub issue + label (RFC-0011) | No "front of the funnel" planning surface |
| Source of truth | GitHub issues/PRs | Stays GitHub — the board projects onto it |

The insight: we are ~80% of the way to agent-native. The missing 20% is a
**planning control plane**, a **capability-discovery manifest**, and a standing
**programmatic-equivalence** rule.

## 3. Design

### 3.1 CFactory planning board (the control plane)

Promote CFactory from read-cockpit to read/write control plane. Add a board
resource on top of the existing `work_items` correlation store:

- **Hierarchy:** `workspace -> board -> card`. A card carries a stable id
  (`FCT-42`), title, acceptance criteria, priority, status, difficulty tier
  (reuse RFC-0011 tiers), assignee (human *or* a factory runtime), and a
  milestone.
- **Views:** start with backlog + board (Kanban) + a roadmap/milestone view.
  Defer calendar/Gantt until asked (ponytail: no speculative views).
- **Human-editable** via the cockpit UI *and* every mutation available via REST
  + MCP (see 3.3). A card is the planning-time home of a correlation key; when it
  enters the factory it becomes an RFC-0001 correlation and threads the existing
  work-item timeline.

### 3.2 The factory consumes the board

A card in `ready` status with a difficulty tier is a **first-class intake
source** alongside a labelled GitHub issue (RFC-0011). On promotion:

- a small task (`factory:low/medium`) dispatches straight to AIFactory build;
- a larger card routes through PFactory planning (RFC-0010) first;
- as PARR runs, the assigned runtime **writes status back to the card** (planned
  -> building -> verifying -> verdict), so the board *is* the live view — the
  same event stream CFactory already threads, surfaced on an editable card.

This makes the board the natural front-end for PFactory's planning research: you
draft a card, the factory reconnoiters the repo and grounds a plan, and the card
shows the RepoMap/DORA context inline.

### 3.3 Programmatic equivalence (the design law)

Adopt utter.ae's principle as a standing rule: **every board action a human can
take has an identical REST + MCP equivalent.** Concretely:

- Publish CFactory's board API as an OpenAPI 3.1 spec, readable **without auth**
  so an agent can discover capabilities before authenticating (utter.ae does
  this; agents enumerate before they hold a token).
- Extend the CFactory MCP server with board tools (create/move/prioritise/assign
  a card, open a milestone) so a Claude/Codex/Gemini agent manages the backlog
  exactly as a human does in the cockpit.
- A CI check asserts parity: any new cockpit board mutation must have a matching
  API + MCP tool, or the check fails. This keeps the law true over time rather
  than aspirational.

### 3.4 Capability discovery — `/.well-known/agent-skills/index.json`

Serve a fleet-level, discoverable skills manifest (the convention utter.ae uses)
so any agent can enumerate what the Factory can do without prior knowledge:

- Each service publishes `/.well-known/agent-skills/index.json` listing its
  installable skills + the MCP endpoint + the OpenAPI URL.
- CFactory aggregates the four into one fleet manifest at the cockpit host.
- This turns the Factory's capabilities into self-describing, machine-discoverable
  metadata — the entry point an external agent (or a partner integration) hits
  first.

### 3.5 Augment, never replace, GitHub

GitHub issues/PRs remain the **record of truth** (RFC-0003). The board is a
planning projection that **syncs** to GitHub:

- creating a `ready` card can open/adopt a GitHub issue (the existing intake
  path), and the card mirrors the issue's state;
- the PR the factory opens, and the RFC-0006 VAL verdict, thread back onto the
  card the same way they thread the work-item today.

No new source of truth; the board is where humans *plan*, GitHub is where the
work *lives*.

## 4. Non-goals

- Not a full Linear/Jira (no custom fields engine, no time tracking, no
  calendar/Gantt in v1).
- Not a replacement for GitHub issues/PRs or for the four service portals.
- Not a public multi-tenant SaaS in this RFC (though 6 below notes the GTM
  optionality it creates).

## 5. Phases

1. **Board data model + read/write REST** on CFactory (`workspace/board/card`
   over the existing `work_items` store) + backlog/Kanban views in the cockpit.
2. **MCP board tools + no-auth OpenAPI** (3.3) — agents can plan into the board.
3. **Board -> intake** (3.2): a `ready` card dispatches to the factory and
   receives live PARR status back.
4. **`/.well-known/agent-skills` manifest** (3.4) per service + fleet aggregate.
5. **Programmatic-equivalence CI parity check** (3.3) so the law stays true.
6. **GitHub sync** (3.5) — card <-> issue mirroring.

Each phase ships independently and is useful on its own; 1-3 deliver the core
"humans plan, the factory builds" loop.

## 6. What it unlocks

- **One surface** for humans and the factory's agents instead of five.
- **A real planning front-end** for PFactory's research — the missing front of
  the funnel.
- **Self-describing capabilities** any agent or partner can discover.
- **A GTM story:** "an agent-native software-delivery control plane." Unlike
  utter.ae, which *tracks* agent work, the Factory *does* it (plan -> build ->
  test -> verify). The board is the productisable face of that.

## 7. Risks

- **Scope creep into a PM product.** Mitigation: the non-goals in 4; ship the
  thin layer, defer views/fields until asked.
- **Dual source of truth drift** (board vs GitHub). Mitigation: GitHub stays
  authoritative; the board is a projection with one-way-authoritative sync on
  conflict (GitHub wins).
- **Write APIs widen the attack surface** on the cockpit. Mitigation: reuse the
  existing CFactory auth (`CFACTORY_API_KEYS`, scoped tokens, tenant scoping);
  board mutations are scoped-write, audited on the RFC-0001a chain.
- **Reconcile-resurrection** (the cockpit already re-materialises work-items from
  upstream events) must be reconciled with human edits. Mitigation: human edits
  on a card take precedence over a reconcile for human-owned fields.

## 8. Open questions

- Do we build the board natively in CFactory, or evaluate adopting utter.ae (it
  ships a Claude MCP server) as the PM layer and integrating? This RFC assumes
  native, to keep the control plane inside the fleet and avoid a hard external
  dependency — but a spike comparing "build vs integrate" is worth one week
  before Phase 1.
- Card id scheme (`FCT-N` global vs per-workspace) and its relationship to the
  existing correlation key.
