---
status: draft
issue: 1958
author: olafkfreund
---

# Intent: Substitution Test score, the agent-doable part

## Problem

Epic #1958 accepts only a Substitution Test score of 10+ out of 12 (playbook Appendix C),
with evidence per question. The 2026-11-18 11:56 re-score comment's table reads 2 yes, 5 partial, 4 no,
1 not re-verified (its prose tally said 4 partial and 2 not re-verified; the table is right). Several answers are weaker than they need to be for lack of files and a
written record, not lack of work: no `AGENTS.md` in the hub or CFactory (Q1), skills not
re-checked in the services (Q2), no written statement of the MCP tool set and where it is
enforced (Q3), `enforce_admins` state not recorded across all repos (Q8), and the
benchmark workflow not named as the eval suite (Q10).

## Proposed outcome

- `AGENTS.md` at the root of the hub and of CFactory (Q1).
- A recorded Agent Skill coverage check; a SKILL.md added only where a procedure already
  exists in a runbook (Q2).
- A recorded MCP inventory and enforcement point per service, honestly marked partial
  where there is no central allowlist (Q3).
- `enforce_admins` state for all repos recorded, with a proposal only (Q8).
- Q10 assessed, not presumed: record whether the weekly benchmark (Factory#3779, gated on
  `BENCH_ENABLED`, owner-provided runner, #3713) can qualify a model in a day, and list the
  blockers. Existence of the workflow alone does not score yes.
- A new per-question comment on #1958 with the honest score; acceptance item 1 ticked
  only if 10+ with evidence.

## Affected users and systems

Factory (hub, `main`), CFactory, AIFactory, PFactory (`dev`). TFactory is covered by the
checks (Q2, Q3, Q8) and changed only if a runbook exists. Q8 covers Factory, AIFactory,
PFactory, TFactory, CFactory and factory-gitops, each protected branch listed. No runtime code, no cluster,
no branch-protection change.

## Constraints

- No invented procedures: a skill is added only for a runbook that exists.
- No secrets; no branch protection changes (owner decision); no live cluster access.
- Questions that wait on #1959 (Q4, Q5, Q7), PFactory signature identity (Q9, Q12) or
  owner steps are marked as such, not scored up.

## Open questions

None. Owner delegation 2026-11-18 covers the recommended option for each.
