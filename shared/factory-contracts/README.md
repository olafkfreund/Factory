# factory-contracts

Single source of truth for the cross-factory **completion-event envelope**
(RFC-0001), its optional v1.1 **token-usage** block, the usage **rollup helpers**,
and the lifecycle **status taxonomy** (terminal / failed / running / review /
queued).

These two contracts were previously hand-rolled per service and disagreed at
runtime: CFactory, AIFactory, PFactory and TFactory each re-derived
`CompletionEvent` / `Usage`, and the status classifier was reimplemented five
divergent times in CFactory alone (one copy's substring match made `"ready"`
match `"already"`). This package is generated **once, in the hub**, from the
canonical inputs and **committed** so consumers can pin a known version.

Part of epic [Factory#154](https://github.com/olafkfreund/Factory/issues/154);
issue [Factory#160](https://github.com/olafkfreund/Factory/issues/160).

## Layout

```
shared/factory-contracts/
  python/factory_contracts/__init__.py   # pydantic v2 models + helpers (generated)
  ts/factory-contracts.ts                # TS types + classifiers (generated)
  README.md                              # this file
```

Both files carry a `GENERATED ... DO NOT EDIT BY HAND` banner. They are produced
by `scripts/gen_contracts.py` from:

- `apis/completion-events.asyncapi.yaml` — the RFC-0001 `CompletionEvent` + `Usage`
- `apis/status-taxonomy.json` — the canonical lifecycle token sets

The token sets mirror CFactory's canonical
`apps/backend/cfactory/status_taxonomy.py` (matching is exact-token, never loose
substring containment).

## Regenerating

```
python scripts/gen_contracts.py          # rewrite the generated output
python scripts/gen_contracts.py --check  # CI: fail if committed output is stale
```

Generation is intentionally **dependency-free** (no `datamodel-code-generator` /
`json-schema-to-typescript` in the hub devShell): the contracts are small and
stable, so a self-contained emitter is preferable. If those tools are later
adopted fleet-wide, `scripts/gen_contracts.py` is the single place to swap the
emitter — the generated public API is the contract, not the generator. A pytest
self-test (`tests/test_gen_contracts.py`) asserts the committed output is not
stale, the Python module imports, and the classifiers keep token-boundary
semantics.

## Consuming (pinned)

Consumers should **pin** a specific commit of this directory rather than vendoring
their own copy. The generated artifacts are stable, additive, and tolerant of
unknown fields (`extra="allow"` in Python, index signatures in TS), so a newer
emitter never drops a field an older consumer reads.

### Python

The package is a plain importable module (no build step required). Add the
directory to the path (or vendor it via a pinned git ref / submodule) and import:

```python
from factory_contracts import (
    CompletionEvent,
    Usage,
    rollup_usage,
    is_terminal,
    is_failed,
    is_running,
)

event = CompletionEvent(
    correlation_key="142",
    service="aifactory",
    task_id="proj:001",
    status="done",
    phase="act",
    updated_at="2026-06-05T12:00:00+00:00",
    usage=Usage(input_tokens=2400, output_tokens=100, total_tokens=2500, cost_usd=1.25),
)

# Roll per-worker / per-stage usage up to a task total.
task_total = rollup_usage([w.usage for w in workers])

# Classify any per-service status string against the canonical taxonomy.
if is_terminal(event.status) and is_failed(event.status):
    ...
```

Requires `pydantic>=2`.

### TypeScript

Import the types and classifiers directly:

```ts
import {
  CompletionEvent,
  Usage,
  isTerminal,
  isFailed,
  isRunning,
} from "factory-contracts";

function classify(status: string): boolean {
  return isTerminal(status);
}
```

## Migration off hand-rolled models (tracked follow-on)

This PR is **hub-only**: it adds the canonical inputs, the generator, the
committed output and the self-test. It does **not** rewrite any service to consume
this package — replacing each service's hand-rolled `CompletionEvent` / `Usage` /
status classifier is **risky** and is intentionally deferred to **separate,
per-repo migration issues** so each can be reviewed and tested in isolation:

- CFactory — `models.py` `CompletionEvent` / `TokenUsage` / `WorkerUsage`;
  fold its `status_taxonomy.py` consumers onto the generated classifiers.
- AIFactory — `services/completion.py`.
- PFactory — `emit/contract_sync.py`.
- TFactory — `triager._build_completion_envelope` (currently a raw dict).

Until those land, drift is still caught only at runtime via tolerant
key-fallback parsing; pinning this package is the first step that lets each
service converge.
