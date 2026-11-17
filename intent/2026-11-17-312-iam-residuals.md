---
status: approved
issue: 312
author: olafkfreund
---

# Intent: Agent-doable residue of the IAM epic (#312)

## Problem

Three items of #312 are still open for an agent: (1) nothing proves that no production manifest sets `DISABLE_AUTH`, and nothing stops one appearing; (2) the steps for flipping `RBAC_ENFORCE_TASK_ROUTES` in PFactory and TFactory are scattered, so the owner has no checklist for a flip that can lock people out; (3) the MFA work (#3781) needs recording on the epic. The rest of #312 is the owner's (retire `APP_API_TOKEN` and `CFACTORY_MCP_SECRET` in production, admin key revoke S4, signing the access review).

## Proposed outcome

- Evidence: a grep of every deployable file in factory-gitops, and of the service repos' deploy files, showing `DISABLE_AUTH` appears only in docs, test CI env and comments.
- A CI check in factory-gitops (the repo Argo CD syncs) that fails if `DISABLE_AUTH` appears in any deployable file.
- A cutover runbook in `docs/compliance/` for the PF/TF role-enforcement flag: preconditions, how to read shadow mode, the flip, verification, rollback. The owner flips it.
- Comments on #312 and #3781 with the evidence.

## Affected users and systems

factory-gitops CI; Factory docs. No runtime behaviour changes.

## Constraints

- Do not flip the flag, touch secrets or the live cluster.
- The check must run on every PR (no paths filter) so a required check never goes missing.

## Limits

A grep sees literals in the repo's deployable files (manifests, kustomize and Helm values, workflows), not values injected from a Secret or ConfigMap at runtime. The services themselves refuse `DISABLE_AUTH` on a non-loopback host (`server/config.py` in AIFactory, PFactory, TFactory), so the CI check is the second layer, not the only one.

## Open questions

None. Decision (owner delegation 2026-11-17): put the check in factory-gitops, not the hub, because that is the only repo whose manifests reach production; a Kyverno policy was not chosen because the file never needs to be admitted to the cluster to be wrong, and the flag is in a Deployment env that a CI grep covers earlier and without a cluster rollout.
