---
status: approved
issue: 2133
intent: intent/2026-11-18-2133-job-ttl-after-finished.md
---

# Spec: configurable finished-Job retention

## Design

1. `build_backend.job_ttl_seconds(default: int = 300) -> int`: reads
   `AIFACTORY_JOB_TTL_SECONDS`. Unset or blank returns `default`. A non-integer or
   value below 1 logs a warning and returns `default`. A value above
   `JOB_TTL_MAX_SECONDS = 3600` logs a warning and returns 3600.
2. The three `JobSpec(...)` sites (build, spec, agent) pass
   `ttl_seconds=job_ttl_seconds()`. `ttlSecondsAfterFinished` applies to
   succeeded and failed Jobs alike, so failed pods are kept for the same TTL.
   No explicit delete runs after completion today, so nothing is skipped; the
   stop, deadline and rollback deletes stay (they act on a live Job).
3. `sweep_orphan_jobs`: a Job is finished when a condition of type `Complete` or
   `Failed` has status `True` (covers deadline failures), or `status.succeeded`
   / `status.failed` is non-zero. Finish time is that condition's
   `lastTransitionTime`, else `status.completionTime`, else creation time.
   Finished Jobs are never age-swept (the Job controller removes them at the
   TTL; today's creation-age rule would delete a long build seconds after it
   finishes, when the sweep is live). Finished Jobs beyond the newest
   (by finish time) `AIFACTORY_JOB_RETAIN_MAX` (default 20, clamped to >= 1; invalid falls back
   to 20) are deleted oldest first, honouring `sweep_dry_run()` and the owned
   set. The cap overrides the TTL (it is the disk guard, so it may delete a Job
   before its TTL when more than N finished Jobs exist). Unfinished orphans keep
   the existing 600 s grace rule.
4. Documented in the AIFactory env reference / CHANGELOG, recommended 600.
5. factory-gitops PR (after release and deploy): `AIFACTORY_JOB_TTL_SECONDS: "600"`
   on the control plane Deployment in `apps/aifactory`. Kyverno and the sandbox
   NetworkPolicy select on `factory.io/kind: task` labels, so a longer-lived pod
   needs no policy change (verify by reading, no apply).

## Alternatives rejected

- Per-kind env vars: more surface, no stated need.
- Raising the 300 s default: changes behaviour for every deployment.
- Setting the TTL inside `build_job_manifest`: the manifest builder is shared
  with other services (hub copy); the policy belongs in AIFactory's builders.
- Per-kind count cap: kind is not in Job labels or names.
- Skipping the gate sandbox delete: many Jobs per task, disk cost, not asked.

## Risks

More finished pods on p620 for up to the TTL: bounded by the 3600 s clamp and
the count cap; pods hold no PVC data. If the sweep stays in dry-run (default),
only the TTL bounds the count; the cap then logs what it would delete.
Mitigation: recommended value 600 only.

## Verification

Unit tests: env unset gives 300 on all three manifests; env set applies to all
three; invalid and over-max values; sweep skips finished Jobs for age, deletes
only the longest-finished beyond the cap, a long-running Job that just finished is
kept, terminal `Failed` condition with zero counters counts as finished, a 20-minute
build finished 1 s ago is not age-swept, respects dry-run and owned rows. Live, after
gitops sync: read-only `kubectl get pods` shows a finished Job pod within the TTL.
