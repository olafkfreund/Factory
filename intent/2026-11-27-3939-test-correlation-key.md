---
status: approved
issue: 3939
author: olafkfreund
---

# Intent: `factory test` files its verify under the run's correlation key

## Problem

E2E run `mvr-20261127u` passed S1 to S5 but failed X: CFactory showed one run as three work items.
Part of that is the verify step. `factory test` ingests the merge-SHA verify into TFactory with no
correlation key, so TFactory files the verdict under a synthetic `tf-<project>:<spec>` key. The
AIFactory half is AIFactory#2266. TFactory#1713 adds the ingest field that `factory test` can now
use.

## Proposed outcome

- `factory test` and its MCP twin `factory_test` accept an optional correlation key and send it on
  the TFactory ingest.
- The E2E harness passes the key that `factory submit` returned, so the verify joins the run's
  work item.

## Affected users and systems

- Factory CLI: `shared/factory-cli/factory_cli/{testrun,__main__,mcp_server}.py` and tests.
- E2E harness: `scripts/e2e/stages.py` and `tests/e2e/unit`.

## Constraints

- **Optional:** without the option, the request body is unchanged.
- **Validated client-side:** the same rule TFactory applies. At most 128 characters, a safe
  character set, and never a bare number. A bad value is refused before any network call.
- **Old TFactory still works:** a TFactory without #1713 ignores the field, because extra fields
  are ignored.

## Open questions

None.
