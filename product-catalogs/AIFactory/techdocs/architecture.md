# Architecture

AIFactory is an agent build pipeline that turns a governed issue into a
merge-ready branch, isolated per task.

## Pipeline

```
governed issue ─▶ planner ─▶ coder ─▶ QA ─▶ merge-ready branch / PR
                            (isolated   (tests,
                             worktree)   lint,
                                         self-review)
                       routed through the multi-provider model factory
```

| Stage | What it does |
|---|---|
| **Planner** | Turn the issue + spec into an executable build plan. |
| **Coder** | Implement in an **isolated git worktree** (one per task), so parallel builds never collide. |
| **QA** | Run tests/lint/self-review; on a TFactory handback, reopen the worktree and apply corrections. |
| **Delegate** | Optionally hand execution to another coding agent/executor. |

## Multi-provider factory

Models are routed by string through a provider factory (Claude Agent SDK at the
core; OpenAI, Gemini, Ollama, vLLM, Codex, Copilot CLI as adapters), with MCP
interop and BYO/air-gapped support — a new model is a small adapter, not a rewrite.

## Enterprise & audit

SAML/SCIM auth, tenant isolation, a LiteLLM gateway, and **HMAC-anchored audit
logs**. Per-task token/cost is tracked in `token_usage.json` and emitted in the
RFC-0001 `usage` block.

## Outputs & handoff

A finished feature on a branch is handed to **TFactory**. On a terminal status
AIFactory emits an RFC-0001 completion event (e.g. `merged` → `act`,
`qa_failed` → `qa`) carrying the `usage` block. See [API & Contracts](api.md).
