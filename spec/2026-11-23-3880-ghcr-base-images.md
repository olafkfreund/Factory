---
status: approved
issue: 3880
intent: intent/2026-11-23-3880-ghcr-base-images.md
---

# Spec: GHCR-hosted base images and an image mirror

## Design (per portal: AIFactory, PFactory, TFactory)

**`docker/base.Dockerfile`**
- One named target per Chainguard stage that runs `apk add` in the main Dockerfile:
  - AIFactory: `py-build`, `runtime`, `gateway`;
  - PFactory and TFactory: `runtime`.
- Each target is `FROM cgr.dev/chainguard/python:latest-dev@sha256:…` (the digest now in the Dockerfile), plus **only the `apk add` package installs** moved out of that stage. Everything else stays in the main Dockerfile.
- Version pins and build args are kept exactly.
- If an apk install is interleaved with other steps and can't move without reordering, leave that one in place and record it in the PR. Moving it is preferred.

**`.github/workflows/base-image.yml`**
- Triggers:
  - push to dev touching `docker/base.Dockerfile`;
  - weekly cron;
  - `workflow_dispatch`.
- Builds each target for the same platforms as `image-build.yml`.
- Pushes `ghcr.io/olafkfreund/<repo>-base:<target>-<yyyymmdd>-<shortsha>`.
- Reads each digest, rewrites the matching `FROM` lines in `Dockerfile` to `ghcr.io/olafkfreund/<repo>-base:<target>-…@sha256:<digest>`, and opens a PR to dev with `gh pr create` (the repo's token). Only when a digest changed.
- Permissions: `packages: write`, `contents: write`, `pull-requests: write`.
- The packages are public, like the app images. If the app images are private, match their visibility.

**`Dockerfile`**
- The stages start `FROM ghcr.io/olafkfreund/<repo>-base:<target>-…@sha256:…`.
- The moved `apk add` lines are gone.
- The first PR seeds the digests by running the workflow once with `workflow_dispatch` on the PR branch.
- Normal CI (`image-build`, the docker P0 check, deploy) then never contacts cgr.dev or apk.cgr.dev, **except build-nix**: check it, and if it pulls Chainguard or apk too, give it its own base target.

**Dependabot**
- The docker ecosystem also watches `docker/base.Dockerfile`. It already watches `/`; add the docker directory if it is separate.
- A Chainguard digest bump then triggers a base rebuild on merge, which opens the FROM-bump PR.

**AIFactory `base-image-pin-liveness.yml`**
- Point it at the base Dockerfile's Chainguard pins, and also check that the GHCR base digests resolve.

## factory-gitops
- A `mirror-images.yml` workflow (weekly plus dispatch) copies each pinned `cgr.dev/chainguard/{minio-client,minio}@sha256` to `ghcr.io/olafkfreund/mirror/<name>@sha256`, by digest, with `crane copy` or `skopeo`.
- The manifests reference the mirror. The digest stays identical, because a copy keeps it.
- Update the two backup test workflows that grep for the image.
- `image-pin-freshness.yml` keeps working.

## Verification
- **Per portal:** the PR's CI builds with cgr.dev unreachable. Check this by inspecting the build log: no cgr.dev or apk.cgr.dev fetch outside base-image.yml.
- **Image smoke test:** the built image runs `python -c 'import ...'` for the moved packages; xmlsec is the key one for AIFactory.
- **Runtime:** the image runs as before. Release, deploy and the pod checks pass.
- **Gitops:** the backup CronJobs' images resolve from GHCR, and the backup tests pass.
