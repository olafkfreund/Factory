---
status: approved
issue: 1053
spec: spec/2026-11-18-1053-cfactory-planning-verify.md
# reviewers:
#   - codex
---

# Plan: verify CFactory to PFactory planning

Decisions: no release or bump (v0.8.5 is live); verify read-only plus one test card; stop at the owner approval step for the signature. No file-editing steps, so no `coders:`.

## Steps
1. Confirm `f8dfbd59` is in v0.8.5 and `kubectl get deploy pfactory` shows `sha-5672b01` -> done, matches.
2. Create hard card FCT-10, `cfactory_plan_card` -> HTTP 200, `source_channel: cfactory`.
3. `plan_process` the session -> processed, gates passed.
4. `python -m plan.governance_cli --root /home/nonroot/.pfactory/plan-docs --json` -> schema2 0 (emit needs owner approval).
5. Close PFactory#1053 with evidence; comment on Factory#1958.

## Tests
Steps 2 to 4 are the checks.

## Rollback
None needed; no change made. Delete card FCT-10 if unwanted.
