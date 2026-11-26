---
status: draft
issue: 3922
author: olafkfreund
---

# Intent: build Job names must not collide across projects

## Problem

`scripts/job_dispatch.py` names every build Job `factory-<service>-<_short(job_id)>`. `_short`
keeps only the last 20 characters of the job id. AIFactory's job id is
`<project-uuid>:<spec-id>`, so the project is cut off, and only the end of the spec slug is left.

Two projects that build a spec with the same ending at the same time get the same Job name, for
example `factory-aifactory-eterministic-word-fr`. The second dispatch fails with
`409 AlreadyExists`. AIFactory logs "Failed to start build from trusted plan", and the CLI reports
"Task creation outcome unknown". The live E2E run `mvr-20261125g` (#3882) hit this, because each E2E
journey builds the same fixture spec in a new project.

The `factory.io/job-id` label uses the same `_short` value. AIFactory's reaper guard for
reconstructed refs (`build_backend._reconstructed_job_is_ours`, #1606) compares that label, so it
cannot tell two colliding builds apart either.

The same code is vendored into AIFactory (`apps/backend/core/job_dispatch.py`) and TFactory
(`apps/backend/tools/runners/job_dispatch.py`, used by `agents/verify_dispatch.py`). TFactory
verify Jobs have the same collision.

## Proposed outcome

- Two different job ids always produce different Job names and different `factory.io/job-id`
  labels, even when their last 20 characters match.
- Names stay DNS-1123 safe, within the 63-character limit, and still end in a readable piece of
  the spec slug.
- The same job id always maps to the same name, so a reconstructed ref (#1606) still finds its
  Job.
- Factory, AIFactory and TFactory all ship the change. The vendor drift gate stays green.
- Live proof: two E2E journeys building the same fixture at the same time both dispatch.

## Affected users and systems

- `Factory/scripts/job_dispatch.py` (source of truth) and its tests.
- AIFactory and TFactory: re-vendored copies, `build_backend` (reconstructed refs and the reaper
  label guard) and TFactory `verify_dispatch`.
- Prod k3d `factory` namespace: build and verify Jobs created after the release.

## Constraints

- Deterministic and short. The result must not depend on time or randomness, because the
  reconstructed ref has to rebuild it later.
- Fail closed in the reaper. A row must never be failed, or have its verdict read, from a Job that
  belongs to another task.
- Re-vendor with the existing vendoring process, without hand edits to the copies.
- Minimal change: no new naming scheme beyond the suffix.

## Open questions

1. **Upgrade window.** A build that is running across the deploy, and whose `job_name` was never
   written to its row, will have its name reconstructed under the new rule. It then finds no Job
   (404), and the reaper fails it as "vanished". Options:
   - (a) Deploy only when no builds or verifies are in flight. This needs no code.
   - (b) For one release, have the reconstructed-ref path also try the legacy name before
     declaring "vanished".

   I propose (a), because rows normally store `job_name` at dispatch and only the #1606 leak path
   reconstructs it.
2. **Suffix shape.** The proposal is the last 13 characters of the slug, then `-`, then 6 hex
   characters of `sha256(job_id)`, which is 20 characters in total. Is 6 hex (about 16 million
   values) enough, or should it be 8?
