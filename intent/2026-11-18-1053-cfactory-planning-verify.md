---
status: approved
issue: 1053
author: olafkfreund
---

# Intent: verify CFactory to PFactory planning after release (PFactory#1053)

## Problem
PFactory#1065 added `cfactory` to `SourceChannel`. The issue was left open until the fix was released and seen working live. Factory#1958 item 3 also needs a schema-2 signed plan in the live registry.

## Proposed outcome
v0.8.5 is live, a hard CFactory card plans with HTTP 2xx, PFactory#1053 is closed with evidence, and Factory#1958 gets the registry result.

## Affected users and systems
PFactory deployment `factory/pfactory`, CFactory card flow, plan registry in the pfactory pod.

## Constraints
No Kubernetes writes (read-only `kubectl`); application-level test data (one card, one plan session) is allowed. No owner signature by an agent.

## Open questions
None.
