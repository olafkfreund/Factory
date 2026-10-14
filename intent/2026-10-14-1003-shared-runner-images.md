---
status: draft
issue: 1003
author: olafkfreund
---

# Intent: one source for the six runner images TFactory and PFactory both build

## Problem

TFactory (`docker/tfactory-runner-*`) and PFactory (`docker/pfactory-runner-*`)
each build six test-runner images: cloud, cypress, jest, playwright, pytest
and vitest. Normalised for the repo name, the Dockerfiles are identical except
for two OCI `LABEL` lines (re-checked for vitest on 2026-10-14: still
identical). About 580 lines are duplicated.

Every fleet-wide image change has to be made twice by hand, and nothing
notices when one copy is missed. On 2026-08-27 a security refresh touched 16
Dockerfiles across both repos, and the Cypress Chrome-repo fix had to be
applied twice. There is no drift gate on these files.

## Proposed outcome

- Each of the six runner images has exactly one Dockerfile, built and
  cosign-signed in one place.
- Both factories run Jobs from that one image, which Kyverno admits and
  verifies (`verify-factory-image-signatures`,
  `require-first-party-signature-coverage`).
- The duplicate Dockerfiles, and the CI that builds them, are deleted.
- The `SECURITY_REFRESH` cache-bust and its guard test keep working for the
  surviving copy.

## Affected users and systems

- TFactory and PFactory: `docker/*-runner-{cloud,cypress,jest,playwright,pytest,vitest}`,
  the image-build workflows, and code that names images. In PFactory that
  includes `agents/cloud/runner.py`, `lang_typescript/*`,
  `framework_registry/descriptor.py` and `tools/runners/docker_runner.py`.
- factory-gitops Kyverno policies: an image no rule names is rejected at
  admission.
- Every running PFactory or TFactory task that starts a runner Job.

## Constraints

- Kyverno coverage changes land **before** any consumer switches image.
  Otherwise every Job is rejected at admission.
- Signing stays keyless cosign via GitHub OIDC (Factory#524).
- Switch one runner first (vitest, the smallest blast radius) and confirm a
  Job admits and runs before moving the rest.
- Don't vendor Dockerfiles through the hub pin. A shared pin re-baselines
  every governed file (AIFactory#1440).
- The five single-consumer runners (nix, java, cucumber, portal-ui,
  selenium) stay where they are.

## Open questions

1. **Where the single copy lives.** My recommendation is (a), because it is
   the smallest change:
   - **(a) TFactory stays the owner, and PFactory uses
     `ghcr.io/olafkfreund/tfactory-runner-*`.** These images are already
     built, signed and named in the Kyverno verify policy. No new repo, no
     new CI, and probably no policy change. The cost is a "tfactory" name on
     images PFactory runs, which is cosmetic.
   - **(b) A new `factory-runners` repo publishing `factory-runner-*`**, as
     the issue proposes. Cleaner names, but it means a new repo, a new
     matrix build and signing, Kyverno policy updates, and both consumers
     switching.
2. Can PFactory's Jobs run the TFactory images unchanged? For example, do
   any of PFactory's six images carry PFactory-only content beyond the
   labels? This gets checked for all six before the spec, not just vitest.
3. Merge approval up front: may I merge this task's PRs once CI is green,
   without asking again?
