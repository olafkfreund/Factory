# TFactory

**Reflect / Verify** — the verification stage of the Factory
[PARR pipeline](https://factory.freundcloud.com/).

TFactory autonomously generates and runs a test suite against a finished feature,
then grades it on a **5-signal verdict** so a pass means *meaningful* tests, not a
green bar. It posts a triage report to the PR and, on failure, routes a
**handback** to AIFactory's QA fixer.

| | |
|---|---|
| **Stage** | Reflect / Verify (PARR) |
| **Backend port** | `:3103` |
| **Surfaces** | REST + WebSocket API, MCP control plane |
| **Lanes** | unit · browser · API · integration · mutation |
| **Verdict** | coverage delta · stability · mutation · lint · semantic relevance |
| **Emits** | RFC-0001 completion events (`triaged` / `triaged_empty` / `triager_failed`) |

## In the suite

TFactory verifies AIFactory's branches and closes the loop with a handback when
tests fail.

```
AIFactory ──branch/PR──▶ TFactory ──triage report──▶ PR
              ▲             │
              └── handback ─┘   observed by CFactory (Review)
```

See [Architecture](architecture.md) and [API & Contracts](api.md).
