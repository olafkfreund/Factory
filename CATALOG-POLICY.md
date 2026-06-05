# Backstage Catalog Policy

> Single source of truth for the Factory family's Backstage Software Catalog.

## TL;DR

**`Factory/catalog-info.yaml` is the only place that defines the family's catalog
entities.** Product repos contribute **TechDocs only**. Register **one** catalog in
Backstage — this file — and the rest follows.

## What lives where

| Concern | Owner | Notes |
|---|---|---|
| Catalog **entities** (Components, System, APIs) | **`Factory/catalog-info.yaml`** | The `factory` Component + `factory-suite` System, the four product Components (`pfactory`, `aifactory`, `tfactory`, `cfactory`, each `subcomponentOf: factory`), and all 9 API entities. |
| API **specs** | `Factory/apis/*.{openapi.yaml,mcp.md,asyncapi.yaml}` | Embedded into the API entities via `definition.$text`. |
| Per-product **TechDocs** | Each product repo (`mkdocs.yml` + `techdocs/`, or Docusaurus `docs/`) | Pulled in cross-repo by the Factory catalog's `backstage.io/techdocs-ref: url:…/<repo>/tree/<branch>` annotations. |

## Rules

1. **Define product entities once — centrally.** Do **not** emit competing
   Component/API/System definitions into the product repos' own `catalog-info.yaml`.
   Duplicate `kind:name` entities across registered Locations cause Backstage to reject
   the duplicates and log conflicts.
2. **Product repos self-describe TechDocs only.** A product repo needs a buildable
   root `mkdocs.yml` (+ `techdocs/`) or Docusaurus `docs/`. It does **not** need to
   register itself in the catalog — the Factory catalog references its docs by URL.
3. **Register one catalog.** In Backstage `app-config.yaml`, register only
   `Factory/catalog-info.yaml`, **or** filter GitHub discovery to `repository: '^Factory$'`.
   See the snippet below.
4. **Keep the model stable.** `Factory/catalog-info.yaml` is the *centralized* model
   (meta + System + product Components + APIs). Do not oscillate it between centralized
   and a slim `meta + dependsOn` form — pick centralized and keep it.

## Backstage registration

Static location (simplest):

```yaml
catalog:
  locations:
    - type: url
      target: https://github.com/olafkfreund/Factory/blob/main/catalog-info.yaml
      rules:
        - allow: [Component, System, API]
```

Or, if using GitHub auto-discovery, scope it to the Factory repo only:

```yaml
catalog:
  providers:
    github:
      factoryMeta:
        organization: olafkfreund
        catalogPath: /catalog-info.yaml
        filters:
          repository: '^Factory$'   # excludes PFactory/AIFactory/TFactory/CFactory
        schedule:
          frequency: { minutes: 30 }
          timeout: { minutes: 3 }
```

> Without the filter, discovery also ingests each product repo's `catalog-info.yaml`
> and the same entities get defined twice → conflicts. Filtering (or a single static
> Location) is the durable fix.

## For the catalog-onboard automation

- Maintain only `Factory/catalog-info.yaml` (+ `Factory/apis/*`).
- For product repos, ensure TechDocs exist (`mkdocs.yml` + `techdocs/`), but do **not**
  generate product entity definitions into their `catalog-info.yaml`.
- Default branches used for cross-repo TechDocs: PFactory `main`, AIFactory `dev`,
  TFactory `dev`, CFactory `main`. Keep the `techdocs-ref` URLs in sync if these change.
