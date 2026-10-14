---
status: approved
issue: 1003
spec: spec/2026-10-14-1003-shared-runner-images.md
---

# Plan: PFactory runs TFactory's six runner images

## Approved decisions (from the spec)

- TFactory stays the only owner of the six runners: cloud, cypress, jest,
  playwright, pytest and vitest. PFactory renames every **live** reference
  from `pfactory-runner-<x>` to `tfactory-runner-<x>`, and deletes its copies
  and the workflow that builds them.
- **No aliasing in the resolver.** `_RUNNER_PREFIX` in
  `apps/backend/tools/runners/docker_runner.py:91` becomes
  `"tfactory-runner-"`, and bare tags still resolve to
  `ghcr.io/olafkfreund/`.
- **Not touched** (history): `CHANGELOG.md`, `.agent-os/`, `intent/`. The
  old GHCR `pfactory-runner-*` packages stay.
- **No Kyverno change.** `tfactory-runner-*` is already verified and covered.
  `pfactory-runner-*` never was.
- **Two PRs to PFactory `dev`.** PR 1 is vitest only, verified live. PR 2 is
  the other five plus all deletions.
- Merges of this task's PRs, including the release PRs that deploy them,
  were pre-approved by the approver at the intent gate.
- The six Dockerfiles are byte-identical apart from the repo name (measured
  2026-10-14), so PFactory loses nothing by using TFactory's.

## Steps

Who does what:
- **the session:** step 1 (one file), plus review, commit, release and live
  checks (steps 2 and 6);
- **Codex:** step 3 (bulk rename, deletions, tests);
- **agy:** step 4 (TFactory header note).

1. **PFactory PR 1 (vitest):** edit `frameworks/vitest/descriptor.yaml:27`,
   changing `image: pfactory-runner-vitest:latest` to
   `image: tfactory-runner-vitest:latest`. Leave the vitest Dockerfile, the
   guides and `runner-images.yml` alone until step 3.
   - Verify: CI is green, and
     `git grep -n "runner-vitest" -- frameworks apps` shows only the
     `tfactory-` name.
   - Trap: `_RUNNER_PREFIX` is still `pfactory-runner-` in this PR, so the
     bare tag `tfactory-runner-vitest:latest` will **not** be qualified by
     `resolve_runner_image` and would resolve against the local daemon.
     Write the descriptor as
     `ghcr.io/olafkfreund/tfactory-runner-vitest:latest`, which is
     already qualified and passes through untouched (`"/" in image`). Step 3
     normalises it back to the bare tag once the prefix changes.
2. **Release and verify vitest live** (session).
   - *Deviation (2026-10-14, while executing):* the deployed PFactory pod has
     no Docker daemon, socket or CLI. `DockerRunner` lanes cannot run in the
     cluster, so a release would have nothing to observe, and Kyverno never
     sees these images. Releases are dropped from steps 2 and 6, and the
     change ships with the next normal release. The check is instead run
     locally through PFactory's own code:
     - `resolve_runner_image(descriptor image)` resolves it;
     - `docker pull` and `docker run --network none <img> npx --no-install vitest --version`
       run it;
     - `cosign verify` with the TFactory GitHub OIDC identity checks the
       signature Kyverno would check.
   - Done for vitest: `ghcr.io/olafkfreund/tfactory-runner-vitest@sha256:bcf1b48b…`,
     `vitest/3.2.7`, cosign claims validated.
   - Originally planned:
   - Merge PR 1, then release:
     `node scripts/bump-version.js patch` on `dev`, a promote PR from `dev`
     to `main` merged with `--merge`, then `release.yml` and `deploy.yml`
     (Argo CD) run.
   - Start a PFactory run that uses vitest, through the pfactory MCP
     `task_create_and_run` on a project with a vitest suite.
   - Verify:
     - the runner Job or container image is
       `ghcr.io/olafkfreund/tfactory-runner-vitest:latest`;
     - if it is a pod in `factory`, its `kyverno.io/verify-images`
       annotation shows `pass`;
     - the lane completes.
   - If PFactory runs this lane through the local Docker daemon rather
     than a pod, record that Kyverno does not apply to it, and verify by
     the pulled image digest instead.
   - Trap: the bump script commits itself and runs PFactory's pre-commit
     hook, which takes about 8–10 minutes. Let it finish.
3. **PFactory PR 2** (Codex, fresh worktree from `dev` after PR 1 merges).
   1. Change `docker_runner.py:91` to `_RUNNER_PREFIX = "tfactory-runner-"`,
      and revert the vitest descriptor to the bare
      `tfactory-runner-vitest:latest`.
   2. Rename `pfactory-runner-(cloud|cypress|jest|playwright|pytest|vitest)`
      to `tfactory-runner-\1` in every file except `CHANGELOG.md`,
      `.agent-os/**`, `intent/**` and the directories deleted below. This
      covers code, tests, `frameworks/*/descriptor.yaml`, `.env.example`,
      `docs/`, `guides/`, `.claude/skills/` and `scripts/demo/`.
   3. Delete `docker/pfactory-runner-{cloud,cypress,jest,playwright,pytest,vitest}/`,
      `.github/workflows/runner-images.yml` and
      `tests/test_runner_images_publish.py`.
   4. In `tests/test_docker_runner.py`, remove or retarget only the
      assertions that read `runner-images.yml` or `docker/pfactory-runner-*`.
      Keep the resolver tests, retargeted to `tfactory-runner-`.
   5. `.github/workflows/image-build.yml:12`: update the comment that names
      `docker/pfactory-runner-*`.
   6. `guides/shipping.md`: local builds now come from the TFactory repo.
      Point the `docker build` example there.

   - Verify:
     - `git grep -nE 'pfactory-runner-(cloud|cypress|jest|playwright|pytest|vitest)'`
       hits only `CHANGELOG.md`, `.agent-os/` and `intent/`;
     - the PFactory suite passes:
       `apps/backend/.venv/bin/pytest tests -q -x`, or CI;
     - the ratchet passes:
       `scripts/ratchet_lint.py --base origin/dev --package scripts,tests`,
       plus the same with `--tool mypy`.
   - Traps:
     - no other `pfactory-runner-` names exist beyond these six, so a broader
       regex is fine. Still check
       `git grep -n "pfactory-runner-" | grep -vE "(cloud|cypress|jest|playwright|pytest|vitest)"`
       is empty;
     - jscpd and the "no workflow is a wholesale copy" gate are unaffected by
       deletions;
     - don't touch `PFACTORY_RUNNER_REGISTRY` semantics.
4. **TFactory `docker/tfactory-runner-{cloud,cypress,jest,playwright,pytest,vitest}/Dockerfile`**
   (agy): after the `# tfactory-runner-<x> — #NNN` line, add one comment
   line: `# Also PFactory's runner (Factory#1003): a change here ships to both factories.`
   - Verify: `git diff --stat` shows six one-line additions, and the
     image-build CI is green. A comment line changes no layer output, but the
     build still runs.
   - Trap: don't touch `SECURITY_REFRESH` or any other line.
5. **Merge PR 2 and the TFactory PR** once green (pre-approved), checking
   each is MERGED before any cleanup.
6. **Verify one Python lane** (session). *Deviation:* this is the local check from step 2, run against pytest. Originally: the same
   way as step 2 but with pytest: the image is
   `ghcr.io/olafkfreund/tfactory-runner-pytest:latest` and the lane
   completes. Then close #1003 with the evidence.

## Tests

- PFactory CI green on PR 1 and PR 2, including `test_docker_runner`,
  `test_framework_registry`, `test_lane_dispatch`, `test_cloud_frameworks`,
  `test_gen_functional` and the `test_lang_typescript_*` tests.
- The grep check in step 3 is clean.
- Live checks in steps 2 and 6.

## Rollback

- **PR 1:** revert the descriptor line. PFactory's own vitest image still
  exists in GHCR.
- **PR 2:** revert it. That restores the prefix, the names, the Dockerfiles
  and `runner-images.yml`. The old GHCR `pfactory-runner-*:latest` images
  are still there, so lanes work immediately, even before
  `runner-images.yml` republishes.
- **TFactory note:** revert (comment only).
