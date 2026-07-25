# Incident Response Policy

- **Policy owner:** Security Owner (CISO function); Incident Commander per incident —
  see [roles.md](../roles.md)
- **Applies to:** All security and availability incidents affecting the fleet
- **Review cadence:** Annually, and after every Sev-1/Sev-2 incident and tabletop
- **Frameworks:** ISO/IEC 27001:2022 A.5.24-.28; SOC 2 CC7.3-.5; NYDFS 500.17;
  SEC Reg S-K Item 1.05; GDPR Art. 33/34; NIST IR

This policy sets the rules and accountability for incident response. The operational
detail — severity classification, roles, the numbered lifecycle, forensics, and the
breach-notification matrix — lives in the
[incident-response runbook](incident-response.md) (Factory#319). This policy does not
restate it; it points to it and makes it binding.

## Purpose

To ensure security and availability incidents are detected, classified, contained,
eradicated, recovered, reviewed, and — where legally required — notified within statutory
timelines.

## Scope

All incidents affecting the six repositories, the cluster, the data stores, CI/CD, or
data the fleet processes, including suspected credential exposure, prompt-injection or
agent-misuse events, supply-chain compromise, and availability/data-loss events.

## Policy statements

1. **Every incident is run to the runbook.** Incidents follow the lifecycle in the
   [runbook](incident-response.md): detection and reporting, triage (t0 = confirmed),
   containment, eradication, recovery, and a blameless post-incident review within 5
   business days.
2. **An Incident Commander is assigned.** Each incident has a named Incident Commander
   (default: the Security Owner, delegable) who owns it to resolution and owns the
   notification decisions.
3. **Report immediately.** Suspected incidents are reported without delay via the
   Security Owner or the repositories' `SECURITY.md` coordinated-disclosure channel.
   `SECURITY.md` exists in PFactory, AIFactory, and TFactory; adding it to Factory and
   CFactory is a tracked governance-coverage gap.
4. **Statutory notification timelines are honored.** When an incident meets a
   notification threshold, the clock that governs is the shortest applicable one, per the
   runbook's breach-notification matrix: SEC 8-K within 4 business days of a materiality
   determination; NYDFS within 72 hours of determination; GDPR within 72 hours of
   awareness. The Materiality decision-maker role makes the SEC determination.
5. **Preserve evidence.** The tamper-evident audit hash-chain and its air-gapped
   verifier (`verify-chain`) are the forensic timeline; incident handling preserves and
   exports the relevant audit evidence before remediation destroys state.
6. **Detection and alerting must improve.** There is currently no alerting or paging
   (no Alertmanager/PagerDuty/Opsgenie/Slack wiring) and no security detection layer
   beyond a pipeline-health heuristic — the highest-priority IR gap. Wiring alerting on
   audit-anchor failure, chain-break, and auth-failure spikes is Wave 1 remediation
   (risk R-009). Until then, detection depends on human observation and the runbook is
   untested by tabletop — both documented risks.
7. **AI-specific incidents.** Agent misuse, prompt-injection breakout, or unexpected
   agent egress are in scope; the runbook is the entry point and the
   [agentic-ai governance](agentic-ai-governance.md) domain supplies the technical
   context.
8. **Learn and record.** Every post-incident review produces corrective actions with
   owners and due dates, fed into the [risk register](../risk-register.md) and the
   quarterly management review; the minutes are retained as evidence.

## Roles and responsibilities

- **Incident Commander** — runs the incident and owns notification decisions.
- **Materiality decision-maker** — determines SEC materiality (starts the 4-business-day
  clock).
- **Security Owner** — owns this policy, is default Incident Commander, and ensures
  corrective actions close.
- **All contributors** — report suspected incidents immediately.

## Related controls

- [incident-response.md](incident-response.md) — the operational runbook and breach-notification matrix
- [audit-logging.md](audit-logging.md) — forensic evidence and (planned) alerting
- [business-continuity-policy.md](business-continuity-policy.md) — recovery during a data-loss incident
- [risk-register.md](../risk-register.md) — R-009 (no alerting/paging)
