# Decisions

The program-level decisions that shaped the Factory suite. This repo has no
`.agent-os/product/decisions.md`; these are distilled from the canonical program
artifacts — [RFC-0001](api.md) (correlation key & completion event), the
[roadmap](https://factory.freundcloud.com/roadmap/), the canonical port-map guide, and
the program [README](https://github.com/olafkfreund/Factory). For per-product
decisions, see each product's own catalog entity and decision log.

## A chain of focused products, not a monolith

> **Accepted** · Product / Strategy

The SDLC is split into **four composable products** (PFactory · AIFactory · TFactory ·
CFactory) chained through PARR, rather than one monolith. Rationale: **adoption**
(take TFactory for QA, or PFactory for governed planning, without buying the whole
stack), **focus** (each product competes on its own merits), and **trust** (the
boundaries between products are exactly where human-in-the-loop gates belong).

## Compete on the governance / verification / observability layer — not code generation

> **Accepted** · Product / Strategy

Factory deliberately does **not** compete with code-generation tools (Copilot, Cursor,
Claude Code, Codex, Devin). It sits in the layer *around* them: **govern → build →
verify → observe.** The bet is that code generation keeps commoditizing while value
migrates to *trusting, governing and verifying* what was generated — sharpened by the
EU AI Act's high-risk obligations (logging, human oversight, audit) from Aug 2, 2026.

## The correlation key is the GitHub issue number

> **Accepted** · Technical · [RFC-0001](api.md)

The unit of work is threaded end to end by the **GitHub issue number** — the durable,
human-visible artifact every stage already references. Before an issue exists, services
emit a stable **synthetic key** (`pf-…` / `af-…` / `tf-…`) and reconcile to the real
number once assigned. Choosing an existing, human-visible identifier (over a new UUID)
keeps the thread legible and auditable.

## A normalized, best-effort completion-event envelope

> **Accepted** · Technical · [RFC-0001](api.md)

Every service emits **one** event on terminal status with six stable fields
(`correlation_key`, `service`, `task_id`, `status`, `phase`, `updated_at`), plus
optional additive `usage` and `correlation` blocks. Delivery is **best-effort** — a
failing delivery must never break the emitting pipeline — over a standardized webhook
or a same-host `COMPLETED.json` sentinel. Consumers treat events as idempotent by
`(service, correlation_key, status)` and must ignore unknown fields. The shape is
normalized; each service keeps its own status/phase vocabulary.

## Additive-only contract evolution

> **Accepted** · Process · [RFC-0001 §7](api.md)

The six envelope fields are stable; new fields are additive and optional, and consumers
must ignore unknown fields. Removing/renaming a field or changing a type is breaking and
requires a new RFC version (and a `schema_version` field at that time). A new product
takes the next free port and updates the map by PR. This keeps the suite extensible
without coordinated breaking changes.

## A canonical, non-overlapping local port map

> **Accepted** · Process

To run the whole factory side by side (and let CFactory reach every product), each
product gets a fixed backend port: AIFactory `3101`, TFactory `3103`, CFactory
`3110`/`3111`, PFactory `3114`/`3115`. This resolved the historical `:3102` collision
(PFactory and TFactory both claimed it); PFactory vacated to `3114/3115`, TFactory had
already moved to `3103`, and `3102` is now free.

## Spine first

> **Accepted** · Process · [roadmap](https://factory.freundcloud.com/roadmap/)

The sequencing principle is **spine first**: make the pipeline traceable end-to-end
(correlation key + completion events + port map) **before** building deep features on
top of it — then ship the CFactory cockpit in phases.

## Model-agnostic by design

> **Accepted** · Technical

The intelligence is in the *workflow*, not a single model. Products use the Claude
Agent SDK at the core with a multi-provider factory routing by model string (Claude,
OpenAI, Gemini, Ollama, vLLM, Codex, Copilot CLI), MCP interop, executor delegation,
and BYO / air-gapped models — so a new model or agent is a small adapter, not a rewrite.
