---
status: approved
issue: 3688
author: olafkfreund
---

# Intent: auth-failure and egress alerts, IR tabletop (R-009)

## Problem

Risk R-009 (detection and response) sits at 12, target 6. Three things are missing:
nothing alerts on auth-failure spikes (they are only queryable in the `audit_chain`
stream), nothing alerts on egress anomalies (no egress telemetry exists at all), and the
incident-response runbook has never been exercised. There is also no paging destination.

## Proposed outcome

- A scheduled job in factory-gitops evaluates an auth-failure rule and an egress rule
  against OpenObserve, writes a `job_health` record per rule, opens one GitHub issue per
  firing rule (same pattern as `secret-rotation-report`) and, only if the owner supplies a
  webhook, also posts to it. Webhook off by default.
- job-watchdog already watches the new CronJob, so a dead evaluator is itself reported.
- Factory docs hold a tabletop scenario and a blank record template, so the owner can run
  the exercise and file the record.
- The egress rule is preparation: it reads a stream the owner must first populate, and
  reports `not_configured` (never ok) until then. It detects nothing today.
- Routing the existing `job_health` failures to a pager needs the owner's destination; the
  docs give the exact steps. This slice leaves #3688 open and does not by itself move R-009
  to its target score.
- Docs state plainly what stays open: the paging destination, the egress telemetry source,
  and running the tabletop.

## Affected users and systems

factory-gitops (new `apps/security-alerts`), Factory `docs/compliance`, the owner as IR owner.

## Constraints

No live-cluster action by the agent; ArgoCD syncs the new app after merge. No secret values
read or printed. Egress rule must not report "ok" while no egress source exists. Webhook
URL and GitHub token are optional secret references; absent means inert.

## Open questions

None for the agent slice. Owner decisions (paging channel and credential, egress source,
tabletop date) go to the PR as owner actions.
