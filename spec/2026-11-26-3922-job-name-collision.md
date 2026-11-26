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
  `_DNS_LABEL_MAX` (63). It is also a valid label value.

New, next to `job_labels`:

```python
JOB_ID_ANNOTATION = "factory.io/job-id-full"


def job_annotations(job_id: str) -> dict[str, str]:
    """Annotations for the Job OBJECT: the full id, which a label cannot hold (#3922)."""
    return {JOB_ID_ANNOTATION: job_id}


def job_owner(job: Any) -> str | None:
    """The full job id stamped on a fetched Job (k8s client object or dict), else None."""
```

`job_owner` reads `metadata.annotations[JOB_ID_ANNOTATION]` from either a client object
(attributes) or a dict, and returns `None` when it is missing.

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

- `_reconstructed_job_is_ours` (~line 1767) compares `job_owner(job) == job_id` instead of the
  shortened label. It still fails closed: a missing annotation, a mismatch or a read error each
  return False, and the row is left for a later tick. The docstring and the comments that say
  "`_short` keeps only the last 20 characters" are updated.
- `job_gone`, the reaper's reconstructed path and `sweep_orphan_jobs` keep rebuilding the name with
  `_reconstructed_ref`. The rule is deterministic and collision-resistant, so they need no other
  change. The sweeper keeps its name-based ownership set.

### 3. TFactory (`apps/backend/tools/runners/job_dispatch.py` re-vendored; `agents/verify_dispatch.py`)

- In `build_verify_manifest` (~line 903), next to the labels, add
  `manifest["metadata"].setdefault("annotations", {}).update(job_dispatch.job_annotations(cfg.job_id))`.
- `_probe_job` gains a keyword-only `expected_job_id: str | None = None`. When it is set, the Job
  exists, and `job_dispatch.job_owner(job)` is not `expected_job_id`, the probe returns
  `(True, True, False)`. That means "present and active", so `reap_if_orphaned` leaves the row
  alone, which is the same fail-safe as a probe error. An injected `probe_fn` ignores the
  parameter.
- The reaper loop (~line 1704) passes `expected_job_id=job_id` only when it rebuilt the name
  (`ref.get("job_name")` was empty).

### 4. Rollout: quiesce (intent option a)

Release Factory first. Then release AIFactory and TFactory, both carrying the re-vendored file.
Before syncing them on prod:

1. Make sure no E2E campaign is running.
2. Confirm there are no active Jobs:
   `kubectl -n factory get jobs -l factory.io/kind -o jsonpath='{.items[?(@.status.active)].metadata.name}'`
   must print nothing.
3. Confirm no `running` build or verify rows remain (the AIF `/api/tasks` running list and the
   TF in-flight list are empty).

Rollback follows the same steps.

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

  The quiesce check is the mitigation. It applies on prod, in the k3d `factory` namespace.
- **A hash collision:** about 2 in a billion for 1,000 ids sharing a tail. The ownership check on
  the full-id annotation still prevents a wrong verdict.
- **Vendor drift:** the copies must be byte-identical. The existing drift gates in AIFactory and
  TFactory catch a mismatch.

## Verification

- `python3 scripts/job_dispatch.py` (the self-test) passes in Factory, and the vendored copies
  pass in AIFactory and TFactory.
- AIFactory: a test where `_reconstructed_job_is_ours` returns False for a Job whose annotation
  holds another id, True for a matching one, and False when the annotation is missing. The
  existing `build_backend` reaper tests keep passing, with fixtures updated to carry the
  annotation.
- TFactory: a test where the reaper leaves a row alone when the rebuilt name's Job belongs to
  another id, and reaps it when the id matches and the Job is gone. Existing `verify_dispatch`
  tests keep passing.
- CI is green in all three repos.
- Live: after the quiesced deploy, two P1 E2E journeys start at the same time and both dispatch
  without a 409.
