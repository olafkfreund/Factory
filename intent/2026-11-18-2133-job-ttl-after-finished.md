---
status: approved
issue: 2133
author: olafkfreund
---

# Intent: keep finished AIFactory Job pods inspectable (AIFactory#2133)

## Problem

Found while verifying AIFactory#2126: after a build, spec, review or
apply-correction Job finishes, its pod is gone before anyone can read its
ServiceAccount, exit status or logs. Investigation (dev aa3fd398):

- `ttlSecondsAfterFinished` comes from `JobSpec.ttl_seconds`
  (`apps/backend/core/job_dispatch.py:180`, applied at `:656`). None of the three
  builders (`build_backend.py:956`, `spec_job_backend.py:83`,
  `agent_job_backend.py:76`, which serves review and apply-correction) sets it,
  so every Job gets a fixed 300 s and there is no knob.
- No code deletes these Jobs after a normal completion. Explicit deletes exist
  only for stop (`delete_job`, called from `agent_kubejob.py:1224`), polling
  deadline (`spec_job_backend.py:292`), dispatch rollback
  (`build_backend.py:1512`, `agent_job_backend.py:128`) and the orphan sweep
  (`build_backend.py:1810`: no active owner row, older than 600 s, dry-run by
  default). The reaper only reads the outcome. Codex review point: the sweep
  measures age from Job creation and ignores completion, so with
  `AIFACTORY_JOB_SWEEP_DRY_RUN=false` a build that ran over 10 minutes is deleted
  at the first reconcile tick after it finishes. That is the likely cause of
  "gone within seconds"; it is live-unverified (the setting is not read here).
- The gate sandbox is the one path that removes its Job within seconds
  (`kube_sandbox.py:498`, 120 s TTL). It is not one of the four kinds and runs
  many times per task, so it is out of scope.

## Proposed outcome

- One env var, `AIFACTORY_JOB_TTL_SECONDS`, sets the TTL of build, spec, review
  and apply-correction Jobs, failed ones included. Unset keeps today's 300 s.
  Recommended value 600, hard maximum 3600 (clamped, logged).
- The orphan sweep does not remove a finished Job on age; it keeps at most
  `AIFACTORY_JOB_RETAIN_MAX` (default 20) finished Jobs and deletes the one
  finished longest ago above that. The cap deliberately overrides the TTL: it is
  the disk guard.
- factory-gitops sets the value to 600 in a separate PR after release.

## Affected users and systems

Control plane (`apps/web-server`), the shared `core/job_dispatch.py`, p620 k3d
cluster (/ is at 82% with DiskPressure during rollouts, owner-only, not touched).

## Constraints

- Unset env must leave every Job spec byte-identical to today.
- Retained pods keep logs and the container writable layer, not the workspace
  PVC; retention must stay bounded in time and count.
- No live-cluster change in the AIFactory PR; no secrets involved.

## Open questions

None. Decision (owner delegation 2026-11-18): the recommended option above.
The count cap is per sweep selector (all `factory.io/kind=task` Jobs), not per
kind, because Job names and labels do not carry the kind.
