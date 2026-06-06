---
layout: default
title: "RFC-0002: Factory Task Contract v2"
permalink: /rfc/task-contract/
---

# RFC-0002 — Factory Task Contract v2

> **Status:** Proposed · **Version:** 2.0 · **Created:** 2026-06-06
> Builds on [RFC-0001](./0001-correlation-key-and-completion-event.md) (correlation
> key + completion-event envelope). The product repos implement against this
> document. Machine-readable schema: [`apis/task-contract.schema.json`](../../apis/task-contract.schema.json).

## 1. Motivation

RFC-0001 lets the four products *track* one unit of work across the family. It
does not let them *hand the work off in full*. Today the handoff is thin:

- **PFactory** emits "what to do" — a `requirements.json` (complexity, optional
  model/thinking) plus governed GitHub issues. It does **not** emit "how to
  execute": no parallel/worker plan, no per-subtask verification, no
  `required_commands`, no provider rationale, no review tier, and nothing for
  TFactory.
- **AIFactory** therefore re-runs its **full planner** on every task, even though
  PFactory already did the analysis. AIFactory has a signed fast-path
  (`trusted_plan` → `POST /api/tasks/from-plan`) that skips planning when given a
  complete signed `implementation_plan.json`, but nothing upstream produces one.
- **TFactory** ingests an AC-only spec and **guesses** framework / lane /
  endpoints. The spec carries no declared test configuration.

The result is duplicated analysis and lossy handoffs. **Task Contract v2** is one
canonical, signed document that carries **WHAT** (the plan), **HOW** (the
execution profile), and **VERIFY** (the test profile) so that:

1. **PFactory computes the full profile once** and signs it.
2. **AIFactory executes it without re-planning** (`skip_planning: true`).
3. **TFactory tests it without guessing** (declared lanes/frameworks/endpoints).
4. All three **stay in sync** via the RFC-0001 completion-event envelope.

The contract is **additive and backward-compatible**: `contract_version: "1"`
plans and the `requirements.json` path keep working. v2 is the enriched
fast-path.

## 2. Document shape

A Task Contract is a superset of AIFactory's `implementation_plan.json` with two
new blocks (`execution`, `tfactory`) and an RFC-0001-aligned envelope. The
authoritative, validatable definition is the JSON Schema; this section is the
human summary.

```jsonc
{
  // -- identity / correlation (RFC-0001) --
  "contract_version": "2",
  "correlation_key": "142",                 // GitHub issue number (string)
  "provenance": {
    "source": "pfactory",
    "session_id": "017-add-rate-limiting",
    "issue_number": 142,
    "repo": "olafkfreund/my-app"
  },
  "approval": {                              // HMAC envelope (AIFactory trusted_plan)
    "approved_by": "pfactory",
    "approval_timestamp": "2026-06-06T12:00:00Z",
    "plan_contract_version": "2",
    "signature": "<hex HMAC-SHA256>"
  },

  // -- WHAT: the plan (existing implementation_plan.json shape, unchanged) --
  "feature": "Add rate limiting to the gateway",
  "workflow_type": "feature",
  "services_involved": ["gateway"],
  "phases": [
    {
      "phase": 1, "name": "Modules", "type": "implementation",
      "depends_on": [], "parallel_safe": true,
      "subtasks": [
        {
          "id": "subtask-1-1",
          "description": "Implement RateLimitMiddleware",
          "depends_on": [],
          "files_to_create": ["app/middleware/ratelimit.py"],
          "files_to_modify": [],
          "model": "claude-sonnet-4-6",
          "verification": { "type": "command", "run": "uv run pytest tests/test_ratelimit.py" },
          "required_commands": ["uv", "pytest"]
        }
      ]
    }
  ],
  "final_acceptance": ["Requests over the limit return HTTP 429"],
  "required_commands": ["uv", "pytest", "ruff", "mypy"],

  // -- HOW: execution profile (NEW, PFactory-computed) --
  "execution": {
    "complexity": "standard",
    "model": "claude-sonnet-4-6",
    "provider": "claude",
    "provider_rationale": "FastAPI/Python stack; Claude SDK is the default agentic provider",
    "phase_models":   { "spec": "sonnet", "planning": "sonnet", "coding": "sonnet", "qa": "sonnet", "qa_fixer": "sonnet" },
    "phase_thinking": { "planning": "high", "coding": "medium", "qa": "high" },
    "parallel": true,
    "workers": 4,
    "review_tier": "async",
    "agents": {
      "planner": false,            // skip — plan is pre-computed
      "coder": true, "qa_reviewer": true, "qa_fixer": true,
      "subagents": ["codebase_analyzer"]
    },
    "skills": [{ "id": "python/fastapi", "name": "FastAPI", "category": "python" }],
    "skip_planning": true
  },

  // -- VERIFY: TFactory test profile (NEW, PFactory-computed) --
  "tfactory": {
    "lanes": ["unit", "api", "security"],
    "frameworks": { "unit": "pytest", "api": "pytest+httpx" },
    "endpoints": { "api_base_url": "http://localhost:8000" },
    "docker_compose": null,
    "coverage_target": 0.85,
    "mutation_scope": ["app/middleware/ratelimit.py"],
    "security_scope": ["owasp:rate-limiting", "owasp:dos"],
    "ac_to_code_map": { "AC#1": ["app/middleware/ratelimit.py"] }
  }
}
```

### 2.1 Blocks

| Block | Owner (produces) | Consumer | Required |
|---|---|---|---|
| `contract_version`, `correlation_key`, `provenance` | PFactory | all | yes |
| `approval` | PFactory (signs) | AIFactory (verifies) | yes for the skip-planning fast-path |
| plan (`feature`…`phases`…`required_commands`) | PFactory | AIFactory | yes |
| `execution` | PFactory | AIFactory | optional (AIFactory falls back to its defaults / own planning if absent) |
| `tfactory` | PFactory | TFactory (via AIFactory handover) | optional (TFactory falls back to inference) |

A v2 contract **without** `execution`/`tfactory` is a valid signed plan that
behaves like v1 plus richer correlation. A v2 contract **with** them is the full
skip-planning, no-guessing fast-path.

## 3. Signing & trust

Signing reuses AIFactory's `trusted_plan` envelope (HMAC-SHA256 over the
canonical contract + approval metadata, keyed by
`AIFACTORY_TRUSTED_PLAN_KEY_<AUTHORITY>`). The signature covers the WHAT, HOW, and
VERIFY blocks — so the execution profile and test profile are tamper-evident, not
just the plan. AIFactory verifies signature **and** completeness before honoring
`skip_planning`; on failure it rejects (HTTP 422) and may fall back to normal
planning.

## 4. Sync model (bidirectional)

- **Forward (handoff):** PFactory → AIFactory via `POST /api/tasks/from-plan`
  (the contract as body). AIFactory → TFactory by carrying the `tfactory` block
  into the spec/context it hands over.
- **Backward (status):** every stage emits the RFC-0001 completion-event envelope
  keyed by `correlation_key`. CFactory threads them. TFactory failures flow back
  to AIFactory's QA-fixer via the existing handback path; AIFactory failures are
  visible to PFactory by the same key. "100% mutual understanding" = both sides
  validate against this one schema and reconcile on the one key.

## 5. Versioning

`contract_version` is bumped when the envelope or block shapes change in a
breaking way. New optional fields are additive (no bump). Consumers MUST ignore
unknown fields. The schema file is versioned alongside this RFC.

## 6. Adoption (tracked by issues)

- **Factory:** this RFC + `apis/task-contract.schema.json` + catalog/TechDocs.
- **PFactory:** compute + sign + emit the full v2 contract.
- **AIFactory:** extend `trusted_plan` to verify/ingest `execution` + `tfactory`;
  apply the execution profile and skip planning; carry `tfactory` to TFactory.
- **TFactory:** consume the `tfactory` block to build `test_plan.json`
  deterministically.

See the cross-linked epics in each repo's issue tracker.
