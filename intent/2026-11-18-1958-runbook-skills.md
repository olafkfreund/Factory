---
status: approved
issue: 1958
author: olafkfreund
---

# Intent: runbook skills for TFactory and CFactory (Substitution Test Q2), MCP allowlist (Q3)

Issue: olafkfreund/Factory#1958. Delegation: owner, 2026-11-18.

## Problem

Substitution Test Q2 asks whether an agent can run a service's operations from a
checked-in skill. AIFactory has `deployment-runbook` (AIFactory#2136) and PFactory
has `rbac-enforce-runbook` (PFactory#1075). TFactory has 10 skills under
`.claude/skills/`, none over a deploy or release procedure. CFactory has no
`.claude/` directory at all. The real procedures exist only as workflow YAML
(`deploy.yml`, `release.yml`, `deploy-drift.yml`) and RELEASE.md, and TFactory's
RELEASE.md is partly stale: it describes a manual tag and `gh release create`, while
`release.yml` tags and releases automatically when the `package.json` version field changes on `main`.

Q3 (no central reviewed MCP allowlist) is a separate, larger piece of work: a hub
file, a drift script across four services and a CI step.

## Proposed outcome

- `TFactory/.claude/skills/tfactory-deploy-runbook/SKILL.md` and
  `CFactory/.claude/skills/cfactory-deploy-runbook/SKILL.md`, each following only
  steps that exist in the repo's workflows and docs, with verification commands and a
  rollback, in the style of the two reference skills.
- CFactory AGENTS.md checked against RELEASE.md and `deploy.yml`; any inconsistency
  fixed.
- Q3 filed as its own child issue with the design, not built in this round.

## Affected users and systems

Agents and operators working in TFactory and CFactory. No runtime code, no cluster
change, no workflow change.

## Constraints

- No invented steps; every step traces to a workflow, chart or doc line.
- Read-only commands only for verification; the skill tells the agent not to touch
  the live cluster or `factory-gitops` itself without the operator.
- No secret values handled or printed.
- Base branch `dev` in both repos; artifacts in Factory (`main`).

## Open questions

None. Decision (owner delegation 2026-11-18): do Q2 fully and defer Q3 to a child
issue, because Q3 spans the hub plus four services and a CI gate and does not fit one
lead's round without risk; the flip criterion is recorded in the child issue.
