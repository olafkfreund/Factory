---
status: draft
issue: 320
author: olafkfreund
---
# Intent: sub-processor list, data residency and Postgres retention

**Problem:** `data-classification-and-handling-policy.md:48` says Postgres has no retention policy, and line 52/60 promise a sub-processor list that does not exist. An assessor cannot see which third parties receive data, where they hold it, or how long each table keeps rows.
**Outcome:** `data-governance.md` gains a sub-processors section (every LLM/provider the fleet egresses to, from AIFactory `providers/` and the factory-secrets key names, with residency per provider) and a per-table Postgres retention schedule (audit 395 days, already in code). Line 48 points to it. Part of #320, does not close it.
**Affected:** Factory `docs/compliance/policies/`.
**Constraints:** No secret values, only key names. Making PII scrubbing default (R-004) is out of scope, an owner decision.
**Open questions:** Tables with no retention in code: record "kept until deleted" honestly, or propose a number? Default: record as-is and flag.
