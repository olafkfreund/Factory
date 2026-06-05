# Dependencies

Factory is a documentation / program repo, so it has **no runtime dependencies** of
its own. Its "dependencies" are the four product repositories it coordinates and the
shared contracts that let them cooperate.

## The four products (Factory family)

Each is a standalone repo with its own Backstage catalog entity; Factory is the
`Domain` (`factory-suite`) that groups them.

| Product | Stage | Repo | Relationship |
|---|---|---|---|
| **PFactory** | Prepare / Plan | [olafkfreund/PFactory](https://github.com/olafkfreund/PFactory) | Emits governed GitHub issues → AIFactory |
| **AIFactory** | Act | [olafkfreund/AIFactory](https://github.com/olafkfreund/AIFactory) | Consumes PFactory issues; hands branches → TFactory; receives handback |
| **TFactory** | Reflect / Verify | [olafkfreund/TFactory](https://github.com/olafkfreund/TFactory) | Verifies AIFactory branches; routes failures back (handback) |
| **CFactory** | Review / Observe | [olafkfreund/CFactory](https://github.com/olafkfreund/CFactory) | Observes & steers all three from one cockpit |

```
PFactory ──issues──▶ AIFactory ──branch/PR──▶ TFactory
    ▲                    │  ▲                     │
    │                    │  └──── handback ───────┘
    └─ correlation key (GitHub issue #) ──────────┘
                 every step observed by CFactory
```

## Shared contracts (what the products depend on)

The products do **not** depend on each other's code — they depend on small, versioned
contracts owned by this repo:

| Contract | What it fixes | Where |
|---|---|---|
| **Correlation key** | The GitHub issue number, threaded end to end (with synthetic fallback) | [RFC-0001](api.md) |
| **Completion-event envelope** | One normalized terminal-status event every service emits | [RFC-0001](api.md) |
| **Canonical port map** | Fixed, non-overlapping local ports (3101 / 3103 / 3110-3111 / 3114-3115) | `docs/dev/local-ports-and-run-all.md` |

These contracts are deliberately small and additive-friendly: new fields are optional,
unknown fields are ignored, and a new product takes the next free port — none of which
forces a breaking change.

## Program tooling

- **Jekyll / GitHub Pages** — the public site at
  [factory.freundcloud.com](https://factory.freundcloud.com/) (`docs/`).
- **Backstage TechDocs** — this site (`techdocs/`, built with `mkdocs` +
  `mkdocs-techdocs-core`; see `techdocs/requirements.txt`).
- **GitHub Projects** — the [Factory Program board](https://github.com/users/olafkfreund/projects/1)
  threads cross-cutting epics and product sub-issues across all five repos.

## Cross-service dependency graph (catalog)

In the Backstage catalog, the cross-product relationships live on each product's own
entity (e.g. AIFactory `dependsOn` PFactory; CFactory consumes all three). This repo's
`factory` Component declares only the `factory-suite` Domain it belongs to — it owns
the contracts, not the dependency edges.
