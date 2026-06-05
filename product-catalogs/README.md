# Per-product Backstage catalog files

Ready-to-drop `catalog-info.yaml` (and embedded API specs) for the four product
repos, so each repo eventually **owns its own** Backstage Component + API entities
instead of being catalogued centrally in this Factory program repo.

These files are **staged here only** — they are not imported by the Factory repo's
catalog (its root `catalog-info.yaml` has no `Location` pointing at this folder).

## What's here

```
product-catalogs/
├── PFactory/   catalog-info.yaml + apis/openapi.yaml + apis/mcp.md
├── AIFactory/  catalog-info.yaml + apis/openapi.yaml + apis/mcp.md
├── TFactory/   catalog-info.yaml + apis/openapi.yaml + apis/mcp.md
└── CFactory/   catalog-info.yaml + apis/openapi.yaml + apis/mcp.md
```

Each `catalog-info.yaml` defines that product's `Component` plus its `*-api`
(OpenAPI) and `*-mcp` (MCP) API entities. The `$text` definitions point at the
sibling `apis/` files, so copy the **whole product folder's contents** to the
target repo root.

## How to adopt (per product)

1. Copy the folder's contents to the **root** of the matching repo, e.g. for
   PFactory:
   ```bash
   cp product-catalogs/PFactory/catalog-info.yaml   <PFactory>/catalog-info.yaml
   cp -r product-catalogs/PFactory/apis             <PFactory>/apis
   ```
   (If a repo already has an `apis/` or `catalog-info.yaml`, merge rather than
   overwrite.)
2. Commit & push in the product repo, then register its `catalog-info.yaml` URL in
   Backstage (or let GitHub discovery pick it up).
3. **Remove the now-duplicated block from this Factory repo's `catalog-info.yaml`:**
   delete that product's `Component` (and optionally its `*-api` / `*-mcp` `API`
   entities). Two entities with the same name in the catalog is an error.
   - **Keep `factory`, `factory-suite` and `factory-completion-events` in this
     Factory repo** — they are the shared/parent entities the products reference.

## Cross-repo references (resolved globally by Backstage)

Each product file references entities owned elsewhere. Backstage resolves these by
name across all registered locations, so they "just work" once every repo is
registered:

| Reference | Defined in |
|---|---|
| `system:factory-suite` | Factory repo |
| `component:factory` (parent of `subcomponentOf`) | Factory repo |
| `api:factory-completion-events` | Factory repo (CFactory only *provides* it) |
| sibling `component:*` / `api:*-api` (dependsOn / consumesApis) | the sibling product repo |

> **Offline validator note.** If a product repo uses the strict, single-file
> `scripts/validate-catalog.py` (the one that requires every `providesApis` /
> `consumesApis` target to be defined *in the same file*), it will flag the
> cross-repo references above. They are valid in Backstage. Either (a) treat those
> names as known-external in that repo's validator, or (b) drop the cross-repo
> `consumesApis` / `dependsOn` lines locally and let the relationships live on the
> providing side. The Factory repo's validator already accepts `openapi`,
> `asyncapi` and `mcp` `$text` types.

## Ports (canonical)

`AIFactory :3101` · `TFactory :3103` · `CFactory :3110`/`:3111` ·
`PFactory :3114`/`:3115`.
