---
layout: default
title: "RFC-0019 Phase 0 Spike: build the board natively vs integrate utter.ae"
permalink: /rfc/agent-native-planning-control-plane-spike/
---

# RFC-0019 Phase 0 Spike — build native vs integrate utter.ae

> **Status:** Complete, awaiting decision · **Date:** 2026-07-25 · **Owner:** CFactory ·
> **Decides:** [RFC-0019](./0019-agent-native-planning-control-plane.md) open question 8.1
> ("Do we build the board natively in CFactory, or adopt utter.ae as the PM layer?") ·
> **Tracking:** [Factory#302](https://github.com/olafkfreund/Factory/issues/302) ·
> **Output:** a recommendation. No implementation. Phases 1-6 remain unstarted.

## 0. Summary

Recommendation: **build native, adopt utter.ae's published conventions, do not
integrate the product.**

The decisive fact is not a scoring nuance. utter.ae ships no self-hosted or
on-premise offering on any first-party surface we could find, and the fleet's
self-hosting requirement is non-negotiable. That rules integration out on its
own. Every other axis (data egress, GitHub-as-record-of-truth, PARR status
write-back) points the same way.

The second finding is that "build native" is smaller than RFC-0019 implies.
Three of the six phases are already largely done or nearly free in the existing
CFactory codebase, and one of the RFC's stated deliverables (an unauthenticated
OpenAPI 3.1 spec) already ships today. Revised estimate for the core loop
(phases 1-3) is 3-4 focused weeks, with phases 4-5 costing days rather than
weeks.

The third finding is a design correction that came out of reading the store:
board cards must live in their **own table**, not inside `work_items`. The
reconcile/prune machinery in `store.py` actively deletes and rewrites work-item
rows from upstream polling, so human-owned card fields stored there would be
destroyed by design, not by accident. RFC-0019 §7 lists this as a risk to be
mitigated by discipline; a separate table removes it structurally.

---

## 1. What we already have

All citations are to the CFactory repository as of commit `86bdfcd`
(`docs: env reference page, feature refresh + latest blog post`), read at
`/mnt/data/Source-home/GitHub/CFactory`.

### 1.1 The correlation store (`work_items`)

- Domain model: `apps/backend/cfactory/models.py` — `WorkItem` (line 314) carries
  `correlation_key`, `title`, three `ServiceState` slices (pfactory / aifactory /
  tfactory), a `timeline` of `CompletionEvent`, and `created_at` / `updated_at`.
- Persistence: `apps/backend/cfactory/store.py` (705 lines) — `WorkItemRow`
  (line 343) and `WorkItemStore` (line 402), SQLAlchemy over Postgres, with a
  tenant partition (`tenant_id`, line 353) and `scoped(tenant)` views (line 423).
- Schema: `apps/backend/migrations/versions/05d233b19ee9_create_work_items.py`
  creates the table with the three service slices and `timeline` as JSON columns
  and a unique index on `correlation_key`;
  `a7c3f2e19b40_work_items_tenant_id.py` adds the tenant column.

What the store is: an **event-derived projection**. Rows are created and mutated
by `upsert_from_event` (line 438) and `upsert_snapshot` (line 497), i.e. by
inbound completion events and by polling upstream services.

What the store is **not**: a place for human-authored state. Four methods exist
specifically to delete or rewrite rows based on what upstream currently reports:

- `reconcile_snapshot(service, live_task_ids)` (line 553)
- `prune_duplicate_stages(...)` (line 579)
- `prune_stuck(...)` (line 607)
- `prune_stalled(...)` (line 633)

This is the concrete mechanism behind the "reconcile-resurrection" risk in
RFC-0019 §7. It is not hypothetical: a human-edited priority or acceptance
criterion stored on a `work_items` row is subject to being pruned or overwritten
whenever the upstream poll disagrees. **Design consequence: cards belong in a
new `cards` table joined to `work_items` by `correlation_key`, with the
work-item row remaining a pure projection.** This is a cheap change to make now
and an expensive one to retrofit.

### 1.2 The REST surface

- Work items: `apps/backend/cfactory/routes_workitems.py` (225 lines) — eleven
  GET endpoints: `/api/workitems`, `/api/workitems/{key}`, `.../timeline`,
  `.../process`, `.../evidence/{kind}/{name}`, plus `/api/search`,
  `/api/needs-you/count`, `/api/rollups`, `/api/tokens`, `/api/tokens/by_worker`,
  `/api/progress`, `/api/anomalies`, `/api/tasks/{key}/worker-progress`,
  `/api/tasks/{key}/cost-routing`. Every one is read-only.
- Writes already exist: `apps/backend/cfactory/routes_actions.py` (128 lines) —
  `POST /api/actions/propose` (advise-only) and `POST /api/actions/execute`
  (audited write, gated on `Depends(require_scope("write"))`, line 49, with an
  actor identity seam and an audit record on every confirmed action, lines
  79-88). Action kinds today: `approve_plan`, `approve_review`, `reject_review`,
  `recover`, `delete_task` (`apps/backend/cfactory/actions.py`, lines 166-288).
- Auth: `apps/backend/cfactory/auth.py` (212 lines) — scoped API keys parsed
  from `CFACTORY_API_KEYS`, with `READ` / `WRITE` scopes (lines 26-27) and a
  `KeyStore.authorize` (line 117). Enforced by the `enforce_api_key` middleware
  in `apps/backend/cfactory/app.py` (lines 124-141), guarding `/api/*` and
  `/connect/*`, exempting `/api/events*` (line 71).
- Other routers wired in `app.py` (lines 143-157): health, events, services,
  workitems, live agents, actions, copilot, connect, ws, mcp.

Two things follow. First, **the write path, the scope model, the audit chain and
the actor seam already exist**; board mutations reuse them rather than inventing
them. Second, RFC-0019 §3.3's "publish an OpenAPI 3.1 spec, readable without
auth so an agent can discover capabilities before authenticating" is **already
true today and costs nothing**: FastAPI (`requirements.txt`: `fastapi>=0.115`)
emits OpenAPI 3.1 at `/openapi.json`, and that path is neither `/api/*` nor
`/connect/*`, so the enforcement middleware never sees it. That is one RFC
deliverable that is a no-op.

### 1.3 The MCP server

- `apps/backend/cfactory/mcp.py` (256 lines) — a POST-only JSON-RPC 2.0 endpoint
  at `POST /mcp` handling `initialize`, `tools/list`, `tools/call` (line 210).
- Five tools (`MCP_TOOLS`, line 53): `cfactory_list_workitems`,
  `cfactory_get_workitem`, `cfactory_get_timeline`, `cfactory_get_rollups`,
  `cfactory_get_anomalies`. The module docstring is explicit: "Read-only by
  design — no actions, no mutation."
- Auth: `_verify_mcp_token` (line 119) checks a single shared bearer,
  `CFACTORY_MCP_SECRET`, and **accepts all requests when it is unset**.

Gap this spike surfaces and RFC-0019 does not budget: the MCP transport has
**no scope model**. REST has `read`/`write`; MCP has one all-or-nothing secret.
Phase 2 ("MCP board tools") therefore has a prerequisite — give `/mcp` the same
scoped-key treatment as `/api/*` — before any mutating tool is exposed. Adding
write tools to a single-shared-secret endpoint that defaults to open would be a
real widening of the attack surface, which is the exact risk RFC-0019 §7 flags.

### 1.4 The cockpit UI

- `apps/frontend-web/src/` — 57 files, ~8,500 lines of TypeScript/TSX.
- **A Kanban board already exists**: `Board.tsx` — "The Pipeline board view
  (plan -> code -> test columns), its work-item cards and the live/stage chips".
  It has search, filter chips (`all` / `running` / `review` / `queued` /
  `failed`), a finished-items section, and card selection into `TaskDetail`.
  It is grouped by *derived pipeline stage* (`activeStage(...)`), not by a
  human-set status, and cards are not draggable or editable.
- Views wired in `App.tsx` (lines 263-276): board, needs-you, running, tokens,
  audit, services, settings. Plus `MissionControl`, `PipelineStrip`,
  `CommandPalette`, `TaskActions`, `TraceabilityPanel`, `CostRoutingPanel`,
  `StageGates`, `LiveAgents`.

So the Kanban rendering, card component, detail drawer, command palette,
WebSocket live updates and toast/notify plumbing are built. Phase 1's frontend
work is adding a **backlog view** and making the board's columns reflect an
editable card status rather than a derived stage — not building a board from
zero.

### 1.5 Skills

Skills exist per service but there is no manifest and no CFactory skills:

| Repo | `.claude/skills` |
|---|---|
| PFactory | 16 skills (`pfactory-init`, `pfactory-watch`, `handover-to-pfactory`, `cloud-discover`, ...) |
| TFactory | 10 skills (`tfactory-init`, `tfactory-watch`, `handback-to-aifactory`, ...) |
| AIFactory | 2 skills (`aifactory-spec`, `handover`) |
| CFactory | none |
| Factory (hub) | none |

No `.well-known` directory exists in CFactory. RFC-0019 §3.4 is genuinely
unbuilt — but it is a static JSON route plus an aggregator, which is the
cheapest phase in the RFC.

### 1.6 Scorecard: how much of "build native" is already done

| RFC-0019 phase | Already in place | Remaining |
|---|---|---|
| 1. Board data model + read/write REST + views | Store, migrations, tenant scoping, write path with scopes + audit, Kanban component, detail drawer, live WS | New `cards` table + CRUD routes; backlog view; make columns editable; card <-> correlation link |
| 2. MCP board tools + no-auth OpenAPI | MCP server + tool dispatch; unauthenticated OpenAPI 3.1 already served | ~8 write tools; **scope model on `/mcp` (unbudgeted prerequisite)** |
| 3. Board -> intake, status write-back | Upstream adapters, `execute_action` dispatch, event ingress, WS broadcast | Dispatch-on-ready; write PARR status onto the card |
| 4. `.well-known/agent-skills` manifest | Skills exist in 3 of 5 repos | Static route per service + fleet aggregate; author CFactory skills |
| 5. Programmatic-equivalence CI parity check | Nothing | A test asserting every board mutation has a REST + MCP twin |
| 6. GitHub card <-> issue sync | RFC-0003/RFC-0011 intake paths exist elsewhere in the fleet | The genuinely new work: webhooks, mirroring, conflict rules |

Roughly: the plumbing is there, the planning entity is not. RFC-0019's own
"~80% of the way to agent-native" claim holds up against the code.

---

## 2. utter.ae: what it actually is

### 2.1 Evidence quality — read this first

**Web search returns nothing on utter.ae.** Four separate searches (product
name, name plus "programmatic equivalence", name plus self-hosting/licence, name
plus GitHub integration) returned zero results referencing the product. There is
no third-party coverage, no review, no comparison article, no GitHub presence, no
funding or company reporting that we could find.

Every fact below therefore comes from **utter.ae's own surfaces, fetched
2026-07-25**. Nothing is independently corroborated. Statements about what the
product does are the vendor's claims; statements about what we could not find are
statements about our search, not proof of absence.

That evidence position is itself material to the decision: taking a hard
dependency on a vendor with no external footprint, no findable company
information, no published SLA and no findable security or compliance page is a
different proposition from depending on, say, Linear.

### 2.2 What it is

From `https://utter.ae` (fetched 2026-07-25): "a calm, opinionated project
management tool" for teams and AI agents. Hierarchy is **workspaces -> projects
-> issues**. Views: Kanban, backlog, list, calendar, timeline (Gantt), reports.
Also sprints, milestones, per-project custom statuses, team chat (channels and
DMs), mindmaps, and a public roadmap / feedback-and-voting board.

Note the hierarchy is one level richer than RFC-0019's proposed
`workspace -> board -> card`, and the view set is a superset of what RFC-0019
explicitly defers in its non-goals (§4 rules out calendar/Gantt in v1). utter is a
full PM product; RFC-0019 deliberately is not.

### 2.3 Programmatic equivalence — confirmed, and it is real

The homepage states the principle as "everything a human can do has a
programmatic equivalent", delivered through three layers. We verified all three
by direct fetch:

**1. Skills manifest.** `https://utter.ae/.well-known/agent-skills/index.json`
returns, unauthenticated:

```json
{
  "$schema": "https://agentskills.io/schemas/v0.2.0/index.json",
  "skills": [
    {"name": "utter-rest-api",      "type": "rest",
     "url": "https://utter.ae/api/v1/openapi.json",
     "sha256": "9428ec920521e39ac71e3e41d655b65d33683eb92e52c7d354a951ae3d000e6b"},
    {"name": "utter-mcp",           "type": "mcp",
     "url": "https://utter.ae/.well-known/mcp/server-card.json",
     "sha256": "5fac59690d872a922272c73466f661b0b24958139eeb82efe8b6914a72e98fba"},
    {"name": "utter-skill-bundle",  "type": "skill-md",
     "url": "https://utter.ae/api/skill/utter-product.skill.md",
     "sha256": null}
  ]
}
```

Two details worth stealing: the manifest is a **typed index** (`rest` / `mcp` /
`skill-md`) rather than a prose list, and each entry carries a **`sha256`** so an
agent can pin what it fetched. The schema is a third-party convention
(`agentskills.io` v0.2.0), not a utter invention — so adopting it is adopting a
convention, not a vendor.

**2. MCP server card.** `https://utter.ae/.well-known/mcp/server-card.json`
returns, unauthenticated:

```json
{"schemaVersion":"0.1.0","serverInfo":{"name":"Utter","version":"1.0.0",
"description":"Project management MCP server — workspaces, projects, issues, sprints, board columns, comments, and team members"},
"transport":{"type":"http","endpoint":"https://utter.ae/api/mcp/v1"},
"capabilities":{"tools":true,"prompts":false,"resources":false},
"authentication":{"type":"oauth2",
"authorizationServer":"https://utter.ae/.well-known/oauth-authorization-server",
"protectedResource":"https://utter.ae/.well-known/oauth-protected-resource"},
"skillBundle":"https://utter.ae/api/skill/utter-product.skill.md"}
```

Streamable HTTP transport, OAuth 2.0 with PKCE. Note CFactory's MCP is a
POST-only JSON-RPC transport with a static bearer — a step behind on both
transport and auth.

**3. REST API v1.** `https://utter.ae/api/v1/openapi.json` — OpenAPI **3.1.0**,
title "Utter API", server `https://utter.ae/api`. We fetched the document
**without any credential**, confirming the "discover before you authenticate"
pattern RFC-0019 §3.3 describes. The *endpoints* require a workspace-scoped
bearer key (`utp_live_…` prefix) with per-resource scopes (`issues:read`,
`webhooks:write`, ...). Roughly 150+ endpoints across: workspaces, projects,
issues, comments, sprints, milestones, releases, labels, custom fields, members,
invites, webhooks, API keys, forms, automations, workflows, documents,
portfolios, goals, chat, agents, sessions, reports, saved views.

The principle is not marketing. The surface area is real and it is large.

### 2.4 Licensing, self-hosting, hosting

From `https://utter.ae/pricing` (fetched 2026-07-25):

| Plan | Price | Notes |
|---|---|---|
| Free | $0 | 5 projects, 128 MB storage, 25 AI credits/month, unlimited members and free viewers |
| Pro | $3 / builder / month | Unlimited projects, 1 GB storage, 5,000 AI credits/month, 14-day trial |
| Business | $6 / builder / month | Unlimited projects, 100 GB storage, 20,000 AI credits/month, dedicated account contact, volume pricing |

Homepage listed a Business tier including SSO/SCIM.

The findings that decide this spike:

- **No self-hosted, on-premise, or Enterprise-installable option is offered on
  the pricing page or anywhere else we could reach.**
- **No open-source or source-available licence is mentioned anywhere.** No
  repository was findable.
- Hosting: files on **Cloudflare R2**; company footer gives **Dubai, UAE**.
- Auth for humans: OAuth 2.0 with PKCE and personal access tokens.

We did not find a security, compliance, DPA, sub-processor, SLA or data-residency
page. Absence of a finding is not proof of absence — but for a component that
would hold the fleet's entire backlog, we would need those documents before
integrating, and we could not obtain them from public surfaces.

### 2.5 GitHub

We found **no evidence of a native GitHub issue/PR sync**. `utter.ae/integrations`
and `utter.ae/docs` both return HTTP 404, and search returned nothing. The
OpenAPI tag list does include `Webhooks` and `Automations`, so a sync could be
*built* against the API — but it would be ours to build and ours to maintain.

This matters more than it first appears. RFC-0019's §3.5 law is "augment, never
replace, GitHub", and its Phase 6 is card <-> issue sync. Integrating utter does
not deliver Phase 6; it makes Phase 6 harder, because the sync then spans three
systems (GitHub, utter, CFactory) instead of two, with the middle one outside our
control.

### 2.6 Is integration even possible for a self-hosted fleet?

Mechanically: yes in the weak sense. A self-hosted CFactory can call
`https://utter.ae/api/v1` outbound with a bearer key, and could consume utter
webhooks if the cockpit were publicly reachable.

In the sense that matters: **no.** Integration means the planning board — every
card title, acceptance criterion, plan, priority and status — lives on a
third-party SaaS in a jurisdiction we did not choose, with no option to bring it
in-house at any price we could find. For a fleet whose positioning is
self-hosting, that is not a trade-off to score; it is a disqualification.

---

## 3. Evaluation matrix

Weighting: self-hosting is a **gate**, not a weighted criterion. An option that
fails it cannot be recovered by scoring well elsewhere.

Scores: 5 best, 1 worst. "Hybrid" here means the honest hybrid — build the board
natively, adopt utter's published conventions (agentskills.io index, MCP server
card, unauthenticated OpenAPI), and keep utter as an *optional outbound
integration* for a future customer who already uses it.

| Criterion | Build native | Integrate utter.ae | Hybrid (build + adopt conventions) |
|---|---|---|---|
| **Self-hosting (GATE)** | PASS — runs in-cluster with the rest of the fleet | **FAIL** — no self-host/on-prem option found; SaaS only | PASS |
| Data egress | 5 — nothing leaves the cluster | 1 — full backlog, ACs and plans on third-party SaaS (Cloudflare R2, Dubai); no DPA/sub-processor page found | 5 — conventions are documents, not data paths |
| Programmatic equivalence | 4 — achievable; REST scopes + audit exist, MCP needs a scope model and write tools | 5 — already delivered and proven at ~150 endpoints | 5 — same as native, plus the manifest/server-card conventions that make it discoverable |
| Effort to first value | 3 — 3-4 weeks to the core loop | 3 — ~2 weeks for a bridge service, but it buys a board we cannot host | 3 — same as native; conventions add ~2 days |
| Maintenance burden | 3 — our table, our routes, our tests; but it is 6 files in a codebase we own | 2 — vendor API drift, OAuth rotation, an unmonitorable dependency, per-builder billing that scales with the team | 3 — same as native; conventions are static JSON that changes rarely |
| Fit with "augment, never replace GitHub" | 5 — board is a projection; GitHub stays authoritative; one sync boundary | 2 — no native GitHub sync found; introduces a *third* system and a second sync boundary outside our control | 5 — same as native |
| Fit with the rest of the fleet (RFC-0001 correlation, RFC-0011 tiers, RFC-0006 VAL) | 5 — cards join `work_items` on `correlation_key` directly | 2 — every fleet concept (difficulty tier, VAL level, correlation key) becomes a custom field on a foreign schema | 5 |
| Vendor risk | 5 — none | 1 — zero external footprint; no findable company info, SLA, or security page; single point of failure for planning | 5 |
| GTM story ("agent-native software-delivery control plane") | 4 — the board is ours to productise | 1 — the productisable face of the offering would be someone else's product | 5 — we can credibly claim standards-conformance *and* own the surface |

Integrate fails the gate on row one. Between native and hybrid, hybrid strictly
dominates: it is the same build, plus about two days of static JSON, and it buys
real interop and a better GTM claim.

---

## 4. Recommendation

**Build the board natively in CFactory. Adopt utter.ae's conventions, not its
product. Do not integrate.**

### Reasoning

1. **The gate settles it.** No self-hosted option exists for utter.ae on any
   surface we could reach. The fleet's positioning is self-hosting. Nothing on
   the other axes can recover that.
2. **Integration would not even deliver the RFC.** utter has no GitHub sync we
   could find, no notion of PARR stages, no correlation key, no VAL levels, no
   difficulty tiers. We would build a bridge service *and* a GitHub sync *and*
   map every fleet concept onto foreign custom fields — then still not own the
   surface.
3. **Native is cheaper than the RFC assumes.** The store, migrations, tenant
   scoping, scoped-write path, audit chain, Kanban component, detail drawer, live
   WebSocket and an unauthenticated OpenAPI 3.1 spec all exist. The missing piece
   is one table and its CRUD, plus a backlog view.
4. **utter's conventions are worth copying verbatim and are free.** The
   `agentskills.io` v0.2.0 index, the MCP server-card, the sha256-pinned entries,
   and the discover-before-auth OpenAPI pattern are documented conventions, not
   vendor lock-in. RFC-0019 §3.3 and §3.4 already propose exactly this; the spike
   just supplies the concrete schema to conform to.
5. **Optionality is preserved.** utter has a large public REST API. If a customer
   arrives already living in utter, an outbound one-way projection from our board
   into their workspace is a later, small, additive integration. Nothing in the
   native path forecloses it.

### Estimated effort for the recommended path

Estimates are for one focused engineer, and assume the `cards`-in-its-own-table
design below.

| Phase | Work | Estimate |
|---|---|---|
| 1 | `cards` table + Alembic migration (tenant-scoped, joined to `work_items` by `correlation_key`); `routes_cards.py` CRUD reusing `require_scope("write")` + the audit chain; backlog view; make `Board.tsx` columns reflect card status and support move/reprioritise | **8-10 days** |
| 2a | **Prerequisite (unbudgeted in RFC-0019):** scope model on `/mcp` so a write tool cannot ride a single shared secret that defaults to open | **2 days** |
| 2b | ~8 MCP board tools (create/update/move/prioritise/assign card, open milestone, list backlog); OpenAPI is already unauthenticated, so no work | **3 days** |
| 3 | Dispatch a `ready` card to the factory (reuse the `execute_action` adapter path); write PARR status back onto the card from the existing event ingress | **5 days** |
| 4 | `/.well-known/agent-skills/index.json` per service (static route + sha256) and the CFactory fleet aggregate; author CFactory's first skills | **2 days** |
| 5 | Parity CI check: every board mutation has a REST route and an MCP tool | **1-2 days** |
| 6 | GitHub card <-> issue sync with GitHub-wins conflict resolution | **5-7 days** |
| | **Core loop (1-3)** | **~3.5 weeks** |
| | **Full RFC (1-6)** | **~5.5-6 weeks** |

Highest-variance item is Phase 6 (sync and conflict handling always costs more
than it looks). Lowest-risk items are 4 and 5.

### Design corrections this spike recommends folding into Phase 1

1. **Cards get their own table.** `store.py`'s `reconcile_snapshot`,
   `prune_duplicate_stages`, `prune_stuck` and `prune_stalled` exist to delete and
   rewrite work-item rows from upstream polls. Human-owned fields must not sit
   where that machinery can reach them. RFC-0019 §7 proposes to mitigate this
   with a precedence rule; a separate table makes the rule unnecessary.
2. **`/mcp` needs scopes before it gets write tools.** Today `_verify_mcp_token`
   is one shared secret that **accepts everything when unset**. Ship the scope
   model first.
3. **Drop "publish an unauthenticated OpenAPI 3.1 spec" from Phase 2's scope.**
   FastAPI already serves it at `/openapi.json` and the enforcement middleware
   already exempts it. It should be a test asserting the property, not a task.
4. **Conform to `agentskills.io` v0.2.0 in Phase 4**, including per-entry
   `sha256`, rather than inventing a manifest shape.

### What would change this recommendation

- **utter.ae publishes a self-hosted or on-premise licence.** This is the single
  fact that reopens the question. It would not automatically flip the decision
  (the GitHub-sync and fleet-concept-mapping problems remain), but the gate would
  no longer be a gate and the matrix would be worth re-scoring.
- **The fleet's self-hosting requirement is relaxed** for the planning layer
  specifically — for example, a hosted control plane over self-hosted execution.
  That is a positioning decision, not an engineering one.
- **Phase 1 overruns badly.** If the `cards` table plus CRUD plus backlog view
  is not demonstrably working inside three weeks, the estimate was wrong and the
  build-vs-buy maths should be redone rather than pushed through.
- **Credible third-party evidence about utter.ae emerges** that contradicts the
  first-party picture — in particular, a self-host offering, a published security
  posture, or a native GitHub sync. All findings here rest on vendor-controlled
  pages and should be re-verified before anyone relies on them.

---

## 5. Open questions for the human, before Phase 1

1. **Confirm the gate.** Is self-hosting genuinely non-negotiable for the
   planning layer, or only for execution? Everything above rests on
   "non-negotiable". If it is negotiable, this spike should be redone.
2. **Card id scheme** (RFC-0019 §8, still open). `FCT-N` global or per-workspace?
   And what is its relationship to `correlation_key`, which is today the GitHub
   issue number with a synthetic fallback (`models.py:315`)? Options: card id is
   the correlation key; card id is separate and the correlation key is populated
   on promotion; or the card id becomes the synthetic fallback for pre-GitHub
   work. The third is the most useful and the most invasive.
3. **Do cards exist before a GitHub issue does?** RFC-0019 §3.5 says creating a
   `ready` card can "open or adopt" an issue. If a card may live in `draft`
   without an issue, we have a window where GitHub is *not* the record of truth
   for that card. Is that acceptable, and for how long?
4. **Who may write to the board?** Reuse the existing `read`/`write` scopes, or
   introduce a `plan` scope so an agent can groom the backlog without inheriting
   the ability to approve a plan or delete a task (both currently `write`)?
5. **Scope of Phase 1's view work.** Backlog plus editable Kanban only, or is a
   milestone/roadmap view in v1? RFC-0019 §3.1 lists three views; §4 defers
   calendar/Gantt. Confirm the milestone view is in.
6. **Does the fleet manifest go behind auth?** utter serves
   `/.well-known/agent-skills/index.json` publicly. For a self-hosted fleet the
   manifest enumerates internal capabilities to anyone who can reach the host.
   Public (matching the convention) or authenticated (safer, less discoverable)?
7. **Multi-tenancy for cards.** `work_items` is tenant-partitioned
   (`store.py:353`, `scoped()` at line 423). Cards should follow — confirm, and
   confirm whether card ids are unique per tenant or globally.
8. **Is Phase 6 in the first cut at all?** Without it the board and GitHub drift
   from day one. With it, the RFC roughly doubles in size. A defensible middle:
   ship Phases 1-3 with a one-way card -> issue creation only, and defer
   bidirectional mirroring.

---

## 6. Sources

CFactory codebase at commit `86bdfcd`, read 2026-07-25:
`apps/backend/cfactory/{models,store,mcp,app,auth,actions,routes_workitems,routes_actions}.py`,
`apps/backend/migrations/versions/{05d233b19ee9_create_work_items,a7c3f2e19b40_work_items_tenant_id}.py`,
`apps/backend/requirements.txt`, `apps/frontend-web/src/` (57 files).

utter.ae first-party surfaces, all fetched 2026-07-25 and all unauthenticated:
`https://utter.ae`, `https://utter.ae/pricing`,
`https://utter.ae/.well-known/agent-skills/index.json`,
`https://utter.ae/.well-known/mcp/server-card.json`,
`https://utter.ae/api/v1/openapi.json`.
`https://utter.ae/docs` and `https://utter.ae/integrations` both returned HTTP 404.

Web search returned no results referencing utter.ae across four queries. No
third-party source corroborates any claim in section 2.
