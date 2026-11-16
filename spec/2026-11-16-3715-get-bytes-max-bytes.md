---
status: approved
issue: 3715
intent: intent/2026-11-16-3715-get-bytes-max-bytes.md
---

# Spec: get_bytes(max_bytes=)

## Design

`get_bytes(key, max_bytes=None)`. When set: read at most `max_bytes + 1` bytes
(an oversize object is never loaded whole); more than `max_bytes` raises
`ValueError`; exactly `max_bytes` is allowed. A negative cap raises `ValueError` before the fetch
(`read(-1)` would read everything). A capped read skips botocore's
length check, so a short read against `ContentLength` raises `OSError` (moved
from `_read_capped`). The hub self-test fake gains `ContentLength` and a
cap test (under, at, over).

AIFactory calls `store.get_bytes(key, max_bytes=_SPEC_FILE_MAX_BYTES)`, logs the
`ValueError` as the existing "too large" warning, and deletes `_read_capped`
and its test.

## Alternatives rejected

- Truncate silently: hides oversize input.
- Custom exception class: more API for no caller need.

## Risks

Downstream pins must point at the hub squash-merge SHA, which exists only after
the Factory PR merges; the three service PRs go green after that re-point.

## Verification

`python3 scripts/artifact_store.py`, ruff, the drift gates in each service,
AIFactory spec-job tests.
