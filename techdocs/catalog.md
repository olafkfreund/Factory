# Catalog & entities

This page documents the Backstage entities defined by this repo's
[`catalog-info.yaml`](https://github.com/olafkfreund/Factory/blob/main/catalog-info.yaml)
and how the suite is wired together. Registering the one `catalog-info.yaml` URL
imports everything below in a single step.

## Entity model

```
System  factory-suite                          (owner: olafkfreund)
  ├── Component  factory      (documentation; this program/meta repo)
  │     └── has subcomponents ▼
  ├── Component  pfactory   ─ subcomponentOf factory ─ provides ▶ pfactory-api,  pfactory-mcp
  ├── Component  aifactory  ─ subcomponentOf factory ─ dependsOn pfactory          ─ provides ▶ aifactory-api, aifactory-mcp
  ├── Component  tfactory   ─ subcomponentOf factory ─ dependsOn aifactory         ─ provides ▶ tfactory-api,  tfactory-mcp
  └── Component  cfactory   ─ subcomponentOf factory ─ dependsOn p/ai/t factory    ─ provides ▶ cfactory-api,  cfactory-mcp,
                                                                                                 factory-completion-events
```

The `factory` Component is **documentation-only** — it provides/consumes no APIs
of its own (those belong to the four product services). It gains a **System** and
a **Has subcomponents** list from the wiring above.

> A `Domain` would be the natural grouper, but the catalog rules in this Backstage
> instance reject `Domain` entities (see PR #14), so the family is grouped by the
> `factory-suite` **System** instead.

## APIs

Nine API entities, with machine-readable definitions embedded from
[`apis/`](https://github.com/olafkfreund/Factory/tree/main/apis) via `$text`:

| API entity | Kind | Provided by | Notes |
|---|---|---|---|
| `pfactory-api` | openapi | pfactory | REST + WS, `:3114` |
| `aifactory-api` | openapi | aifactory | REST + WS, `:3101` |
| `tfactory-api` | openapi | tfactory | REST + WS, `:3103` |
| `cfactory-api` | openapi | cfactory | Cockpit + ingress, `:3110`/`:3111` |
| `factory-completion-events` | asyncapi | cfactory (channel) | RFC-0001 envelope; consumed by p/ai/t |
| `pfactory-mcp` … `cfactory-mcp` | mcp | each product | MCP control planes (markdown tool catalogs) |

The completion-event contract is **provided by** CFactory (it owns the
`/api/events/completion` ingress channel) and **consumed by** PFactory, AIFactory
and TFactory (they publish to it). See [API & Contracts](api.md) and
[RFC-0001](api.md) for the schema.

## Files

| File | Purpose |
|---|---|
| `catalog-info.yaml` | All entities (Component · System · 4 product Components · 9 APIs), inline |
| `apis/*.openapi.yaml` | Per-product REST/WS OpenAPI 3.0 specs |
| `apis/completion-events.asyncapi.yaml` | RFC-0001 completion-event AsyncAPI 2.6 |
| `apis/*.mcp.md` | Per-product MCP control-plane tool catalogs |
| `scripts/validate-catalog.py` | Offline validator (`catalog-validate` in the Nix devShell) |
| `mkdocs.yml` + `techdocs/` | This TechDocs site |

## Import into Backstage

**UI:** *Create → Register existing component →*
`https://github.com/olafkfreund/Factory/blob/main/catalog-info.yaml`

**Static config** (`app-config.yaml`):

```yaml
catalog:
  locations:
    - type: url
      target: https://github.com/olafkfreund/Factory/blob/main/catalog-info.yaml
      rules:
        - allow: [Component, API, System]
```

> The four product Components are catalogued here while their repos are onboarded.
> When a product repo gains its own `catalog-info.yaml`, move its Component there
> and drop it from this file to avoid duplicate entities (the API entities can stay
> centralised here, since the cross-product contract lives in this program repo).

## Validation

```bash
nix develop -c catalog-validate   # runs scripts/validate-catalog.py
```

Checks that every entity has the required envelope, `providesApis`/`consumesApis`
resolve to defined APIs, each API's `$text` target exists and parses for its type
(OpenAPI 3.x / AsyncAPI 2–3 / MCP markdown), and the mkdocs nav targets all exist.
