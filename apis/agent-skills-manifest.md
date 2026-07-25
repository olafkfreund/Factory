# Factory Agent-Skills Manifest (RFC-0019 Phase 4)

> Normative contract for `/.well-known/agent-skills/index.json`. Implements
> [RFC-0019](../docs/rfc/0019-agent-native-planning-control-plane.md) section 3.4
> (issue #302). Published by PFactory, AIFactory, TFactory and CFactory.
> Machine-readable schema:
> [`agent-skills-manifest.schema.json`](./agent-skills-manifest.schema.json).
> Reference instances: [`examples/agent-skills/`](./examples/agent-skills/).

The Factory already exposes a REST API and an MCP server per service, and ships
installable skills. What it lacks is the entry point: a way for an agent that
knows nothing about us to find out what we can do. This contract is that entry
point. One unauthenticated GET returns a service's identity, its skills, its MCP
endpoint and its OpenAPI URL; one more GET against the cockpit returns the same
for the whole fleet.

Phase 4 is independent of the Phase 1-3 board work: nothing here depends on how
(or whether) the planning board is built.

## 1. The endpoint

Every service MUST serve:

```
GET /.well-known/agent-skills/index.json
```

on the same origin as its API, returning `application/json` that validates
against `agent-skills-manifest.schema.json` with `kind: "service"`.

CFactory MUST additionally serve the fleet aggregate on the cockpit origin, at
the same path, with `kind: "fleet"`. The two are distinguished by `kind`, not by
path, so a consumer can point at any Factory origin and parse the answer without
knowing in advance which one it hit.

`.well-known` is reserved by RFC 8615; do not route it through the SPA fallback.
Several of the portals serve a single-page app and rewrite unknown paths to
`index.html` - a manifest that returns HTML is worse than one that 404s, because
the consumer cannot tell "not implemented" from "broken". Register the route
before the catch-all and assert the content type in a test.

## 2. No authentication, ever

**Reading the manifest MUST NOT require a credential**, from any origin.

This is the whole point of the convention: an agent enumerates capabilities
*before* it holds a token, and a partner integration evaluates us before anyone
provisions anything. A manifest behind auth is a manifest nobody discovers.

The same requirement extends to `openapi_url` (RFC-0019 section 3.3): the
OpenAPI document is readable without auth so an agent can enumerate the REST
surface before authenticating. *Invoking* anything is a different matter and is
authenticated as it is today; the manifest's `auth.schemes` says how.

Because it is public, the manifest is capability metadata and nothing else. It
MUST NOT contain secrets, tokens, tenant names, customer identifiers, internal
hostnames that are not already public, or any work-item state. `auth.manifest`
is pinned to the constant `"none"` so a consumer can assert the guarantee rather
than infer it, and so a future change that breaks it fails a schema check rather
than shipping quietly.

CORS: send `Access-Control-Allow-Origin: *` on this path. A browser-based agent
is a first-class consumer.

## 3. What a manifest says

| Field | Required | Meaning |
|---|---|---|
| `schema_version` | yes | Manifest schema version, currently `"1"` |
| `kind` | yes | `service` or `fleet` |
| `service.name` / `.version` | yes | Machine name (matches the Backstage component) and the **running service** version |
| `service.role` | no | PARR stage: `prepare` / `act` / `reflect` / `review` |
| `openapi_url` | yes | Absolute or origin-relative URL of the OpenAPI 3.x document |
| `mcp` | yes | `transport` plus `endpoint` (remote) or `command` (stdio) |
| `skills[]` | yes | One entry per capability: `name`, `description`, `invocation` |
| `auth` | no | `manifest: "none"` plus the schemes invocation accepts |
| `generated_at` | no | When the document was rendered |

### Skills

A skill entry answers one question: *what can I do here, and how do I call it?*

- `description` is the field an agent reasons over. Write it for a reader with
  no prior Factory knowledge - what the skill does and when to reach for it. A
  restated title is a wasted entry.
- `invocation` names exactly **one** concrete call, discriminated by `kind`:
  `slash_command` (`/handover`), `mcp_tool` (`task.create`), or `rest`
  (`POST /api/tasks/from-plan`). Programmatic equivalence (RFC-0019 section 3.3)
  means most capabilities are reachable over both REST and MCP; the manifest
  names the preferred route, and `openapi_url` plus `mcp` let an agent enumerate
  the rest. Listing every route per skill would duplicate the OpenAPI document
  and go stale against it.
- `install` is present only for skills shipped as a `SKILL.md` package, and
  points at the repo and the repo-relative path. Capabilities that are pure
  API/MCP surface have no `install` block.

**The list is curated, not a directory dump.** An entry MUST correspond to a
capability the service genuinely implements. A skill directory can drift - a
skill copied from a sibling repo and renamed still describes the sibling's
behaviour - and publishing that drift as a discovery manifest turns a local
tidiness problem into a contract that lies to external agents. Generating the
list from `.claude/skills` is fine; publishing it unreviewed is not.

## 4. The fleet aggregate

CFactory fetches the four service manifests and serves their union with
`kind: "fleet"`. Each `services[]` entry is a complete service manifest body
(envelope stripped) plus:

- `manifest_url` - the origin it was copied from, so a consumer can always go
  back to the source of truth;
- `fetched_at` - when that fetch last succeeded;
- `reachable: false` - set when the aggregator served a cached copy because the
  origin was down.

The aggregate is a **projection, never a source of truth**. A service's own
manifest wins on any disagreement, exactly as GitHub wins over the board in
RFC-0019 section 3.5. The aggregator MUST NOT edit skill entries as it folds
them in - the drift check in `tests/test_agent_skills_manifest.py` asserts the
folded body equals the origin.

Partial availability degrades, it does not fail: if one origin is unreachable,
serve the other three plus the stale entry marked `reachable: false`. An agent
with three quarters of the fleet can still work.

### 4.1 Services with no manifest at all

`reachable: false` covers the origin that was fetched once and is down now - the
aggregator still has a body to serve. It does not cover the origin the
aggregator has **never** reached: a cold start against a stopped service, or one
that does not serve a manifest yet. There is no body to fold in, and inventing a
version, an MCP endpoint or a skills list would put fiction in a discovery
document.

Such a service goes in `unavailable[]`, never in `services[]`:

```json
{
  "unavailable": [
    {
      "name": "tfactory",
      "title": "TFactory",
      "manifest_url": "https://tfactory.freundcloud.org.uk/.well-known/agent-skills/index.json",
      "reason": "unreachable",
      "checked_at": "2026-07-25T09:05:00Z"
    }
  ]
}
```

This keeps `services[]` strictly conformant - a consumer iterates it and reads
`skills`, `mcp` and `openapi_url` off every entry without defensive checks -
while the service is still announced rather than silently missing, so an agent
does not conclude the fleet is smaller than it is. `manifest_url` is included so
a consumer can retry the origin directly; it may be up again by the time it
asks.

`reason` is for a human reading the aggregate and MUST stay coarse
(`unreachable`, `manifest incomplete`). This document is public and
unauthenticated: raw exception text, stack traces and internal hostnames do not
belong in it.

## 5. Caching and versioning

**Caching.** The manifest is public, small and changes only on deploy:

- `Cache-Control: public, max-age=300` on a service manifest;
  `max-age=60` on the fleet aggregate, which is one hop staler by construction.
- Send a strong `ETag` over the serialised body and honour
  `If-None-Match` with `304`. Consumers SHOULD send it.
- CFactory SHOULD refresh its upstream copies on the same 5-minute cadence and
  MUST serve the last good copy rather than an error when an origin is down.

**Versioning.** Three independent version numbers, deliberately:

- `schema_version` - this contract. `"1"` today. Additive fields keep it;
  removing or repurposing a field bumps it. **Consumers MUST ignore unknown
  fields** rather than fail, which is what makes additive change safe.
- `service.version` - the running service. Bumps every deploy. With
  `generated_at` it is how a consumer decides a cached manifest is stale.
- Skill-level changes carry no version: a skill is identified by `name`, and
  `name` is stable. Renaming a skill is a removal plus an addition, and an agent
  holding the old name gets a clean "unknown skill" rather than silently
  different behaviour.

## 6. Rollout order

Ship per service, smallest blast radius first. Each step is independently useful
and none blocks the others.

| # | Service | Why this order | Done when |
|---|---|---|---|
| 1 | **TFactory** | Already publishes `docs/.well-known/skills/index.json` - the closest prior art, so it proves the contract against an existing implementation before anything is invented | `GET /.well-known/agent-skills/index.json` validates as `kind: service`; the older `docs/.well-known/skills/` path keeps working |
| 2 | **AIFactory** | The only service with a remote MCP transport (`/api/mcp-remote`), so it exercises the `endpoint`-required branch that stdio services never touch | Manifest validates and the remote MCP endpoint in it actually resolves |
| 3 | **PFactory** | Straightforward stdio service; also the point at which its skill directory gets the curation pass section 3 requires | Manifest validates and lists only capabilities PFactory implements |
| 4 | **CFactory (service)** | Same shape as the others; must land before the aggregate it will serve alongside | Manifest validates as `kind: service` |
| 5 | **CFactory (fleet aggregate)** | Needs all four upstreams live to be meaningful | Aggregate validates as `kind: fleet`, lists four services, and degrades to `reachable: false` when an origin is stopped |

Each service SHOULD validate its own manifest against this schema in its own CI,
so drift fails at the source rather than at the aggregator.

## 7. Non-goals

- Not a service registry or health surface - the manifest says what a service
  *can* do, never what it is *doing*. Work-item state stays on the CFactory
  cockpit APIs.
- Not an auth or entitlement description beyond naming the schemes. What a
  particular caller may invoke is decided at invocation time.
- Not a skill package format. `SKILL.md` frontmatter stays authoritative for the
  package; the manifest only points at it.

## 8. Related

- [RFC-0019](../docs/rfc/0019-agent-native-planning-control-plane.md) - the
  agent-native planning control plane (this is section 3.4, phase 4).
- [`pfactory.mcp.md`](./pfactory.mcp.md) ·
  [`aifactory.mcp.md`](./aifactory.mcp.md) ·
  [`tfactory.mcp.md`](./tfactory.mcp.md) ·
  [`cfactory.mcp.md`](./cfactory.mcp.md) - the MCP tool surfaces the manifests
  point at.
- [`*.openapi.yaml`](.) - the REST surfaces `openapi_url` points at.
- [RFC-0001](../docs/rfc/0001-correlation-key-and-completion-event.md) - the
  correlation key several skills take or return.
