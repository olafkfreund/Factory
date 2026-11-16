# Incident-response tabletop: scenario and record (Factory#3688, R-009)

A tabletop exercises `policies/incident-response.md` with no live system touched. It has not been
run yet; the first run is the owner's. Running it and filing the record is what closes gap 3 of the
policy ("Runbook untested") and supports SoA A.8.16 and SOC 2 CC7.3 and CC7.4. This page is the
script and the blank record; it is not evidence of an exercise until the record below is filled in.

## Setup

- 60 to 90 minutes. Facilitator reads the injects; the IC answers from the runbook, not from memory.
- Roles per the policy: Incident Commander, technical lead, comms and notification owner,
  materiality decision-maker, scribe. One person may hold several; name who held which.
- Nothing is changed in the cluster. Where the runbook says "rotate" or "scale down", the group
  states the exact command and who would run it.

## Scenario: leaked token, auth-failure burst, odd egress

| Inject | Time | Facts given | Questions the group must answer from the runbook |
|---|---|---|---|
| 1 | T+0 | `security-alerts` opens issue `security-alert: auth_failure_spike fired (47 in 30 min, threshold 10)`. Rows in `audit_chain` show `auth.failure` against CFactory from two source actors. | Who is paged and by what channel today (honest answer: nobody; the issue is the signal)? Who is IC? Severity? Where is t0 recorded? |
| 2 | T+20 | A sibling's task Job logs show successful calls with the shared `API_TOKEN` from an unexpected actor, after the failures stop. | Confirmed or suspected? Severity change? Which containment step, and what is the fleet-wide blast radius of revoking the wildcard token? |
| 3 | T+40 | A sandbox Job is seen opening HTTPS connections to an unknown host. There is no egress log (`egress_anomaly` is `not_configured`). | What evidence exists to scope this? What do you do without egress telemetry? |
| 4 | T+60 | Postgres job-state may have been read. Counsel asks whether notification clocks have started. | Is a regime plausibly applicable (GDPR, NYDFS 72 h, SEC four business days)? Who decides materiality? When is t0? What does recovery look like given no tested backups (policy gap 5)? |

## Record template (copy to `docs/compliance/ir-tabletop-records/YYYY-MM-DD.md`)

```markdown
# IR tabletop record: <date>

- Scenario: leaked token, auth-failure burst, odd egress (docs/compliance/ir-tabletop.md)
- Facilitator: <name>   Scribe: <name>   Duration: <min>
- Participants and roles: <name: role, ...>
- Runbook version exercised: <git SHA of policies/incident-response.md>

## Timeline as exercised
| Inject | Decision taken | Runbook step used | Time to decision |
|---|---|---|---|

## What worked / what did not
- Detection (alert to human):
- Severity and t0 determination:
- Containment (could every command be named and run by the named person?):
- Notification (materiality owner reachable? contacts known?):
- Recovery (given the backup gap):

## Gaps found
| Gap | Runbook section | Owner | Issue | Due |
|---|---|---|---|---|

## Result
- Pass / pass with actions / fail:
- Paging destination in place at the time of the exercise: yes / no
- Next exercise due:
- Signed off by (IC): <name>   Date: <date>
```

## What to do after

File the record, open one issue per gap, update gap 3 of `policies/incident-response.md` and the
R-009 row of `risk-register.md` with the record's path, and only then change the score.
