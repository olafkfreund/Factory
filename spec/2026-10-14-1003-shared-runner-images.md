---
status: draft
issue: 1003
intent: intent/2026-10-14-1003-shared-runner-images.md
---

# Spec: PFactory runs TFactory's six runner images

The approver chose option (a): TFactory stays the single owner. They also
pre-approved merging this task's PRs once green.

## What was measured (2026-10-14)

- **The Dockerfiles.** All six `docker/pfactory-runner-*/Dockerfile` are
  byte-identical to `docker/tfactory-runner-*/Dockerfile` once the repo name
  is normalised. That includes the labels: 0 differing lines for each of
  cloud, cypress, jest, playwright, pytest and vitest. Each directory holds
  only the Dockerfile.
- **How PFactory names the images.** It uses bare `pfactory-runner-<x>:latest`
  tags, and `tools/runners/docker_runner.py::resolve_runner_image` qualifies
  them as `ghcr.io/olafkfreund/pfactory-runner-<x>`. Its
  `runner-images.yml` publishes and cosign-signs those images on main. That
  workflow says of itself that its steps were "copied" from TFactory's.
- **Kyverno.** `verify-factory-image-signatures` verifies
  `ghcr.io/olafkfreund/tfactory-runner-*` and `factory-runner-*`, and
  `require-first-party-signature-coverage` accepts the same two prefixes.
  **`pfactory-runner-*` is in neither.** So the switch needs no policy change,
  and it moves PFactory onto images whose signatures are already verified at
  admission.
- **References.** 221 occurrences of `pfactory-runner-` across 45 files: code,
  tests, framework descriptors, guides, CI, and historical records.

## Design

1. **Rename every live reference** in PFactory from
   `pfactory-runner-<x>` to `tfactory-runner-<x>`, for the six runners only:
   - code, tests, `frameworks/*/descriptor.yaml`, `.env.example`,
     guides and docs, `.claude/skills`, `scripts/demo`;
   - in `docker_runner.py`, `_RUNNER_PREFIX` becomes `"tfactory-runner-"`,
     so bare tags still resolve to GHCR;
   - with `PFACTORY_RUNNER_REGISTRY=""`, the local-daemon path keeps working
     against a locally built `tfactory-runner-*`.
   - **Not touched** (they are history): `CHANGELOG.md`, `.agent-os/specs/`
     and `intent/`.
   - A literal rename is chosen over aliasing inside the resolver because a
     grep for the image name then finds every consumer. That is the property
     the issue says was missing.
2. **Delete PFactory's copies:** `docker/pfactory-runner-*/` (6 directories),
   `.github/workflows/runner-images.yml`, and any test that only exists to
   check that workflow (`tests/test_runner_images_publish.py`).
   `image-build.yml` gets its references updated or removed.
3. **The `SECURITY_REFRESH` cache-bust and its guard test** already live in
   TFactory for the surviving copy, which TFactory's `runner-images.yml`
   builds. Nothing moves.
4. **Rollout in two PRs:**
   - **PR 1: vitest only.** Rename the vitest references. Keep PFactory's
     vitest Dockerfile until the end of PR 2.
     Verify: a PFactory vitest lane pulls
     `ghcr.io/olafkfreund/tfactory-runner-vitest`, Kyverno admits it, and it
     runs.
   - **PR 2: the other five, and all six deletions.**
   - Old `ghcr.io/olafkfreund/pfactory-runner-*` packages stay in GHCR, so an
     old PFactory release can still pull them. Deleting the packages is a
     separate, later decision.

## Alternatives rejected

- **(b) A new `factory-runners` repo.** The approver chose (a): it needs no
  new repo, CI, signing setup or policy change.
- **Aliasing in `resolve_runner_image`** (map `pfactory-runner-x` to
  `tfactory-runner-x`). One line, but the names in code and descriptors would
  then point at images that no longer exist, so a grep misleads. It would
  also only cover callers that go through the resolver.
- **A drift gate between the two Dockerfile sets.** It would keep the
  duplication and police it. Deleting one copy removes the problem.

## Risks

- **A PFactory caller that bypasses the resolver** with a hard-coded
  `ghcr.io/.../pfactory-runner-*` keeps pulling the old, now frozen image.
  Mitigated because the rename is global: after it, `git grep pfactory-runner-`
  must hit only history files, and that is checked in the plan.
- **TFactory image changes now reach PFactory unreviewed by PFactory.** This
  is intended (one source), but a TFactory-only tweak to these six would
  ship to PFactory too. TFactory's runner Dockerfile headers get a note.
- **A host with a stale local `tfactory-runner-*:latest`** under
  `PFACTORY_RUNNER_REGISTRY=""` runs whatever it last built. This is the
  existing escape-hatch behaviour, unchanged.
- **Image tag skew:** PFactory follows TFactory's `:latest`, which is
  published on TFactory's `main`. A PFactory dev lane gets TFactory's latest
  released runner, which is the same contract PFactory had with its own
  images.

## Verification

- PFactory CI green on both PRs, including the updated tests
  (`test_docker_runner`, `test_framework_registry`, `test_lane_dispatch`,
  `test_cloud_frameworks` and the `lang_typescript` tests).
- `git grep -nE 'pfactory-runner-(cloud|cypress|jest|playwright|pytest|vitest)'`
  in PFactory hits only `CHANGELOG.md`, `.agent-os/` and `intent/`.
- **Live, after PR 1 deploys:** a PFactory run that uses vitest starts a Job
  on `ghcr.io/olafkfreund/tfactory-runner-vitest`. Its Kyverno
  `verify-images` annotation says `pass`, and the lane completes. Repeat for
  one Python lane (pytest) after PR 2.
