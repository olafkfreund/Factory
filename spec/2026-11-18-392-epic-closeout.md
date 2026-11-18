---
status: draft
issue: 392
intent: intent/2026-11-18-392-epic-closeout.md
---

# Spec: Close out epic checklists after the 2026-11-18 merges

## Design

Verify against the trees (origin/dev of the services, origin/main of Factory and factory-gitops) and the live cluster (read-only get), then edit issue bodies with gh and add one status comment per issue.

- #392: tick Phases 3, 4, 5 as "code merged, flag off; live smoke test pending (owner)". Evidence: CFactory#543 (c66bd3a) jira connection behind CFACTORY_JIRA_ENABLED (tests/test_jira_connection.py covers default off); hub Factory#3809 (c6490cf) JiraProvider; CFactory#546 (a467215) work_item_connection_id, Alembic head 7e4c2a91d6b8 (no later down_revision); hub Factory#3812 (479f2a5) Bitbucket behind FACTORY_BITBUCKET_ENABLED; services AIFactory#2122, PFactory#1067, TFactory#1561, CFactory#545. #3775 and #3776 get closing-status comments and stay open for the owner's live smoke tests.
- #1959: tick only the hot-reloadable ConfigMap box if its evidence holds (factory-gitops#375 cc10736; live ConfigMap model-routes in ns gateway), with the pod-UID proof stated as pending. Comment splits the rest into agent-doable (gateway-side per-route quota, spend attribution, failover, telemetry normalisation; AIFactory apps/model-gateway/gateway.py has route resolution only; AC-1 migration, live scan 18 violations) and owner-only (Secret, token seeding, Plane B bench test, key rotation).
- #1958: re-score the twelve-question Substitution Test (playbook Appendix C) from evidence in a comment; tick nothing new.
- #312, #324, #310, #314: confirm AIFactory#2121, PFactory#1066, TFactory#1560, CFactory#544, Factory#3811 merged; add a current-status block to each body linking docs/compliance/audit-readiness.md; tick nothing owner-gated.
- #3701: reply only. Catch-all policy is Audit; flip to Enforce on or after 2026-11-23 only if the PolicyReport has zero fail results; the live kubectl debug check is the owner's.

## Alternatives rejected

- Ticking on "merged" alone: rejected, acceptance needs live proof.
- Closing #3775/#3776: rejected, the live smoke tests are owner-only.

## Risks

Live numbers are timestamped 2026-11-18. A body edit can overwrite a concurrent edit: read the body immediately before editing.

## Verification

gh issue view shows the edited bodies and comments; git diff shows only these three files.
