# Framework Applicability Decision Record

- **Owner:** Security Owner (CISO function), see [roles.md](roles.md)
- **Review cadence:** Annually, and at each new customer or contract
- **Issue:** Factory#3697 (parent Factory#310)
- **Decided:** 2026-11-16, by the owner's delegation ("use the recommendations"), taking the
  recommended option: not applicable to a non-regulated single-operator platform.

This record settles the four frameworks the [README](README.md) listed as conditional. ISO 27001
and SOC 2 are in scope (2026-07-24), PCI DSS is scoped out and FedRAMP is deferred; those are
recorded in the README and are not repeated here.

## Premises

The decision holds only while all three are true. They are premises taken from the delegated
recommendation, not facts this repository can verify. The owner confirms them in the table at
the end; if any is false, the affected rows below are reopened.

1. The operator is not a public company and has no SEC reporting obligation.
2. Neither the operator nor any customer is a financial firm regulated in a way that reaches the
   fleet (NYDFS-covered entity, bank supervised under the FFIEC handbook).
3. The fleet does not affect anyone's financial reporting.

## Decision

| Framework | Question | Decision | Re-scope trigger (means review, not "applies") | Reassessment action |
|---|---|---|---|---|
| SEC cyber rules | Is the operator, or will it be, a public company? | Not applicable | The operator becomes an SEC registrant, or a public company's disclosing subsidiary. | Review Item 1.05 (4 business days from the materiality determination) and the risk-management disclosure duties; make the SEC row of the [breach matrix](policies/incident-response.md) active; assign the materiality decision-maker. |
| NYDFS Part 500 | Is the operator, or a customer, a NYDFS-covered entity? Would a 500.19 exemption apply? | Not applicable; 500.19 does not arise | The operator or a customer becomes a regulated financial firm, or a customer contract makes the operator its third-party service provider (500.11). | Decide first whether the operator is itself a covered entity (every section applies) or only a customer's service provider (500.11 and the contract apply). Activate only that scope in [nydfs-part500-mapping.md](nydfs-part500-mapping.md), make the 500.19 determination there, and name the 500.17(b) signers. |
| FFIEC IT Handbook | Is a customer, or the operator, an FFIEC-supervised institution? | Not applicable | A customer that is an FFIEC-supervised institution asks for evidence under the Outsourcing Technology Services or other booklets. | Compare the booklet-level mapping in the [control matrix](control-matrix.md) with the customer's examiner expectations; open a gap assessment for the booklets requested. |
| SOX ITGC | Does the fleet affect anyone's financial reporting? | Not applicable | The fleet's output or hosting is used in a public company's financial-reporting systems. | Assess whether the fleet is in scope of that company's ITGC. If so, open a gap assessment and add the computer-operations ITGC domain (job scheduling, backup and recovery, incident handling), which the control matrix does not map today. |

When a framework is confirmed as applicable, open a gap assessment modelled on
[soc2-gap-assessment.md](soc2-gap-assessment.md) and change its row in the README scope table.

## What stays as reference

The [NYDFS mapping](nydfs-part500-mapping.md) is kept, withdrawn from active scope, so a
re-scope starts from a mapped baseline. The FFIEC, SEC and SOX ITGC columns of the
[control matrix](control-matrix.md) remain reference mappings. Neither is a claim of compliance.
The breach-notification rows for SEC and NYDFS in the [IR runbook](policies/incident-response.md)
are marked not applicable while out of scope.

## Premise check (owner)

> TEMPLATE: not a record. Leave every field empty until the owner has checked it.

| Premise | True? | Date checked | By |
|---|---|---|---|
| 1. Not a public company; no SEC reporting obligation | | | |
| 2. No regulated financial firm among operator or customers | | | |
| 3. Fleet does not affect anyone's financial reporting | | | |

Re-run this table at each new customer or contract and at the annual review.
