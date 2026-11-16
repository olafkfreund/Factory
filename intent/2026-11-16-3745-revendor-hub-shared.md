---
status: draft
issue: 3745
author: olafkfreund
---

# Intent: re-vendor hub shared packages into the product repos

## Problem

Hub `factory_common` (Anthropic sk-ant- redaction, Factory#3745) and `agent_sandbox` (inherited-git-redirection warning, Factory#3760) moved. AIFactory, PFactory, TFactory and CFactory still vendor older copies; the pin-freshness gate (Factory#3762) flags them.

## Proposed outcome

Each product repo vendors the current hub canonical byte-for-byte, with its `.hub-sha` at hub main `b3844b8b224d1ec198afd7a77221eb67b45fe217`, and its drift gates and tests pass.

## Affected users and systems

AIFactory (backend + web-server factory_common, backend agent_sandbox), PFactory and TFactory (web-server factory_common, backend agent_sandbox), CFactory (backend factory_common). Base branch dev.

## Constraints

Vendored files are never hand-edited. Pins must be a squash-merge commit on hub main. No live-cluster changes.

## Open questions

None. Mechanical change; one artifact set here covers all four PRs.
