---
status: approved
issue: 3715
author: olafkfreund
---

# Intent: optional size cap on artifact_store get_bytes

## Problem

AIFactory must cap how much of a spec-Job object it reads from MinIO (8 MiB).
The vendored `artifact_store.py` is byte-checked against the hub, so AIFactory
could not add the cap there and carries a local helper, `workspace_fetch._read_capped`,
which reaches into the store's private `_client()`.

## Proposed outcome

The hub `get_bytes` takes an optional `max_bytes` and raises on overflow. The
three services re-vendor it. AIFactory drops `_read_capped`.

## Affected users and systems

Factory `scripts/artifact_store.py`; the vendored copies in AIFactory, PFactory,
TFactory; their drift gates (`HUB_PIN_SHA`).

## Constraints

Default behaviour unchanged. Vendored copies stay byte-identical to the hub.

## Open questions

None.
