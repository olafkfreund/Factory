# AIFactory

**Act** — the build core of the Factory
[PARR pipeline](https://factory.freundcloud.com/).

AIFactory takes a governed GitHub issue and runs a **spec-first plan → code → QA**
pipeline in an isolated git worktree, routed through a multi-provider model
factory. It is the provider-agnostic execution engine the rest of the suite wraps.

| | |
|---|---|
| **Stage** | Act (PARR) |
| **Backend port** | `:3101` |
| **Surfaces** | REST + WebSocket API, MCP (stdio **and** remote HTTP+SSE) |
| **Providers** | Claude, OpenAI, Gemini, Ollama, vLLM, Codex, Copilot CLI |
| **Enterprise** | SAML/SCIM, tenant isolation, HMAC-anchored audit, LiteLLM gateway |
| **Emits** | RFC-0001 completion events **with the v1.1 `usage` block** |

## In the suite

AIFactory consumes the governed issues PFactory emits and hands a finished branch
to TFactory; when tests fail, TFactory routes a **handback** to AIFactory's QA
fixer — a bounded, closed loop.

```
PFactory ──issues──▶ AIFactory ──branch/PR──▶ TFactory
                       (Act)  ◀──── handback ────┘
              observed by CFactory (Review)
```

See [Architecture](architecture.md) and [API & Contracts](api.md).
