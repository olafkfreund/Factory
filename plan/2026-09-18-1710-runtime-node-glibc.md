---
status: approved
issue: 1710
spec: spec/2026-09-18-1710-runtime-node-glibc.md
---

# Plan: the runtime image's Node cannot outrun its glibc

## Approved decisions (self-contained)

- **Mechanism (measured):** the Chainguard `python:latest-dev` base pins every
  package, glibc included, exactly in `/etc/apk/world`, so `apk upgrade`
  cannot move glibc. apk dependencies are unversioned sonames, so an apk
  package built against a newer glibc installs anyway. apk `nodejs-26` needs
  exactly `GLIBC_2.44` (the image's version), and `curl` needs `GLIBC_2.43`.
- **Fix A:** Node comes from the **official** `node:<major>-bookworm-slim`
  image, digest-pinned, copied into the runtime stage. `<major>` is each repo's
  `.nvmrc`: AIFactory **24**, TFactory **26**, PFactory **26**. Official
  binaries need `GLIBC_2.28` / `GLIBCXX_3.4.21`, and their shared deps
  (`libc`, `libm`, `libdl`, `libpthread`, `libstdc++`, `libgcc_s`, `libatomic`)
  are all in the base's world. `nodejs` and `npm` are removed from `apk add`.
- **Fix B:** Dependabot `docker` PRs (digest bumps) auto-merge when their
  required checks pass: a `dependabot-digest-automerge.yml` workflow plus
  `allow_auto_merge=true` on the three repos. **Approved as a policy change.**
  No review gate exists to bypass (dev protection: AIFactory 11 required
  checks, TFactory 9, PFactory 9, no reviews).
- **Fix C:** clear the stuck base bumps AIFactory#1452, TFactory#1269,
  PFactory#666.
- Rejected: pinning apk `nodejs=` (it would freeze Node CVE fixes under the
  daily `apk upgrade`), unpinning the base (not reproducible), and a
  glibc-check-only build step (a better message, same outage).
- Unchanged: the three CLIs (`claude-code@2.1.238`, `codex@0.149.0`,
  `gemini-cli@0.56.0`), `SECURITY_REFRESH` / `apk upgrade`, Trivy gates, and
  auto-merge of anything except docker digest bumps.

### Decisions made while planning

- **One Node digest per repo.** Each repo's `frontend-build` stage already pins
  the same official image at the `.nvmrc` major (AIFactory
  `node:24-bookworm-slim@sha256:3638d9…`, TFactory and PFactory
  `node:26-bookworm-slim@sha256:cd5657…`). The new `node-runtime` stage uses
  **the identical digest**, so Dependabot bumps both lines in one PR and the
  runtime never runs a different Node from the one the frontend built with.
- **Drift guard in the Dockerfile, not CI** (deviation from the spec's wording,
  same intent). The spec said to reuse CFactory's `.nvmrc` CI step. Copying a
  15-line CI step into three workflows makes four copies to keep in sync. A
  one-line `RUN` in the runtime stage compares `node`'s major to `.nvmrc` and
  fails every build path (CI, local, cluster) on drift, with no CI change.

## Steps

Per repo, in this order: **PFactory, then TFactory, then AIFactory**. PFactory
has no `build-runtime` stage and is the smallest; AIFactory has the extra
Playwright stage. One branch `fix/1710-runtime-node-official` off `dev` per
repo, one PR each.

1. **`Dockerfile`: add the Node stage.** Directly above the `runtime` stage:
   `FROM docker.io/node:<major>-bookworm-slim@sha256:<frontend-build digest> AS node-runtime`
   → verify by `grep` showing both `FROM` lines with the identical digest.
2. **`Dockerfile`: copy Node into the runtime stage.** Before the `apk add`
   block:
   ```
   COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
   COPY --from=node-runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
   RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
   ```
   → verify in step 5's build.
3. **`Dockerfile`: remove `nodejs \` and `npm \` from `apk add`,** and replace
   the `nodejs, npm` comment (AIFactory L96, TFactory L86, PFactory L83) with
   the measured reason and a pointer to Factory#1710.
   → verify: `grep -nE '^\s+(nodejs|npm) \\$' Dockerfile` returns nothing.
4. **`Dockerfile`: the drift and glibc guard,** right after step 2's `RUN`:
   ```
   COPY .nvmrc /tmp/.nvmrc
   RUN want="$(tr -dc '0-9.' < /tmp/.nvmrc | cut -d. -f1)" \
    && have="$(node -p 'process.versions.node.split(".")[0]')" \
    && [ -n "$want" ] && [ "$want" = "$have" ] \
    || { echo "Node major drift: .nvmrc=$want runtime=$have (Factory#1710)"; exit 1; } \
    && rm /tmp/.nvmrc
   ```
   → verify: `.nvmrc` is not excluded by `.dockerignore`, and a mutation
   (edit `.nvmrc` to another major locally) fails the build with that message.
5. **Local build and property checks** (per repo, `docker build --target runtime`
   and, for AIFactory, `--target build-runtime`):
   - `node --version` major = `.nvmrc`; `npm --version` runs.
   - `claude --version`, `codex --version`, `gemini --version`,
     `antigravity --version` all print (AIFactory also `agy` if present).
   - `objdump -T "$(readlink -f "$(command -v node)")" | grep -oE 'GLIBC_[0-9.]+' | sort -Vu | tail -1`
     prints `GLIBC_2.28`.
   - `apk info | grep -c '^nodejs'` prints `0`.
   - AIFactory `build-runtime`: the Playwright `npm install -g` and the
     `/usr/local/lib/node_modules/@ffmpeg-installer` lookup (L486-487) still
     work. Root's npm global prefix is now `/usr/local`.
   - Record image size before and after (`docker image inspect … .Size`).
6. **Commit and open a PR to `dev`** with the evidence from step 5. CI must pass
   `Build root Dockerfile`, `docker (P0 acceptance)` and Trivy (no new
   HIGH/CRITICAL). Merge when green and review threads are resolved.
7. **Auto-merge workflow** (same PR or a follow-up per repo):
   `.github/workflows/dependabot-digest-automerge.yml`
   - `on: pull_request` (`opened`, `synchronize`, `reopened`);
     `if: github.actor == 'dependabot[bot]'`
   - `permissions: contents: write, pull-requests: write`
   - `dependabot/fetch-metadata` **pinned by commit SHA**; proceed only if
     `package-ecosystem == 'docker'` **and** every changed file is a
     `Dockerfile` (checked with `gh pr diff --name-only`).
   - `gh pr merge --auto --squash "$PR_URL"` with `GH_TOKEN` from env, never
     argv.
   → verify: `actionlint` clean, and the repo's workflow-pin / supply-chain
   checks pass.
   *(As built, this step also requires `base.ref == 'dev'` and adds an `edited`
   trigger with a `disarm` job; see Deviations.)*
8. **Enable the setting:** `gh api -X PATCH repos/olafkfreund/<repo> -F allow_auto_merge=true`
   → verify with `gh api repos/… --jq .allow_auto_merge` = `true`.
9. **Clear the backlog (Fix C):** `@dependabot rebase` on AIFactory#1452,
   TFactory#1269 and PFactory#666. With step 7 merged, each lands itself when
   green; close any that a newer bump supersedes.
   → verify: each is merged or closed with a reason, and PFactory's base digest
   equals the others' after it lands.
10. **Release and live check,** per repo, through its release process
    (`release/X.Y.Z` → `main`, five version places for AIFactory). After
    ArgoCD rolls out, in each pod: `node --version` = `.nvmrc` major and `claude
    --version` runs. Then one real build through the factory exercises the CLIs
    end to end.
11. **Close out:** close PFactory#674 in favour of #1710 (intent decision 3),
    close #1710 with the evidence, update each repo's docs where the runtime
    Node is described, and update memory.

## Deviations recorded during implementation

- **Newer Node digests, forced by the Trivy gate.** The first PFactory and
  TFactory builds passed every local check, then CI's `docker (P0 acceptance)`
  Trivy test failed on four HIGHs **inside the npm bundled with the reused
  `frontend-build` digest** (brace-expansion 5.0.7, ip-address 10.2.0, tar
  7.5.19). The local checks never ran Trivy; that was the gap. The node:26
  digest `c8fedd78` (v26.9.0, npm 11.19.1) ships them fixed. PFactory and
  TFactory moved **both** `FROM` lines to it, keeping the one-digest decision.
  Verified with `trivy rootfs` on the copied npm tree: the old digest
  reproduces exactly CI's four findings, and the new one scans 0.
- **AIFactory pins `npm@11.19.1`.** No node:24 image ships a patched npm yet
  (newest `2fe369e9` has npm 11.19.0). AIFactory's `.nvmrc` is 24, so the
  runtime stage runs `npm install -g npm@11.19.1` (engines `^20.17 || >=22.9`),
  and both node:24 lines moved to `2fe369e9` (v24.21.0). Dependabot cannot
  track a version inside `RUN`, so the comment states the removal condition
  (a node:24 image with npm >= 11.19.1). The final image scans 0 HIGH/CRITICAL
  in `/usr/local/lib/node_modules`.
- **Auto-merge workflow hardened after review (steps 7-8).** Two additions:
  a `base.ref == 'dev'` guard (#738/#1306/#1574), so a Dependabot PR
  retargeted at `main` is never armed, and a `disarm` job on `edited`
  (#741/#1306/#1576) that takes auto-merge back off an already-armed PR moved
  off `dev`. For PRs into `main`, GitHub evaluates the workflow from `main`,
  so both protect `main` from each repo's next release onward.
- **Post-apk guard (step 4 extended):** the `.nvmrc` guard runs before the
  apk block, so an apk `nodejs` re-added later would not have been caught. A
  second assertion after the apk block fails the build (#740/#1307/#1575).
  Verified both ways on PFactory.
- **Step 5 gains a check:** run Trivy (`rootfs`, HIGH/CRITICAL) on the
  copied `/usr/local/lib/node_modules`, not just the build and version checks.


- Local, per repo: step 5's checks all hold, and step 4's mutation fails the
  build with the drift message.
- CI, per repo: `Build root Dockerfile`, `docker (P0 acceptance)` and Trivy
  are green on the PR.
- Auto-merge: the first Dependabot digest PR after step 8 merges itself after
  its checks, and a non-docker Dependabot PR (e.g. an npm bump) is **not**
  auto-merged.
- Live: pods report the `.nvmrc` Node major, and a factory build completes.

## Rollback

- **Fix A:** revert the per-repo Dockerfile PR. apk `nodejs`/`npm` come back,
  and with them the known hazard.
- **Fix B:** delete the workflow, or set `allow_auto_merge=false` (one
  `gh api` call per repo). Already-merged bumps are ordinary commits and can
  be reverted individually.
- **Fix C:** each landed bump is a single-line digest change and can be
  reverted.
