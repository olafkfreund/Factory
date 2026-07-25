# Acceptable Use Policy

- **Policy owner:** Security Owner (CISO function) — see [roles.md](../roles.md)
- **Applies to:** Everyone and everything that uses fleet systems, credentials, or agents
- **Review cadence:** Annually
- **Frameworks:** ISO/IEC 27001:2022 A.5.10, A.6.2, A.8.1; SOC 2 CC1.1, CC2.2

## Purpose

To state how the Factory fleet's systems, credentials, data, and AI agents may and may
not be used, so that acceptable-use expectations are explicit and enforceable rather
than assumed.

## Scope

All human contributors and operators, and by extension the automated agents they run.
Covers the six repositories, the cluster and its data stores, CI/CD, issued credentials,
and interaction with third-party services (LLM providers, GitHub, cloud).

## Policy statements

1. **Authorized purpose only.** Fleet systems and credentials are used only for
   operating, building, and improving the Factory fleet. No personal, unlawful, or
   otherwise unauthorized use.
2. **Protect credentials.** Credentials are never committed to source, pasted into
   issues or logs, or passed on a command line where they land in process listings
   (agent execution scrubs a deny-list of secret env vars and pushes via
   `gh auth git-credential`, not bare tokens). Report a suspected credential exposure
   immediately as an incident.
3. **Least data.** Only the data needed for a task is introduced into the fleet.
   Personal data and regulated data are handled per the
   [data-classification-and-handling-policy.md](data-classification-and-handling-policy.md);
   do not paste real customer PII into task specs when synthetic data suffices.
4. **Use the pipeline.** Code and infrastructure change reaches production through the
   reviewed PARR pipeline and CI gates, not by manual out-of-band edits to running
   systems, except during a declared incident under the Incident Commander's direction.
5. **Do not disable controls.** Security controls (auth, sandboxing, egress guards,
   scanners, signing) are not bypassed or disabled outside a sanctioned, recorded
   exception. Auth-disable flags must not be set in production.
6. **Responsible agent operation.** Operators are accountable for the actions of agents
   they run. Agents run inside the provided sandbox and egress boundaries; untrusted
   content is treated as hostile input, never as instructions (see the
   [agentic-ai governance](agentic-ai-governance.md) domain).
7. **Report concerns.** Suspected security weaknesses, incidents, or policy violations
   are reported to the Security Owner or through the repositories' `SECURITY.md`
   coordinated-disclosure channel.

## Roles and responsibilities

- **Contributors and operators** — comply with this policy and report violations.
- **Security Owner** — owns the policy, grants exceptions, and handles violations
  (escalation, and where an incident results, the incident process).

## Related controls

- [access-control-policy.md](access-control-policy.md) — who may access what
- [secrets-management.md](secrets-management.md) — credential handling
- [agentic-ai-governance.md](agentic-ai-governance.md) — agent behaviour controls
- [incident-response-policy.md](incident-response-policy.md) — reporting a violation or exposure
