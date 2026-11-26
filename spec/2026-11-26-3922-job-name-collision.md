---
status: draft
issue: 3922
intent: intent/2026-11-26-3922-job-name-collision.md
---

# Spec: hash the full job id into Job names and prove ownership from it

## Design

### 1. Factory `scripts/job_dispatch.py` (the source of truth; it is vendored byte-identical)

`_short` (~line 195) becomes:

```python
_HASH_HEX = 12  # 48 bits; ~2e-9 collision odds among 1,000 ids sharing a tail (#3922)
_TAIL = 13


def _short(job_id: str) -> str:
    """k8s-safe suffix: readable tail + hash of the FULL id (DNS-1123, <=26 chars).

    The tail alone collided across projects building the same spec slug (#3922).
    """
    digest = hashlib.sha256(job_id.encode()).hexdigest()[:_HASH_HEX]
    s = re.sub(r"[^a-z0-9-]", "-", job_id.lower()).strip("-")
    tail = s[-_TAIL:].strip("-")
    return f"{tail}-{digest}" if tail else digest
```

- The function is deterministic, so `_reconstructed_ref` and `verify_job_name` still rebuild the
  same name.
- The result starts and ends with an alphanumeric character, is at most 26 characters long, and
  the longest name (`factory-aifactory-`, 18 characters, plus 26) is 44, well under
  `_DNS_LABEL_MAX` (63). It is also a valid label value. Add `import hashlib`.

New, next to `job_labels`:

```python
JOB_ID_ANNOTATION = "factory.io/job-id-full"


def job_annotations(job_id: str) -> dict[str, str]:
    """Annotations for the Job OBJECT: the full id, which a label cannot hold (#3922)."""
    return {JOB_ID_ANNOTATION: job_id}


def job_owner(job: Any) -> str | None:
    """The full job id stamped on a fetched Job (k8s client object or dict), else None.

    Never raises: missing/None metadata or annotations, a non-mapping annotations
    value or a non-string id all return None, so every caller fails closed.
    """
    meta = job.get("metadata") if isinstance(job, dict) else getattr(job, "metadata", None)
    ann = meta.get("annotations") if isinstance(meta, dict) else getattr(meta, "annotations", None)
    value = ann.get(JOB_ID_ANNOTATION) if isinstance(ann, dict) else None
    return value if isinstance(value, str) and value else None
```

`build_job_manifest` (~line 649) adds `"annotations": job_annotations(spec.job_id)` to the Job's
`metadata`, but not to the pod template.

The self-test (`python3 scripts/job_dispatch.py`, run by `contracts.yml`) gains these checks:

- two ids with the same 20-character tail give different names and labels;
- the same id gives the same name every time;
- an id with no usable slug (e.g. `":::"`) gives the bare hash;
- every name matches DNS-1123 and is 63 characters or shorter;
- the manifest carries the annotation, and `job_owner` reads it back from both a dict and an
  object.

### 2. AIFactory (`apps/backend/core/job_dispatch.py` re-vendored; `build_backend.py`)

- **The reaper reads each Job once.**
  - Split `_job_outcome` (~line 2110) so the reaper gets the outcome and the Job object from a
    single `read_namespaced_job`.
  - `_resolve_row_ref` (~line 1860) then checks `job_owner(job) == row["job_id"]` on that same
    object whenever the Job exists, for every row, whether its ref was stored or rebuilt. A
    mismatch or a missing annotation returns `None`, and the row is left for a later tick.
  - `_reconstructed_job_is_ours` and its second GET are removed, and so is `_job_id_label` if
    nothing else calls it.
  - A 404 behaves as today: the dispatch grace, then "vanished".
- **The sweeper proves ownership.**
  - `sweep_orphan_jobs` (~line 1974) counts a listed Job as owned when its name is in the current
    owned-name set, which spec Jobs need, or when `job_owner(job)` is the job id of an active row.
  - Each delete passes `V1DeleteOptions(preconditions=V1Preconditions(uid=job.metadata.uid))`, so a
    replacement Job created after the listing is never deleted. A 409 from a failed precondition
    is skipped, like a 404.
  - `_sweep_candidates` returns name and uid pairs instead of bare names.
- `job_gone` stays a presence-only 404 check on the rebuilt name.
- Update the comments that say "`_short` keeps only the last 20 characters".

### 3. TFactory (`apps/backend/tools/runners/job_dispatch.py` re-vendored; `agents/verify_dispatch.py`)

- In `build_verify_job_manifest` (~line 903), next to the labels, add
  `manifest["metadata"].setdefault("annotations", {}).update(job_dispatch.job_annotations(cfg.job_id))`.
- `_probe_job` gains a keyword-only `expected_job_id: str | None = None`.
  - On the default probe, when `expected_job_id` is set, the Job exists, and
    `job_dispatch.job_owner(job)` is not `expected_job_id`, the probe returns
    `(True, True, False)`. That means "present and active", so `reap_if_orphaned` leaves the row
    alone, the same fail-safe as a probe error.
  - A 404 still returns `(False, False, False)`.
  - An injected `probe_fn` keeps its `(namespace, job_name)` call and both tuple shapes, and
    ignores the new argument.
- The reaper loop (~line 1704) always passes `expected_job_id=job_id`, whether the name was stored
  or rebuilt. A 409 at create time can leave a queued row pointing at another task's Job.
- Update the stale "<=20 chars" docstring on TFactory's `_short` wrapper (~line 524).

### 4. Rollout: quiesce (intent option a)

Release Factory first. Then release AIFactory and TFactory together, both carrying the
re-vendored file. There is no admission switch, and this is an owner-only system, so quiescing
means:

1. **Stop submissions.** No E2E campaign, no CFactory card runs, and no task starts from a portal
   or the CLI, until both services report the new version.
2. **Drain.** No Job in the `factory` namespace with the label `factory.io/kind` lacks a `Complete`
   or `Failed` condition. Checking `status.active` alone isn't enough, because a just-created Job
   may not have it set yet.
3. **Empty queues.** No `queued` or `running` build rows in AIFactory, and no queued or in-flight
   verify rows in TFactory.
4. **Cut over.** Sync both Argo apps, wait for both health checks to report the new versions, then
   resume.

Rollback follows the same steps. If a Job with an old-style name is found after the cutover anyway,
it fails safe:

- the ownership checks find no annotation, so they leave it and its row alone;
- the sweeper doesn't count it as owned.

It is then deleted by hand, after checking it.

## Alternatives rejected

- **A wider tail with no hash:** two ids can still share any tail.
- **The full id in a label:** label values are limited to 63 characters and `[A-Za-z0-9._-]`, and
  the id contains `:` and is longer than that.
- **Reading `AIFACTORY_TASK_ID` / `JOB_ID` from the container env** as the ownership proof: it
  works without a new annotation, but every consumer would have to dig through
  `spec.template.spec.containers[*].env`, and the field is not stable across the two forks'
  manifests. One annotation and one helper in the shared file are simpler.
- **A legacy-name fallback (intent option b):** the owner chose to quiesce instead.

## Risks

- **A Job created under the old name** (for example, if the quiesce check is skipped) is no longer
  found under its rebuilt name:
  - AIFactory fails the row as vanished after the dispatch grace.
  - The sweeper treats the Job as unowned and may delete it after ten minutes.
  - TFactory marks the verify `stuck`.

  The quiesce check is the mitigation. If one slips through, the ownership checks fail safe (see
  Rollout). This applies on prod, in the k3d `factory` namespace.
- **A hash collision:** about 2 in a billion for 1,000 ids sharing a tail. The ownership check on
  the full-id annotation still prevents a wrong verdict.
- **Vendor drift:** the copies must be byte-identical. The existing drift gates in AIFactory and
  TFactory catch a mismatch.

## Verification

- `python3 scripts/job_dispatch.py` (the self-test) passes in Factory, and the vendored copies
  pass in AIFactory and TFactory.
- AIFactory:
  - The reaper reads each Job once. It leaves the row alone when the annotation holds another id or
    is missing, whether the ref was stored or rebuilt, and applies the verdict when the id matches.
  - The sweeper does not delete a Job owned by an active row's id, and each delete carries the
    listed uid.
  - Existing `build_backend` tests keep passing, with Job fixtures that carry the annotation.
- TFactory, using a fake Kubernetes client on the default probe:
  - a matching terminal Job is reconciled;
  - a mismatched or unstamped Job is left alone;
  - a 404 is reaped as today;
  - a non-404 error is left alone.

  Tests that inject `probe_fn` keep passing unchanged.
- CI is green in all three repos.
- Live: after the quiesced deploy, two P1 E2E journeys start at the same time and both dispatch
  without a 409.
