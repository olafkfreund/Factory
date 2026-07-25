---
layout: default
title: "RFC-0020: Multi-Provider Git Integration and Tenant-Configured Projects — the board syncs to the host you actually use"
permalink: /rfc/multi-provider-git-integration/
---

# RFC-0020 — Multi-Provider Git Integration and Tenant-Configured Projects

> **Status:** Proposed · **Created:** 2026-07-25 · **Owner:** CFactory ·
> **Extends:**
> [RFC-0003](./0003-github-agentic-integration.md) (GitHub integration — this generalises it to the other hosts),
> [RFC-0007](./0007-access-and-credential-provisioning.md) (credential provisioning — the custody model here is an instance of it),
> [RFC-0011](./0011-label-driven-intake-and-difficulty-tiers.md) (intake — which already promises uniform GitHub/GitLab/Azure DevOps),
> [RFC-0019](./0019-agent-native-planning-control-plane.md) (planning board — section 3.5 card/issue sync is the thing being generalised) ·
> **Affects:** CFactory (vendors the canonical provider layer, new tenant git-config resource, issue import, explicit stage actions, settings UI + MCP twins); the Factory hub (`shared/factory-github/` gains a fourth consumer and its drift gate; `apis/planning-card.schema.json` gains a `description` field in Phase 6). Task-contract change limited to provider-qualifying the existing repo reference (Phase 5).

## 1. Motivation

Two env vars decide which git host and which project the cockpit talks to:

```
CFACTORY_INTAKE_PROJECT_ID   # which project intake files into
CFACTORY_GITHUB_TOKEN        # the credential it files with
```

Both are process-global and both are GitHub-shaped. That has three consequences:

- **You cannot change your project without a redeploy.** The one piece of
  configuration a user most wants to set — "which repo does my backlog sync
  to?" — is the one piece they cannot reach from the portal.
- **A multi-tenant cockpit has a single-tenant integration.** CFactory already
  supports `CFACTORY_MULTI_TENANT` and `X-Tenant-Id`, and the board is already
  tenant-scoped (RFC-0019). The git integration underneath it is not. Every
  tenant would file into whatever project the operator's env var names.
- **GitLab users have no path at all.** RFC-0011 states the intake surface is
  uniform across GitHub, GitLab and Azure DevOps. The board is not.

### 1.1 Connecting a repo has to bring the work with it

Configuration alone is not the feature. RFC-0019 Phase 6 sync is **card-first
only**: a card can create an issue, or adopt one you name. There is no path that
pulls a repository's *existing* issues in. Connect a repo with 200 open issues
today and the board stays empty, which makes it useless to everyone except
someone starting from nothing.

The same gap exists on the other end of the card's life. Dispatch is *implicit*:
a card promoted to `ready` with a tier goes wherever its tier says (low/medium to
AIFactory build, hard to PFactory planning). There is no way to say "plan this",
"just build this", "re-verify this" from the board. The routing is a policy, not
a control.

So the board today can neither absorb the work that already exists nor drive the
factory deliberately. Sections 3.6 and 3.7 close those two, and they are the
difference between "the board syncs" and "the board is where you work".

### 1.2 The motivating finding: duplicated capability

The reason GitLab is missing from the board is not that the fleet lacks a GitLab
implementation. **It has one, and CFactory reimplemented past it.**

`shared/factory-github/providers/` in this hub is the canonical VCS layer, with a
`GitProvider` Protocol and three working implementations (GitHub, GitLab, Azure
DevOps) selected by `get_provider(provider_type, repo, **kwargs)`. PFactory,
AIFactory and TFactory each vendor that layer and guard it with a pinned-SHA
drift gate (`.github/workflows/factory-github-drift.yml`).

CFactory does neither. Its RFC-0019 Phase 6 sync module,
`apps/backend/cfactory/github_sync.py`, hardcodes GitHub directly: raw
`/repos/{owner}/{repo}/issues` paths, an `X-GitHub-Api-Version` header, and
GitHub's issue JSON shape parsed inline. An `owner/repo#123` reference format is
baked into the card store's `issue_ref`.

So the fleet solved this problem once, generically, and the newest service solved
it again, specifically. Stating it plainly because it is the whole motivation:
**the work here is mostly deletion.** Vendor the canonical layer, call the
protocol, and GitLab and Azure DevOps arrive with it — no second GitLab client,
no second auth path, no second rate limiter.

## 2. What we already have (and what is missing)

| Primitive | Today | Gap this RFC closes |
|---|---|---|
| Provider abstraction | `shared/factory-github/providers/protocol.py` — `GitProvider` with `create_issue` / `fetch_issue` / `fetch_issues` / `close_issue` / `add_comment` / labels / PR ops | CFactory does not use it |
| Provider implementations | GitHub, GitLab, Azure DevOps (Bitbucket/Gitea are stubs) | Not reachable from the board |
| Consumption model | Vendor canonical + pinned-SHA drift gate, in PFactory / AIFactory / TFactory | CFactory has no copy and no gate |
| Board sync | `github_sync.py`, GitHub-hardcoded, `owner/repo#123` refs | Provider-agnostic refs and calls |
| Project selection | `CFACTORY_INTAKE_PROJECT_ID` (global env) | Tenant-scoped, portal-editable |
| Credential | `CFACTORY_GITHUB_TOKEN` (global env) | Tenant-scoped custody, obtained by install not by paste |
| Settings precedent | `PUT /api/settings/copilot` persists provider + model, **never** the key | The same shape, extended to git — with the credential question answered honestly rather than deferred |
| Tenancy | `CFACTORY_MULTI_TENANT`, `X-Tenant-Id`, tenant-scoped cards | Integration config is not tenant-scoped |
| Issue listing | `fetch_issues(IssueFilters)` — `state`, `labels`, `author`, `assignee`, `since`, `limit`, `include_prs`, provider-agnostic | Nothing calls it: sync is card-first, so a repo's existing issues never reach the board |
| Dispatch transport | `actions.py` routes to PFactory, AIFactory **and** TFactory (`tfactory_api_url` configured) | `card_intake.py` uses only two of the three, and only implicitly, driven by tier |

## 3. Design

### 3.1 Vendor the canonical provider layer into CFactory

CFactory adopts the fleet's existing consumption model rather than inventing a
fourth one:

- Vendor `shared/factory-github/` (`gh_client.py`, `rate_limiter.py`,
  `providers/`) into CFactory at the same path its siblings use
  (`apps/backend/runners/github/`), byte-for-byte, at a pinned hub SHA.
- Add `.github/workflows/factory-github-drift.yml` to CFactory, matching the
  sibling gate. Reconcile drift by **re-vendoring from the hub**, never by
  editing the copy — the rule already documented in
  `shared/factory-github/README.md`.
- Add `shared/factory-github/` to hub CODEOWNERS review if it is not already,
  because a canonical change is now a four-repo change.

No canonical change is required for Phase 1. The protocol already exposes
everything `github_sync.py` needs: `create_issue`, `fetch_issue`, `close_issue`,
`add_comment`, `apply_labels`.

### 3.2 Refactor `github_sync.py` onto the protocol

`github_sync.py` becomes `git_sync.py`: same RFC-0019 section 3.5 semantics
(mirrored fields vs planning-only fields, "the host wins" on conflict, fail-safe,
`issue_ref` non-NULL as the idempotency key), with every HTTP call replaced by a
protocol call against a provider constructed from the tenant's config.

One schema-visible change: `issue_ref` stops being `owner/repo#123` and becomes a
provider-qualified reference —

```
github:owner/repo#123
gitlab:group/subgroup/project#45
azure_devops:org/project/repo#7
```

— parsed and validated with the same anchored, character-restricted regexes the
current module already uses, because the ref is still interpolated into a request
path. Existing unqualified refs read as `github:` for backward compatibility;
new writes are always qualified. GitLab's `group/subgroup/project` nesting is why
the repo segment must allow more than one slash, which today's `_REPO_RE` does
not.

**This phase alone delivers GitLab and Azure DevOps board sync.** It depends on
nothing in 3.3 or 3.4: a deployment that keeps using env-supplied credentials
gets multi-provider support the day this lands.

### 3.3 Tenant-scoped git configuration

Git configuration becomes a **tenant-level resource**, not a global env var and
not a per-card field. A tenant has exactly one git configuration:

| Field | Meaning |
|---|---|
| `provider` | `github` \| `gitlab` \| `azure_devops` (the `ProviderType` values already implemented) |
| `base_url` | Host root; defaults per provider. Present so self-hosted GitLab / GitHub Enterprise work |
| `project` | `owner/repo`, or a GitLab group path, or `org/project/repo` for ADO |
| `intake_project` | Optional; where intake files if different from the sync target. Defaults to `project` |
| `default_labels` | Optional labels applied to cards the board opens |
| `status` | Derived: `unconfigured` \| `configured` \| `credential_missing` \| `verified` |

Surface, obeying the RFC-0019 section 3.3 parity law (CI-enforced by CFactory's
`tests/test_board_parity.py` — every mutation needs a REST **and** an MCP twin):

- `GET/PUT /api/tenants/{tenant}/git-config` plus a `POST .../git-config:verify`
  that does one cheap read (`get_repository_info`) and records `status`.
- MCP twins: `get_git_config`, `set_git_config`, `verify_git_config`.
- A cockpit Settings panel modelled on the existing copilot settings view.

`CFACTORY_INTAKE_PROJECT_ID` is **retired as a global**. It survives one release
as a seed: on first boot, if a tenant has no git config and the env var is set,
it materialises the default tenant's config, which is then editable and
authoritative. After that release the env var is removed.

### 3.4 Credential custody

The user's decision is **OAuth / installed-app custody**. Encoding it, with the
correction stated up front because it changes what Phase 3 has to build:

> **OAuth changes how the credential is obtained, not whether it is stored.**
> An install flow means nobody pastes a long-lived PAT into a form — but the
> access token, or the refresh token, or the App private key still lands in
> CFactory and must survive a restart. Encrypted-at-rest storage is therefore
> required either way. It is not something OAuth lets us skip, and it is open
> work: it belongs to the compliance track (Factory#314/#315), not to this RFC.

Given that, the target per provider:

- **GitHub: a GitHub App, not an OAuth App.** An App mints short-lived (one
  hour) installation tokens, scoped to the repositories the installer selected,
  and acts as its own identity rather than impersonating the person who clicked
  install — so the audit trail says "Factory" and a departing employee does not
  take the integration with them. CFactory stores the App private key (one
  secret, deployment-wide) plus a per-tenant `installation_id` (not a secret).
  That is a materially smaller stored-credential blast radius than a PAT per
  tenant, which is the real argument for the App.
- **GitLab: an OAuth application, or a group access token.** GitLab's App
  equivalent is a group access token or an OAuth app with refresh; both store a
  token, so the encrypted store is unavoidable here.
- **Azure DevOps:** out of scope for the install flow in this RFC. It works via
  the stored-credential path from Phase 3.

Phasing follows the honesty above rather than the marketing order:

1. Phase 3 builds the **encrypted tenant credential store** — the thing that is
   needed in every scenario, PAT or OAuth. Until it exists, a multi-tenant
   deployment cannot hold per-tenant credentials at all, and Phase 2's config
   resource runs against the deployment's env-supplied credential (safe for
   single-tenant, explicitly not for multi-tenant).
2. Phase 4 puts the **install flow** in front of it, so the store gets filled by
   an OAuth callback rather than by a paste box.

The callback endpoint needs one deployment decision: CFactory sits behind
oauth2-proxy at `https://cfactory.freundcloud.org.uk` (callback
`/oauth2/callback`). A provider redirect arrives unauthenticated and would be
bounced to login, losing the `code`. Either the App callback path is exempted
from oauth2-proxy with its own `state` + signature verification, or it is hosted
on `https://cfactory-mcp.freundcloud.org.uk`. Exempting a path in the auth
perimeter is a security change and needs the review to match; the MCP host is the
lower-risk default.

### 3.5 The fleet follows the tenant, not the env

RFC-0011 label intake, the auto-PR path and the RFC-0009 merge gate all run
against the provider each downstream service is configured for. Once a tenant
declares its provider on the board, the same declaration should reach PFactory,
AIFactory and TFactory so a GitLab tenant's PARR run does not open a GitHub PR.
The task contract already carries a repo reference; this extends it with the
provider qualification from 3.2 and nothing more.

**Known reduction in the agentic surface for non-GitHub tenants**, stated rather
than discovered later: `assign_to_user` raises `NotImplementedError` on GitLab
and Azure DevOps (Duo Workflow is partial), and `enable_auto_merge` — the
RFC-0011 low-tier auto-merge-when-green path — is GitHub-shaped. A GitLab tenant
gets board sync, intake and PARR; it does not get Copilot assignment or
auto-merge until those provider methods are implemented. That is a capability
matrix to publish, not a blocker.

### 3.6 Import: the repository's existing issues become cards

Connecting a repo populates the board. The protocol already has the read side —
`fetch_issues(IssueFilters)`, where `IssueFilters` carries `state` (default
`"open"`), `labels`, `author`, `assignee`, `since`, `limit` (default 100) and
`include_prs` (default `False`) — and it is provider-agnostic, so import works on
GitLab and Azure DevOps for free.

**Backfill.** On connect (and on demand via an explicit action), import **all
open issues**, not a label-filtered subset. Recommending the wider default
deliberately: the user's mental model of "connect my repo" is "show me my
backlog", and a filter that silently hides most of it produces the worst failure
mode this feature has — "where are my issues?" — with no error to diagnose. A
label filter is available as opt-in configuration (`import_labels`), and
`import_state` may be widened to `all`, but neither is the default. `include_prs`
is pinned `False` and is **not** configurable: a pull request is not a plan, and
a board full of PR cards is noise nobody asked for.

`limit` defaults to 100, so backfill pages to completion rather than taking the
first page. It carries a ceiling (`import_max`, default 1000) and — per the fleet
rule against silent caps — when the ceiling truncates, the import result says so
explicitly and the Settings panel shows how many were dropped.

**Ongoing reconciliation.** Issues filed after connect must appear, and without
webhooks that is a poll. Saying it plainly rather than implying freshness:
RFC-0019 Phase 6 deferred inbound webhooks and this RFC does not undefer them
(section 4), so **import is not live**. Design:

- A `last_synced_at` watermark per tenant git-config, set to the maximum
  `updated_at` observed in the previous pass, **minus a 60-second overlap** to
  tolerate clock skew between us and the host. Overlapping re-reads are free
  because import is an upsert.
- Poll with `IssueFilters(since=watermark, state="all", include_prs=False)`.
  `state="all"` on the incremental pass, not `"open"`, because closures and
  reopenings are exactly the changes the board would otherwise miss.
- Cadence: default 5 minutes, configurable per tenant. Fast enough that a board
  is rarely more than one coffee out of date, slow enough that a hundred tenants
  do not exhaust a rate limit.
- The board surfaces "last synced" as a timestamp, for the same reason RFC-0019
  stores `issue_state` rather than inferring it: staleness should be visible, not
  assumed away.

**Idempotency.** Re-running import must never duplicate a card. This is the
single most likely bug in the feature, so it is enforced by the database and not
by application logic: a **UNIQUE index on (`tenant_id`, `issue_ref`)**, with the
provider-qualified ref from section 3.2 as the key, and import written as an
upsert against it. An application-level "does this exist?" check does not survive
two concurrent polls; a unique constraint does. A card that already carries an
`issue_ref` is updated in place — the same code path as adopting an issue
somebody else filed.

**Mapping.**

| Issue field | Card field | Ownership |
|---|---|---|
| `title` | `title` | mirrored (host wins) |
| `body` | `description` (new field — see below) | mirrored (host wins) |
| `labels` matching `factory:<tier>` | `tier` (`low`/`medium`/`hard` — note `hard`, not `high`) | mirrored |
| other `labels` | `labels` | mirrored |
| `assignees[0]` | `assignee` | mirrored |
| `milestone` | `milestone` (the title — already the documented semantics) | mirrored |
| `state` | `issue_state`, and `status` per the rule below | mirrored |
| — | `acceptance_criteria` | **not** derived from the body |
| — | `priority` | planning-only, default 100 |

Two of those need their reasoning on the record.

*The body does not become acceptance criteria.* `acceptance_criteria` is a list
of testable statements that dispatch turns into the RFC-0002 task contract's
criteria; parsing prose into that list would **fabricate** the thing the factory
verifies against. Import leaves it empty, which is a legal planning state, and
the board shows a dispatch-readiness warning on a card that has none.

*The body needs somewhere to go, and the card contract has no field for it.*
`apis/planning-card.schema.json` has no `description`. Importing an issue without
its body produces a title-only card, which is not a plan. So Phase 6 includes a
**contract change**: add `description` (free-form markdown, nullable) to the card
resource, `card_create` and `card_patch`, with the schema, the examples and the
contracts CI updated. It is classified as a *mirrored* field — the host owns it,
like `title` — which keeps RFC-0019 section 3.5's property that no field has two
owners, so "the host wins" stays a one-line rule instead of a merge algorithm.

**An imported card never dispatches. This is a safety property, not a default.**
An open issue imports as `backlog`; a closed issue imports as `done`. Neither is
ever `ready`. The dispatch trigger is `ready` + a tier, and issues commonly carry
`factory:low` labels already — so importing 200 of them as `ready` would fire 200
builds from a single "connect repo" click. Import is therefore forbidden from
producing `ready` at all, in the importer and in a test that asserts it.

**Closure, deletion and disappearance.**

- *Issue closed on the host* -> `issue_state: closed`, card `status: done`.
  Reopened -> back to `backlog`.
- *Card already in the factory* (non-NULL `correlation_key`) -> the poll mirrors
  `title`, `description`, `labels` and `issue_state`, but **not** `status`. A run
  in flight owns its status; a poll must not stomp it back to `backlog` because
  someone reopened the issue.
- *Card deleted locally* -> the issue is **not** touched. Deleting a card means
  "not on my board", never "destroy the record of truth". It is a soft delete
  (`deleted_at`), which both keeps the unique index doing its job and stops the
  next poll resurrecting the card — the resurrection failure RFC-0019 already
  names as a risk.
- *Issue deleted or transferred on the host* -> a 404 on the next poll sets
  `issue_state: missing`. The card stays. Human planning data is not destroyed by
  a 404.

### 3.7 Explicit stage actions: plan, code, test, or the whole sequence

Give the board buttons that push a card into a specific stage, and one that runs
the sequence. The transport already exists: `actions.py` routes to all three
services (`Service.PFACTORY`, `Service.AIFACTORY`, `Service.TFACTORY`, with
`tfactory_api_url` configured). `card_intake.py` simply only ever calls two of
them. Phase 7 is wiring, not new plumbing.

**Surface** (parity law, section 3.3 of RFC-0019 — each REST mutation ships its
MCP twin in the same PR or `tests/test_board_parity.py` fails):

| REST | MCP twin | Effect |
|---|---|---|
| `POST /api/cards/{key}/actions/plan` | `plan_card` | dispatch to PFactory |
| `POST /api/cards/{key}/actions/code` | `code_card` | dispatch to AIFactory |
| `POST /api/cards/{key}/actions/test` | `test_card` | dispatch to TFactory |
| `POST /api/cards/{key}/actions/run` | `run_card` | plan -> code -> test in sequence |

**An explicit action overrides tier routing.** The tier still supplies the
*payload* (model, planning depth, the `factory:<tier>` label AIFactory's
classifier reads); the button decides the *destination*. A `low` card can be sent
to PFactory because a human wants a plan first; a `hard` card can be sent
straight to AIFactory because a human already has one. A NULL tier still refuses,
for the same reason implicit dispatch refuses: there is no payload to build.

**Preconditions — refuse, never dispatch into nothing.** Every refusal is a 409
with a machine-readable reason code and a human sentence; never a silent no-op.

- `plan` — requires a tier. Nothing else.
- `code` — requires a tier. Permitted with or without a prior plan: that is the
  existing low/medium path. A `hard` card built without a plan is allowed but the
  response carries a warning naming the skipped stage, because refusing would
  make a button the user pressed lie about what it does.
- `test` — requires something to verify: a non-NULL `correlation_key` **and** a
  completed AIFactory build stage on the work-item timeline. Asking to test a
  card that was never built is refused with `no_build_to_verify`. This is the
  case the whole precondition rule exists for.
- Any stage — refused while that same stage has a live dispatch
  (`stage_already_running`).

**Idempotency, and the one RFC-0019 rule this changes.** Today
`correlation_key` non-NULL *is* the idempotency check: already in the factory,
do not dispatch. That rule is precisely what makes a multi-stage sequence
impossible — after `plan` the key is set, so `code` would be refused. So it is
refined: **a non-NULL `correlation_key` no longer means "do not dispatch"; it
means "this card is joined to a run, reuse its key".** Per-stage idempotency
moves to a per-stage dispatch record (`stage`, `service`, `dispatched_at`,
upstream ref, terminal status). A card cannot hold two live dispatches of the
same stage. The write-once property of `correlation_key` is untouched: it is
still set exactly once and a server still rejects re-pointing it at a different
key.

**The sequence.** `run` executes plan -> code -> test, advancing a stage only
when the previous one reaches a terminal-success status on the existing work-item
timeline. A stage already recorded complete is **skipped, not re-run**, which is
what makes `run` safe to press again after a failure — it resumes rather than
restarts. A failed stage stops the sequence, sets the card `blocked`, and records
the reason. There is no new orchestrator: the sequence advances off the status
write-back that already threads PARR events, which means honestly that it
advances at write-back cadence, not instantly.

**Status write-back across a sequence.** `card_status_for()` maps a runtime state
onto the card status enum, and a completed *stage* currently maps to `done` — so
a sequenced card would flash "done" the moment planning finished. The sequence
therefore records its remaining stages, and write-back may only resolve a card to
`done` when none remain; until then it holds `in_progress`. Without that, the
board lies twice per run.

## 4. Non-goals

- **Not new providers.** Bitbucket and Gitea stay stubs. This RFC only makes the
  three implemented providers reachable.
- **Not a secret manager.** CFactory does not become one; it consumes whatever
  the compliance track (Factory#314/#315) settles on. Noting the standing
  correction from that work: SOPS is not currently a real secret backend in this
  deployment.
- **Not per-card or per-board provider selection.** One git config per tenant.
- **Not a change to the record of truth.** The git host — whichever one — stays
  authoritative (RFC-0003, RFC-0019 section 3.5). The board remains a projection.
- **Not inbound webhooks.** RFC-0019 Phase 6 deferred live inbound sync; this RFC
  does not undefer it. Import (3.6) is therefore poll-based and a board can be
  minutes stale, which is stated in the UI rather than papered over. It does mean
  a future webhook receiver needs per-provider signature verification
  (`X-Hub-Signature-256` vs `X-Gitlab-Token`).
- **Not two-way field sync.** Import (3.6) adds a read direction; it does not add
  a write direction. RFC-0019 section 3.5's single card-to-issue write (create,
  once) is unchanged, and no local edit to a mirrored field is ever pushed up.
- **Not an orchestrator.** The sequence in 3.7 advances off the existing status
  write-back. No scheduler, no queue, no retry policy engine.
- **Not a migration of the other three services' vendored copies.** They already
  have theirs.

## 5. Phases

Effort is honest working time for one engineer, not a sprint-planning fiction.

| Phase | Scope | Effort | Depends on |
|---|---|---|---|
| 1 | Vendor `factory-github` into CFactory + drift gate; refactor `github_sync.py` -> `git_sync.py` onto `GitProvider`; provider-qualified `issue_ref` + migration | ~1 week | nothing |
| 2 | Tenant git-config resource: model, REST, MCP twin, cockpit Settings panel, `:verify`, seed-then-retire `CFACTORY_INTAKE_PROJECT_ID` | ~1 week | 1 |
| 3 | Encrypted tenant credential store; per-tenant credential injection into the provider (env-per-invocation, never argv) | ~2 weeks | 2, and a decision from Factory#314/#315 |
| 4 | GitHub App install flow + GitLab OAuth/group token; callback hosting + oauth2-proxy exemption; token refresh | ~2-3 weeks | 3 |
| 5 | Fleet propagation (3.5): provider qualification through the task contract to PFactory/AIFactory/TFactory; publish the capability matrix | ~1 week | 1, 2 |
| 6 | Issue import (3.6): backfill, poll reconciliation with watermark, unique-index dedupe, mapping, `description` contract change, closure/delete semantics | ~1.5 weeks | 1, 2 |
| 7 | Explicit stage actions (3.7): four REST routes + four MCP twins, preconditions, per-stage dispatch record, sequence runner, write-back fix | ~1 week | nothing new (RFC-0019 Phase 3 dispatch) |

**Phase 1 is the whole GitLab story on its own.** It is not blocked by, and
should not wait for, any of the credential work. Phases 1 and 2 together deliver
the user's literal ask for a single-tenant deployment: pick your provider and
project in the portal, and the Backlog/Planning board syncs to it. Phases 3-4 are
what make the same thing safe to offer to more than one tenant.

Phase 3 is where the real risk sits, and it is deliberately the phase that does
not depend on OAuth being finished — because the store is needed either way.

**Phase 6 is what makes phases 1-2 worth having.** A configurable, multi-provider
connection to an empty board is a demo; the same connection that fills the board
with the work already in the repo is the feature. It should follow Phase 2
immediately, ahead of the credential work, on every deployment that has a
credential already.

**Phase 7 depends on none of the provider work** and can be built in parallel by
a second pair of hands. It touches dispatch and the card store, not the git
layer.

## 6. What it unlocks

- **GitLab and Azure DevOps users can use the board**, which RFC-0011 already
  promised and RFC-0019 could not deliver.
- **The portal configures the portal.** No redeploy to change a project.
- **Multi-tenant becomes real**, rather than nominal-with-a-shared-token.
- **One VCS client in the fleet instead of two.** A bug fixed in the canonical is
  fixed for four services.
- **Connecting a repo shows you your actual backlog**, on any of the three
  providers, instead of an empty board — the point at which the planning surface
  stops being a demo.
- **Deliberate control of the factory from the board:** plan this, build this,
  verify this, or run the lot, instead of a routing policy inferred from a label.

## 7. Risks

- **Credential blast radius.** A stored token with repo write across tenants is
  the highest-value secret CFactory would ever hold. Mitigations: the GitHub App
  path (short-lived installation tokens, repo-scoped, one deployment-wide private
  key instead of N tenant PATs), encryption at rest, and RFC-0001a audit-chain
  entries on every credential read.
- **The GitHub provider is `gh`-CLI-backed, and `gh` auth is process-ambient.**
  `GitHubProvider` wraps `gh_client.py`, which shells out; its credential comes
  from the process environment. Per-tenant credentials therefore need a
  per-invocation subprocess environment, and the token must never appear in
  argv (visible in `/proc`, in shell history, and in any command log). The GitLab
  provider already takes an explicit `_token` and `_base_url`, so it needs no
  such care — the asymmetry is a trap worth naming.
- **Drift-gate ossification.** A fourth consumer means a canonical change is now
  four re-vendors and four SHA bumps. Mitigation: it is already the documented
  process; the cost is real but linear, and cheaper than the divergence it
  replaces.
- **`issue_ref` migration.** Changing the ref format touches stored rows.
  Mitigation: unqualified refs read as `github:`, so the migration is
  read-compatible and the backfill can be lazy.
- **Parity-law regression.** New settings mutations without an MCP twin fail
  `tests/test_board_parity.py`. Mitigation: this is the gate working; write the
  twin in the same PR.
- **oauth2-proxy exemption widens the perimeter.** A misconfigured exemption is a
  hole, not a feature. Mitigation: prefer the MCP host; if exempting, verify
  `state` and the provider signature inside the handler and scope the exemption
  to the exact callback path.
- **Capability asymmetry surprises users.** A GitLab tenant expecting auto-merge
  gets `NotImplementedError`. Mitigation: publish the capability matrix in Phase
  5 and surface it in the Settings panel next to the provider selector.
- **Import duplicates cards.** The likeliest bug in Phase 6, and the one a user
  notices instantly. Mitigation: a UNIQUE index on (`tenant_id`, `issue_ref`) and
  an upsert, not an application-level existence check — plus a test that runs the
  importer twice and asserts the card count is unchanged.
- **A large repo floods the board.** Importing thousands of issues makes the
  backlog unusable and burns rate limit. Mitigation: `import_max` with the
  truncation reported rather than silent, the optional `import_labels` filter,
  and open-only by default.
- **Import mass-dispatches.** The highest-consequence failure in this RFC:
  imported issues carrying `factory:low` labels landing as `ready` would fire a
  build per issue. Mitigation: import can produce only `backlog` or `done`, never
  `ready`, asserted by a test whose failure mode is "someone made import smarter".
- **Poll cost scales with tenants.** Mitigation: `since` watermark so each pass
  reads only what changed, a per-tenant cadence, and the provider layer's
  existing `rate_limiter.py`.
- **Relaxing the `correlation_key` dispatch guard (3.7) re-opens double
  dispatch.** That guard is the only thing stopping a card being built twice
  today. Mitigation: the per-stage dispatch record replaces it before it is
  relaxed, in the same change, with a concurrent double-press test.
- **A sequenced card reports `done` mid-run.** Real today in
  `card_status_for()`. Mitigation: the remaining-stages marker in 3.7, and a test
  that a card mid-sequence never reads `done`.

## 8. Open questions

- **Where does the encrypted credential actually live?** CFactory's Postgres with
  an envelope key, or an external manager? This is Factory#314/#315's call and
  Phase 3 is blocked on it; SOPS is not a real backend here today.
- **Who owns the GitHub App registration?** A Factory-owned App serves the hosted
  deployment, but a self-hosted operator must be able to register their own —
  which means App credentials become deployment configuration, and the
  registration steps become documentation.
- **Self-hosted GitLab / GitHub Enterprise CA trust.** `base_url` covers the
  address; it does not cover a private CA. Does the cockpit image need a
  configurable trust store?
- **Does `intake_project` earn its place**, or is one `project` per tenant
  enough? Shipping both fields is speculative; the lazy answer is one field until
  someone asks for two.
- **Does a tenant ever need more than one git config** (a second repo, a second
  host)? Assumed no. If yes, the config becomes a list and `issue_ref` needs to
  name which one — which the provider qualification in 3.2 already half-solves.
- **Token refresh failure semantics.** When a refresh token expires, the board
  should degrade to `credential_missing` and keep serving rather than fail
  writes silently. Where is that surfaced — the card, the Settings panel, or an
  alert?
- **Does `since` mean the same thing on all three providers?** GitHub filters by
  `updated_at`. GitLab and Azure DevOps need verifying before the watermark is
  trusted; if one filters by creation instead, the incremental pass silently
  misses edits and the poll must fall back to a full compare for that provider.
- **Is `description` the right contract change**, or should the issue body live
  outside the card resource (a linked body blob) so the card stays a planning
  record? Shipping it on the card is the lazy answer and probably right, but it
  is a schema change to a published contract and deserves the question.
- **Should a re-import ever revive a soft-deleted card?** "I deleted this by
  mistake" and "stop showing me this" want opposite answers. Assumed: stays
  deleted, with an explicit undelete action if anyone asks.
- **Default poll cadence.** Five minutes is a guess informed by nothing but
  taste. Revisit once a real tenant has a real repo attached.
- **Should `run` be resumable across a restart?** The sequence state lives in the
  per-stage dispatch record, so in principle yes; whether anything drives it
  forward after a cockpit restart depends on where the advance loop lives.
