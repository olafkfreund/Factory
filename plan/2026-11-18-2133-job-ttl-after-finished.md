---
status: approved
issue: 2133
spec: spec/2026-11-18-2133-job-ttl-after-finished.md
coders:
  2: codex   # contained, tricky sweep logic with a fake batch API
  3: codex   # contained test additions once steps 1-2 exist
reviewers:
  - codex    # independent read of the final diff against this plan
---

# Plan: configurable finished-Job retention (AIFactory#2133)

Repo olafkfreund/AIFactory, branch `fix/2133-job-ttl-after-finished` off `dev`.
Approved decisions (spec): `AIFACTORY_JOB_TTL_SECONDS`, unset keeps 300 s,
invalid or < 1 falls back to the default with a warning, > 3600 clamps to 3600
with a warning; one helper `build_backend.job_ttl_seconds()` used by the three
builders (build, spec, agent = review + apply-correction); no explicit delete
runs after normal completion today, so TTL is already the only GC and the
stop/deadline/rollback deletes stay; the orphan sweep never age-sweeps finished
Jobs and deletes the longest-finished Jobs (finish time per spec: terminal condition, then completionTime, then creation) above `AIFACTORY_JOB_RETAIN_MAX`
(default 20, min 1, invalid -> 20), honouring dry-run and the owned set; count cap
overrides the TTL (disk guard) and is per sweep selector, not per kind. The gate sandbox (kube_sandbox) is out of
scope. factory-gitops env wiring is a separate PR after release and deploy.

## Steps

1. `apps/web-server/server/services/build_backend.py` near `_ENV_DEADLINE`
   (:171) and `_job_service_account` (:211): add `_ENV_JOB_TTL`,
   `JOB_TTL_MAX_SECONDS = 3600`, `_DEFAULT_JOB_TTL_SECONDS = 300`,
   `job_ttl_seconds()`; pass `ttl_seconds=job_ttl_seconds()` in the `JobSpec(`
   at :956, and the same in `spec_job_backend.py:83` and `agent_job_backend.py:76`
   (call as `build_backend.job_ttl_seconds()`). Check: `pytest tests/test_spec_job_backend.py apps/web-server/tests/test_agent_job_backend.py`.
   Traps: ruff "as" alias rule (use plain names); log via `sanitize_log`.
2. `build_backend.py` `sweep_orphan_jobs` (:1810): add `_ENV_JOB_RETAIN_MAX`,
   `_retain_max()`; classify finished by terminal condition `Complete`/`Failed` status True, or non-zero
   `status.succeeded`/`.failed`;
   finished Jobs skip the age/grace rule; collect finished, non-owned Jobs,
   sort by finish time, delete all but the newest N (dry-run: log and append
   only). Check: step 3 tests.
   Traps: keep 404-tolerant delete handling; keep `owned` check first.
3. Tests: `tests/test_kubejob_build_ownership.py` (sweep cases: finished not
   age-swept, cap deletes only oldest, dry-run deletes nothing, owned kept,
   cap env invalid, Failed condition with zero counters, long build just finished is kept
   and not age-swept, cap overrides TTL) and `tests/test_job_ttl.py` (new: helper unset/valid/invalid/
   clamp; manifests from the build, spec and agent builders carry the env TTL,
   unset gives 300). Check: `pytest tests/test_job_ttl.py tests/test_kubejob_build_ownership.py`.
4. `docs/docs/environment-reference.md` (near :293): rows for both vars;
   `CHANGELOG.md` `[Unreleased]` Added entry (#2133). Yours, not delegated.
5. Run repo lint (`ruff check`, `ruff format --check` per CI) and the touched
   test files; vendored hub files untouched.

## Tests

`pytest tests/test_job_ttl.py tests/test_kubejob_build_ownership.py
tests/test_spec_job_backend.py apps/web-server/tests/test_agent_job_backend.py
apps/web-server/tests/test_correction_job_backend.py` all pass; `ruff check` clean.

## Rollback

Revert the PR; unset env is byte-identical to today, so the env var can also
simply be removed from factory-gitops.
