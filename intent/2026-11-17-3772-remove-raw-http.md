---
status: approved
issue: 3772
author: olafkfreund
---

# Intent: RFC-0022 Phase 2c: remove api_get/api_post from the provider protocols

## Problem

`GitProvider` still carries `api_get` and `api_post`, raw HTTP escape hatches that RFC-0022 section 2.2 says do not survive the split. A raw HTTP method on a provider-agnostic interface is a hole through the abstraction, and a Jira or Bitbucket provider cannot honestly implement it.

## Proposed outcome

`GitProvider` is exactly `WorkItemProvider` plus `CodeProvider`. `api_get`/`api_post` stay on the concrete clients and provider classes (RFC section 2.2) but not on the protocols. AIFactory, PFactory, TFactory and CFactory re-vendor `protocol.py` together.

## Affected users and systems

Factory hub protocol; the four vendored copies and their drift-gate pins; any caller still typed to the protocol that uses the methods (none after Factory#3771).

## Constraints

Must land after every Factory#3771 site is merged. Concrete providers keep their methods. Re-vendors go in one coordinated set so the four copies never disagree.

## Open questions

None.
