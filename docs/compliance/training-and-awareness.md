# Security Awareness and Training

- **Policy owner:** Security Owner (CISO function) — see [roles.md](roles.md)
- **Review cadence:** Annually, and after any Sev-1 incident or material policy change
- **Frameworks:** ISO/IEC 27001:2022 A.6.3 and Clause 7.2/7.3; SOC 2 CC1.4;
  NYDFS 500.10 and 500.14 (reference only, not applicable: see [framework-applicability.md](framework-applicability.md));
  FedRAMP AT family (deferred); PCI DSS 12.6 (scoped out)
- **Issue:** Factory#3693

This document defines what security training the fleet's people receive, how often,
and the dated record that proves it happened. It is a procedure. It is not a record:
no training is claimed here. A.6.3 and CC1.4 stay Planned/Gap until the first
completion record below is filled in by the Security Owner.

## Audience

Everyone with access to the fleet: the Security Owner, any contributor with push or
cluster access, and any human who operates agents that act with fleet credentials
(agents authenticate as the operator, see [agent-identity.md](agent-identity.md)). Agents
themselves are covered by [agentic-ai-governance.md](policies/agentic-ai-governance.md),
not by this training.

## Content

The policy set is the baseline material. Each cycle covers:

| Topic | Source material |
|---|---|
| ISMS purpose, roles, how to raise an issue or exception | [information-security-policy.md](policies/information-security-policy.md), [roles.md](roles.md) |
| Acceptable use of fleet systems and agents | [acceptable-use-policy.md](policies/acceptable-use-policy.md) |
| Least privilege, MFA, credential handling | [access-control-policy.md](policies/access-control-policy.md), [secrets-management.md](policies/secrets-management.md) |
| Data classes and what may go to a third-party LLM | [data-classification-and-handling-policy.md](policies/data-classification-and-handling-policy.md) |
| Reporting and handling an incident | [incident-response-policy.md](policies/incident-response-policy.md), [incident-response.md](policies/incident-response.md) |
| Secure change: PR review, signed commits, no direct pushes | [secure-sdlc-policy.md](policies/secure-sdlc-policy.md), [change-management-sod.md](policies/change-management-sod.md) |
| Operator endpoint rules | [operator-endpoint-standard.md](operator-endpoint-standard.md) |
| Phishing, social engineering, prompt injection and agent misuse | the above, plus [agentic-ai-governance.md](policies/agentic-ai-governance.md) |

Content is reviewed at each annual review; the record names the content version
(the git commit of the policy set used).

## Cadence

1. **On joining**, before fleet credentials are issued.
2. **Annually**, within 12 months of the last completion.
3. **After a Sev-1 incident or a material policy change**, a short briefing on what changed.

## Delivery

Self-study of the material above, followed by a short acknowledgement that the person
read it and can name how to report an incident. The Security Owner keeps the records
under `docs/compliance/training-records/` (create the directory with the first record).

## Screening

The fleet has no hiring or employment process (SoA A.6.1 and A.6.2 are Not Applicable,
with no credit). For a one-operator fleet, screening is recorded as not applicable:
access is granted to named individuals the Security Owner already knows, and each
grant goes through the access-control policy. Re-scope when the team formalizes
employment or onboards a contractor, and record the screening applied then.

## Evidence and what flips the rows

The first dated completion record, filled in by the Security Owner, is the evidence
for SoA A.6.3 and SOC 2 CC1.4. The assessor re-reads it against the criterion; CC1.4
also needs the competence side, which the screening statement above addresses.

### Completion record (template)

> TEMPLATE: not a record. Copy per person and cycle. Leave every field empty until it
> has actually happened.

| Field | Value |
|---|---|
| Person | |
| Role | |
| Cycle (on joining / annual / post-incident) | |
| Content version (policy-set commit) | |
| Method | |
| Date completed | |
| Acknowledgement (reads and can report an incident) | |
| Recorded by (Security Owner) | |
| Signature | |
