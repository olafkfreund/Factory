---
status: approved
issue: 320
author: olafkfreund
---

# Intent: outbound PII scrub is mandatory for regulated projects

## Problem

Factory#320 says PII goes to LLM providers by default because `scrubBeforeSend` is
opt-in. That premise is stale. Since AIFactory #1128 / #1133 (2026-07-30) the outbound
scrub is ON by default on every LLM path (`apps/backend/core/outbound_scrub.py`,
`providers/__init__.py` `__init_subclass__`, the Claude SDK client factories, the
insights strategies), fail-closed, with one deployment-wide kill-switch,
`LITELLM_AUDIT_SCRUB_OUTBOUND=false`.

What is still missing:

1. AIFactory has no project-level data classification, so nothing ties the scrub to
   the policy's "Regulated" tier.
2. The kill-switch turns the scrub off for every project at once, including any
   project holding regulated data. The policy's Regulated handling floor is "redact
   before third-party egress", which is not optional.
3. The Factory policy docs (`data-classification-and-handling-policy.md` statement 2,
   `data-governance.md` "Redaction posture") still describe the scrub as opt-in and
   default-off, which is now wrong.
4. DSAR / per-record erasure is listed as a gap with no decision on whether it is in scope.

## Proposed outcome

- A project has a `dataClassification` setting: `public | internal | confidential |
  regulated`, default `internal` when unset.
- A `regulated` project's outbound prompts are always scrubbed: the kill-switch and any
  per-adapter `scrub_outbound=False` pin are ignored for it.
- Every other tier keeps today's behaviour exactly (scrub on by default, kill-switch honoured).
- The Factory policy docs state the real posture, the regulated rule, and that DSAR is
  out of scope with the trigger that brings it back.

## Affected users and systems

- AIFactory web-server (project settings API, settings allowlist, agent/spec/PR-review/
  changelog spawn env, insights chat) and backend (outbound scrub chokepoints).
- Factory `docs/compliance/policies/`.
- Operators who set the kill-switch: regulated projects stop following it.

## Constraints

- Smallest change; reuse the existing per-project settings store and env injection
  (`project_settings_store.load_project_env`) and the existing scrub. No new pattern set,
  no second kill-switch.
- Must not change behaviour for unclassified projects.
- No secrets, no names of people or organisations in docs.

## Open questions

- Which classification to use? Decided (lead recommendation, user-approved 2026-10-24):
  none exists in AIFactory, so add project setting `dataClassification`, default `internal`,
  tiers from the Factory policy.
- Scrub default per tier? Decided (lead recommendation, user-approved 2026-10-24): on by
  default for `regulated`; other tiers keep today's behaviour. Note: "today" is default-on
  with a kill-switch, not opt-in; this lane does not weaken it.
- Is an explicit opt-out respected for regulated? Decided (lead recommendation,
  user-approved 2026-10-24): only if the policy allows it. The policy's Regulated floor
  requires redaction before third-party egress, so no: the kill-switch and adapter pins
  are ignored for `regulated`.
- DSAR / right-to-erasure? Decided (lead recommendation, user-approved 2026-10-24): out
  of scope, because no PII is in scope today. Recorded in the policy with its trigger.
