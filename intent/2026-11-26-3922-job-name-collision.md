---
status: approved
issue: 3922
author: olafkfreund
---

# Intent: build Job names must not collide across projects

## Problem

`scripts/job_dispatch.py` names every build Job `factory-<service>-<_short(job_id)>`. `_short`
keeps only the last 20 characters of the job id. AIFactory's job id is
`<project-uuid>:<spec-id>`, so the project is cut off, and only the end of the spec slug is left.

Two projects that build a spec with the same ending get the same Job name. They don't have to
build at the same moment: a finished Job is kept for `ttlSecondsAfterFinished` (300 s by default),
so the second build also collides within that window. An example name is `factory-aifactory-eterministic-word-fr`. The second dispatch fails with
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

- Job ids whose last 20 characters match no longer share a Job name or a `factory.io/job-id`
  label. The suffix carries a deterministic hash of the full job id, wide enough that a collision
  is negligible at any realistic number of retained Jobs.
- Where a reaper or sweeper uses a Job's status, or deletes a Job, it proves ownership from the
  full job id on that same Job object, not from the shortened label. The full id is already in
  the Job spec as `AIFACTORY_TASK_ID` (AIFactory) and `JOB_ID` (TFactory).
- Names and labels stay DNS-1123 safe, within 63 characters, start and end with an alphanumeric
  character (including when the job id has no usable slug), and still carry a readable piece of
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

1. **Upgrade window.** Every path that rebuilds a name from a job id would compute the new name
   for a Job created under the old one:
   - AIFactory `job_gone` (rebuilds unconditionally);
   - AIFactory reaper (when the row has no name or namespace);
   - AIFactory orphan sweeper (its ownership set, so it can delete a live old Job after ten
     minutes when dry-run is off);
   - TFactory verify reaper (marks the verify `stuck` and can fail the spec).

   Options:
   - (a) Quiesce: pause build and verify dispatch, let in-flight Jobs finish and their rows reach
     a terminal state, then deploy. Rollback does the same.
   - (b) Keep a legacy-name fallback for one release on every path above, accepting a match only
     when the full job id on the Job object agrees.

   I propose (a): it needs no compatibility code, and the factories are idle between E2E runs.
2. **Suffix shape.** The proposal: the last 13 characters of the slug, `-`, then 12 hex characters
   of `sha256(job_id)`. That is at most 26 characters, so the longest name is 44, within 63. With
   no usable slug, the hash alone is used. Is a 12-hex hash, about 2 in a billion odds of a collision
   among 1,000 Jobs with the same tail, acceptable?
