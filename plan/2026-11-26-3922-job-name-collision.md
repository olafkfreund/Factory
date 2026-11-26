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
     - Split `_job_outcome` (~line 2110) so the reaper can get `(outcome, job)` from one read.
     - In `_resolve_row_ref` (~line 1860), check `job_owner(job) == row["job_id"]` on that object
       whenever the outcome is not `gone`, for stored and reconstructed refs alike. On a mismatch,
       return `None`. Keep the dispatch-grace handling for `gone`.
     - Remove `_reconstructed_job_is_ours`, and `_job_id_label` if it has no other caller.
     - In `sweep_orphan_jobs` (~line 1974), compute the owned job ids from the active rows. Have
       `_sweep_candidates` skip a Job whose `job_owner` is in that set, and return `(name, uid)`.
     - Delete with `V1DeleteOptions(preconditions=V1Preconditions(uid=uid))` and treat a 409 like
       a 404.
     - Update the "last 20 characters" comments.
   - Tests (`apps/web-server/tests/`, next to the existing `build_backend` reaper and sweeper
     tests):
     - the reaper leaves a row alone on a mismatched or unstamped Job, for both stored and
       reconstructed refs;
     - the reaper applies the verdict on a matching Job;
     - the sweeper keeps an id-owned Job;
     - the sweeper deletes with the uid precondition;
     - existing Job fixtures gain the annotation.

   Verify:
   - `cd apps/web-server && ../backend/.venv/bin/pytest -q tests -k "build_backend or reap or sweep" -p no:cacheprovider`
     passes, comparing against a clean `origin/dev` run for any failures that already exist.
   - The vendored-file drift check passes: `cmp` against the Factory copy.

   Traps:
   - The local venv may lack pytest-asyncio. Compare against the dev baseline, and rely on CI for
     async tests.
   - Don't log ids without `sanitize_log`.
   - The kubernetes client symbols are imported lazily in this file, so follow the existing pattern
     for `V1DeleteOptions`.

3. **TFactory** (new branch `fix/3922-job-name-collision` from `origin/dev`):
   - Copy the file byte-identical to `apps/backend/tools/runners/job_dispatch.py`.
   - In `apps/backend/agents/verify_dispatch.py`:
     - In `build_verify_job_manifest` (~line 903), add the annotation as the spec describes.
     - Give `_probe_job` (~line 1533) the keyword `expected_job_id` and the owner check on the
       default probe only.
     - The reaper loop (~line 1708) always passes `expected_job_id=job_id`.
     - Update the `_short` wrapper docstring (~line 524).
   - Tests: on the default probe with a fake k8s client:
     - a matching terminal Job is reconciled;
     - a mismatched or unstamped Job is left alone;
     - a 404 is reaped;
     - a non-404 error is left alone.

     Existing tests that inject `probe_fn` stay unchanged.

   Verify: `apps/backend/.venv/bin/pytest -q tests -k "verify_dispatch" -p no:cacheprovider`
   (or the repo's documented runner) passes against the dev baseline, and the vendored-file
   drift check passes.

   Traps:
   - TFactory's own drift gate compares against the Factory canonical, so copy the file and don't
     edit it by hand.
   - Keep both `probe_fn` tuple shapes.

4. **Lead only** (not part of any handoff):
   - review each diff;
   - open PRs: Factory to `main`, and AIFactory and TFactory to `dev`;
   - merge after CI with `--match-head-commit`;
   - release AIFactory and TFactory;
   - quiesce, as in the spec rollout steps 1 to 4, and post on the agent bus before syncing;
   - confirm both health versions;
   - run two P1 journeys at the same time and check that neither gets a 409.

## Tests

- Step 1: the self-test passes and the ratchets pass.
- Steps 2 and 3: the targeted pytest runs pass, with no new failures against the dev baseline,
  and CI is green.
- Live: two P1 journeys started together both dispatch.

## Rollback

Revert the AIFactory and TFactory PRs and release patches, quiescing first in the same way.
Revert the Factory PR so the canonical copy matches. Jobs created under the new names have
annotations, and the old code ignores them, so they reconcile under their stored refs. Rows with
rebuilt refs need the quiesce.
