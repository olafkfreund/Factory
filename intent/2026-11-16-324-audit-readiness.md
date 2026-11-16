---
status: approved
issue: 324
author: olafkfreund
---

# Intent: Audit-readiness checklist, mock-audit plan, stale compliance text

## Problem

The #324 issue body has four unchecked boxes. The 2026-11-14 comments confirm the matrix box is done, so three remain. Verified against `main` on 2026-11-16:

- Automated evidence collection: runs daily, but the code-scanning snapshot needs
  an `evidence-github-token` secret that only the owner can create.
- Per-framework gap assessment: ISO 27001 (SoA) and SOC 2 are written. The
  residual-risk sign-off table is empty and only the Security Owner can sign it.
- Readiness checklist and mock audit: no checklist and no concrete mock-audit plan exist. The audit programme in `management-review-and-internal-audit.md` section 2 already defines scope, independence and the report template, and no audit record exists yet.
- Stale text (follow-up work found by review, not one of the boxes): several compliance files still describe the pre-refresh state
  (no backups, scrub default off, no policy set or SoA, closed issue numbers),
  which contradicts the SoA and risk register an assessor reads next to them.

## Proposed outcome

- One assessor-facing page, `docs/compliance/audit-readiness.md`, holding a
  readiness checklist (each item: status, evidence link, owner) and a mock-audit
  plan that is written so a held mock audit counts as the first independent
  review (#3694, ISO A.5.35).
- The stale statements named above corrected to what the code, cluster and
  newer documents show, with a pointer to the open tracker where one exists.
- A test that every link and evidence path in the new page resolves.
- Owner-only steps listed with exact commands.

## Affected users and systems

Assessors, the Security Owner, `docs/compliance/` in Factory. No runtime change.

## Constraints

- Docs and one test only. No cluster change, no secret handling.
- No SoA or SOC 2 rating changes: those are the owner's call (A.8.8, A.8.13).
- Do not edit text owned by open work: alerting, paging and IR (#3688), key
  expiry (#3689), backup rows and the off-cluster copy (#3681, #3691).
- Do not claim the mock audit was held. The plan only describes it.

## Open questions

None. The mock-audit date and the independent reviewer are owner decisions,
listed under owner actions.
