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
> **Affects:** CFactory (vendors the canonical provider layer, new tenant git-config resource, settings UI + MCP twin); the Factory hub (`shared/factory-github/` gains a fourth consumer and its drift gate). No task-contract changes.

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

### 1.1 The motivating finding: duplicated capability

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
  does not undefer it. It does mean a future webhook receiver needs per-provider
  signature verification (`X-Hub-Signature-256` vs `X-Gitlab-Token`).
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

**Phase 1 is the whole GitLab story on its own.** It is not blocked by, and
should not wait for, any of the credential work. Phases 1 and 2 together deliver
the user's literal ask for a single-tenant deployment: pick your provider and
project in the portal, and the Backlog/Planning board syncs to it. Phases 3-4 are
what make the same thing safe to offer to more than one tenant.

Phase 3 is where the real risk sits, and it is deliberately the phase that does
not depend on OAuth being finished — because the store is needed either way.

## 6. What it unlocks

- **GitLab and Azure DevOps users can use the board**, which RFC-0011 already
  promised and RFC-0019 could not deliver.
- **The portal configures the portal.** No redeploy to change a project.
- **Multi-tenant becomes real**, rather than nominal-with-a-shared-token.
- **One VCS client in the fleet instead of two.** A bug fixed in the canonical is
  fixed for four services.

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
