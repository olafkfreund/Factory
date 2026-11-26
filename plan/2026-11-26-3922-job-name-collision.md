---
status: draft
issue: 3922
spec: spec/2026-11-26-3922-job-name-collision.md
coders:
  1: codex   # small, exact naming logic and its self-test
  2: codex   # tricky reaper and sweeper ownership logic in AIFactory
  3: codex   # TFactory probe semantics and fake-client tests
reviewers:
  - codex    # checks each repo's diff against the spec
  - agy      # independent read of the ownership and fail-safe paths
---

# Plan: hash the full job id into Job names and prove ownership from it

## Approved decisions (from the spec)

- **`_short(job_id)`** builds the Job name suffix. It sanitises the id (lowercase, `[^a-z0-9-]` →
  `-`, strip `-`), takes the last 13 characters, strips `-` again, then appends `-` and the first
  12 hex characters of `sha256(job_id.encode())`. With no usable tail it returns the hash alone.
  - The result is deterministic, at most 26 characters, starts and ends with an alphanumeric
    character, and is a valid label value.
  - The longest name is 44 characters.
- **The full id goes on the Job object** as the annotation `factory.io/job-id-full`, through
  `job_annotations(job_id)`. It is not added to the pod template.
- **`job_owner(job)`** reads that annotation from a k8s client object or a dict. It never raises:
  anything missing or malformed returns `None`.
- **AIFactory reaper:**
  - It reads each Job once. It checks `job_owner(job) == row["job_id"]` on that same object for
    every row, stored or rebuilt. A mismatch or a missing annotation leaves the row alone.
  - `_reconstructed_job_is_ours` and its second GET are removed.
  - A 404 behaves as today.
- **AIFactory sweeper:**
  - A Job counts as owned when its name is in the owned-name set, or when `job_owner(job)` is an
    active row's job id.
  - Deletes carry a uid precondition. A 409 is skipped like a 404.
- **TFactory:**
  - The verify manifest carries the annotation.
  - `_probe_job(..., expected_job_id=...)` on the default probe returns `(True, True, False)` when
    the owner is different. It is always passed by the reaper loop. Injected `probe_fn` behaviour
    is unchanged.
- **Rollout:** quiesce. Stop submissions, drain until no `factory.io/kind` Job lacks a
  `Complete`/`Failed` condition, check there are no queued or running rows in AIFactory and
  TFactory, then sync both apps together.

## Steps

1. **Factory** `scripts/job_dispatch.py`, on this branch:
   - Add `import hashlib`. Replace `_short` (~line 195) with the spec's code, using the constants
     `_HASH_HEX = 12` and `_TAIL = 13`.
   - Add `JOB_ID_ANNOTATION`, `job_annotations` and `job_owner` next to `job_labels` (~line 296),
     as in the spec.
   - In `build_job_manifest` (~line 649), add `"annotations": job_annotations(spec.job_id)` to
     the Job `metadata`.
   - Add these self-test cases to the existing self-test (the `__main__` block used by
     `contracts.yml`):
     - two ids with the same 20-character tail give different names and labels;
     - the same id gives the same name every time;
     - `":::"` gives the bare 12-character hash;
     - names match DNS-1123 and are 63 characters or fewer for every entry in `SERVICES`;
     - the manifest carries the annotation;
     - `job_owner` handles a dict, an object, `None` metadata and non-mapping annotations.

   Verify: `python3 scripts/job_dispatch.py` exits 0, and
   `python3 scripts/ratchet_lint.py --base origin/main --package .` passes (both ruff and mypy).

   Traps:
   - The file is vendored byte-identical, so it must not import anything outside the stdlib or
     anything repo-specific.
   - Keep the `_short` name, because both forks call it.

2. **AIFactory** (new branch `fix/3922-job-name-collision` from `origin/dev`, worktree under the
   scratchpad):
   - Copy `Factory/scripts/job_dispatch.py` byte-identical to `apps/backend/core/job_dispatch.py`.
   - In `apps/web-server/server/services/build_backend.py`:
     - Add `_read_job(batch, namespace, job_name) -> tuple[str, Any | None]`, which does the single
       `read_namespaced_job` and returns `("gone", None)` on a 404, `("running", None)` on any other
       error (logged as today), or `(outcome, job)`. `_job_outcome` (~line 2110) becomes
       `return (await _read_job(...))[0]`, so `job_gone` (~line 1732) keeps comparing a string and
       is still true only on a 404.
     - In `_resolve_row_ref` (~line 1860), use `_read_job`. When `job is not None`, require
       `job_owner(job) == row["job_id"]` for stored and reconstructed refs alike; on a mismatch, log
       with `sanitize_log` that the Job belongs to another task and return `None`. When `job is
       None` (404 or read error), keep today's handling unchanged: grace for a reconstructed `gone`,
       "running" for a read error. Call `_repair_worker_ref` for a reconstructed ref only after the
       owner check passes.
     - Remove `_reconstructed_job_is_ours`, and `_job_id_label` if nothing else calls it.
     - In `sweep_orphan_jobs` (~line 1974), build `owned_ids = {row["job_id"] for row in rows}`
       next to the owned names. Pass it to `_sweep_candidates` (~line 290), which skips a Job whose
       name is owned or whose `job_owner(job)` is in `owned_ids`, skips a Job with no
       `metadata.uid`, and returns `(name, uid)` pairs for both the unfinished-past-grace path and
       the finished-beyond-cap path. Sort finished Jobs on `(time, name)` only.
     - Delete with `batch.delete_namespaced_job(name, namespace,
       body=client.V1DeleteOptions(preconditions=client.V1Preconditions(uid=uid)),
       propagation_policy="Background")`. Import `client` lazily from `kubernetes_asyncio`, as
       `_batch_api` (~line 1533) does.
     - On a 409 (the precondition failed: the Job was replaced), log it and `continue` without
       adding the Job to `swept`. A 404 keeps today's behaviour.
     - Update the "last 20 characters" comments.
   - Tests (`apps/web-server/tests/`, next to the existing `build_backend` reaper and sweeper
     tests). Existing Job fixtures gain the annotation and a `metadata.uid`.
     - `job_gone` is true only on a 404, whatever the owner.
     - A reconstructed row reads the Job exactly once (assert one `read_namespaced_job` call).
     - The reaper leaves a row alone on a mismatched or unstamped Job, for both stored and
       reconstructed refs, and applies the verdict on a matching Job.
     - On a non-404 read error, the row is treated as running, with no ownership warning.
     - The sweeper keeps an id-owned Job, deletes with the uid precondition on both paths, skips a
       Job without a uid, and on a 409 skips that Job and moves on to the next.

   Verify:
   - `python3 apps/backend/core/job_dispatch.py` (the vendored self-test) exits 0.
   - `cmp apps/backend/core/job_dispatch.py <Factory worktree>/scripts/job_dispatch.py` reports no
     difference.
   - `cd apps/web-server && ../backend/.venv/bin/pytest -q tests -k "build_backend or reap or sweep" -p no:cacheprovider`
     shows no new failures against a clean `origin/dev` run.

   Traps:
   - The local venv may lack pytest-asyncio, so rely on CI for the async tests.
   - Never log an id without `sanitize_log`.
   - `V1DeleteOptions` is not used in this file yet, so follow the lazy `client` import from
     `_batch_api`.

3. **TFactory** (new branch `fix/3922-job-name-collision` from `origin/dev`):
   - Copy the Factory file byte-identical to `apps/backend/tools/runners/job_dispatch.py`.
   - In `apps/backend/agents/verify_dispatch.py`:
     - In `build_verify_job_manifest` (starts ~line 700), in the label block (~line 903), add
       `manifest["metadata"].setdefault("annotations", {}).update(job_dispatch.job_annotations(cfg.job_id))`.
     - Add `*, expected_job_id: str | None = None` to `_probe_job` (~line 1533). On the default
       probe only, after a successful `read_namespaced_job`, if `expected_job_id` is set and
       `job_dispatch.job_owner(job) != expected_job_id`, log it (sanitized) and return
       `(True, True, False)`. A 404 still returns `(False, False, False)`. When an injected
       `probe_fn` is given, call it exactly as today with `(namespace, job_name)` and keep both
       tuple shapes.
     - The reaper loop (~line 1708) always passes `expected_job_id=job_id`.
     - Update the `_short` wrapper docstring (~line 524) to describe the hashed suffix.
   - Tests, on the default probe with a fake k8s client:
     - a matching terminal Job is reconciled;
     - a mismatched or unstamped Job is left alone;
     - a 404 is reaped;
     - a non-404 error is left alone.

     Existing tests that inject `probe_fn` stay unchanged.

   Verify:
   - `python3 apps/backend/tools/runners/job_dispatch.py` (the vendored self-test) exits 0.
   - `cmp` against the Factory copy reports no difference.
   - `cd apps/backend && .venv/bin/pytest -q tests -k verify_dispatch -p no:cacheprovider` shows no
     new failures against a clean `origin/dev` run. Use the repo's documented test runner if this
     command does not match it.

   Traps:
   - TFactory's drift gate compares the vendored copy against Factory `main`, so don't edit the
     copy by hand.

4. **Lead only** (not part of any handoff):
   - Review each diff against this plan.
   - Merge order (the drift gates compare against Factory `main`):
     1. Merge the Factory PR to `main` after CI passes.
     2. Open the AIFactory and TFactory PRs to `dev`, or rerun their CI, and merge each with
        `--match-head-commit` after CI passes.
   - Release AIFactory and TFactory (their normal release PRs to `main`), but don't sync them on
     prod yet.
   - Cutover:
     1. Post on the agent bus.
     2. **Hold** submissions: no E2E campaign, no CFactory card runs, and no task starts from a
        portal or the CLI.
     3. **Drain:** in the `factory` namespace, every Job labelled `factory.io/kind` has a condition
        `Complete=True` or `Failed=True`. Check this with a `kubectl -o json` query.
     4. **Empty queues:** AIFactory has no `queued` or `running` build rows, and TFactory has no
        queued or in-flight verify rows.

        Steps 3 and 4 are hard gates: if either fails, wait and don't sync.
     5. Sync both Argo apps.
     6. Wait until both `/api/health` endpoints report the new versions.
     7. **Resume** submissions.
     8. Run two P1 journeys at the same time and check that neither gets a 409.
   - Leftover legacy Job found after the cutover (an unstamped Job in the `factory` namespace):
     - Check whether a live row still points at it.
     - If no row does, delete it by hand.
     - If a row does, fail that row from its Job status by hand, then delete the Job.
     - Don't wait for the sweeper, which may delete the Job under its usual grace or retention
       rules once nothing owns it by name.

## Tests

- Step 1: the self-test passes and the ratchets pass.
- Steps 2 and 3: the targeted pytest runs pass, with no new failures against the dev baseline,
  and CI is green.
- Live: two P1 journeys started together both dispatch.

## Rollback

1. Revert the Factory PR first, because the drift gates compare the copies against Factory `main`.
2. Revert the AIFactory and TFactory PRs.
3. Release patches for AIFactory and TFactory.
4. Cut over with the same hold, drain, empty-queue, sync, health-check and resume sequence as in
   step 4. Both rollback versions must report healthy before submissions resume.

The drain is what makes the rollback safe:

- The old reaper trusts a stored name without checking the full id.
- A rebuilt ref uses the reverted naming rule, so it would miss a Job created under the new rule.

With no Jobs or rows in flight at the cutover, neither case can happen.
