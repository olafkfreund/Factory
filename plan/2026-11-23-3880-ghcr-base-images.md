---
status: approved
issue: 3880
spec: spec/2026-11-23-3880-ghcr-base-images.md
coders:
  1: codex   # AIFactory: three bases, liveness workflow, build-nix check
  2: codex   # PFactory
  3: codex   # TFactory
  4: codex   # factory-gitops mirror
reviewers:
  - agy
---

# Plan: GHCR base images (#3880)

The spec decisions are binding. Each step is its own PR in its own repo, from dev, or from main for gitops. The lead merges, then runs `workflow_dispatch` for the base workflow, merges the digest-bump PR, and releases.

## Steps
1. AIFactory.
2. PFactory.
3. TFactory.
4. factory-gitops.

For each step:
- **Verify:** `docker build` of every base target and the main image locally, if docker is available; actionlint on the new workflows; the repo's tests or lint for touched files.
- **Traps:**
  - keep apk version pins exactly;
  - multi-arch parity with `image-build.yml`;
  - don't break the docker P0 acceptance test, which builds the Dockerfile;
  - a seeding chicken-and-egg (the first PR needs a base digest): until the workflow has run once, use the Chainguard image in a build ARG default, or push the base from the PR branch with dispatch.

## Rollback
Revert the PR. The Dockerfiles go back to the cgr.dev FROM lines.
