---
status: draft
issue: 1710
intent: intent/2026-09-18-1710-runtime-node-glibc.md
---

# Spec: the runtime image's Node cannot outrun its glibc

## What was measured (2026-09-18)

All measured in `cgr.dev/chainguard/python:latest-dev@sha256:aa89…`, the
runtime base AIFactory and TFactory pin today.

1. **`apk upgrade` cannot move glibc.** The base's `/etc/apk/world` pins every
   package to an exact version (`glibc-2.44=2.44-r5`, `libstdc++=16.2.0-r1`, …),
   and glibc is packaged per version (`glibc-2.44`). A newer glibc is a
   different package name that nothing pulls in. The intent's open question 1
   is answered: the upgrade layer is working as designed. It just cannot touch
   glibc.
2. **apk has no way to know.** Node's apk dependencies are unversioned sonames
   (`so:libm.so.6`, `so:libc.so.6`) and carry no `GLIBC_2.xx` symbol version,
   so apk installs a Node built for a newer glibc than the image has.
3. **There is no headroom.** `apk add nodejs` installs `nodejs-26` (the newest
   major, while `.nvmrc` says 24), and that binary needs exactly `GLIBC_2.44`,
   the image's own version. The next Wolfi rebuild against 2.45 breaks every
   PR again.
4. **It is not only Node.** `curl` from the index already needs `GLIBC_2.43`.
   `gh` is statically linked and immune. Any C package rebuilt on the rolling
   index can do this; Node gets there first because it is rebuilt most often.
5. **The official Node binary does not have the problem.** Both
   `node:24-bookworm-slim` (v24.21.0) and `node:26-bookworm-slim` (v26.9.0) ship a
   `node` that needs only `GLIBC_2.28` / `GLIBCXX_3.4.21`. Its shared deps are
   `libc`, `libm`, `libdl`, `libpthread`, `libstdc++`, `libgcc_s` (plus
   `libatomic` on 26), all in the base's pinned world. libuv, OpenSSL and ICU
   are bundled. Copied into the
   pinned base, it runs: `v24.21.0`, npm `11.19.0`, and
   `npm install -g @anthropic-ai/claude-code@2.1.238` works and runs. The
   Dockerfile comment rejecting a binary copy "so libuv resolves" does not
   hold for the official binaries.
6. **The window is how long a digest bump stays unmerged.** Dependabot
   (`docker`, daily, target `dev`) opens base-digest bumps in all three repos,
   and they sit: AIFactory#1452 open since 08-29, TFactory#1269 and PFactory#666
   since 08-31. PFactory is still on an older digest (`30cd…`). A pinned
   `latest-dev` digest can also be garbage-collected upstream (PFactory#631).
   `allow_auto_merge` is off in all three repos.

**Scope (intent decision 2):** from 4 and 6, the hazard is general. The fix has
two parts: remove the fastest-moving package from the index entirely, and
bound the window for everything else.

## Design

### A. Node comes from a digest-pinned official image, not apk

In each root `Dockerfile` (AIFactory, TFactory, PFactory):

- Add a stage `FROM docker.io/node:<major>-bookworm-slim@sha256:<digest> AS node-runtime`,
  where `<major>` is **that repo's `.nvmrc`**. Today that is AIFactory 24,
  TFactory 26, PFactory 26: one approach, each repo on its own declared major.
  CFactory's CI already has a `.nvmrc`-vs-Dockerfile drift guard ("Node major
  drift"), which is reused so the stage cannot silently diverge from `.nvmrc`.
- In the runtime stage, `COPY --from=node-runtime` `/usr/local/bin/node` and
  `/usr/local/lib/node_modules/npm`, and link `npm` and `npx`.
- Remove `nodejs` and `npm` from the `apk add` list, and replace the comment that
  justified apk with the measured facts above.
- Everything downstream is unchanged (`npm config set prefix`, `npm install -g`
  of the three CLIs at pinned versions).

Node then moves only when the digest moves, in a reviewable Dependabot PR,
and it keeps working on every future glibc (backward compatible from 2.28).

### B. Base-digest bumps merge themselves when green

Scope: Dependabot `docker` PRs that touch only a `FROM … @sha256` line, in the
three repos.

- A small workflow, `dependabot-digest-automerge.yml`, runs on
  `pull_request` from `dependabot[bot]`. It uses
  `dependabot/fetch-metadata` and acts only when the update is a docker digest
  change. It then runs `gh pr merge --auto --squash`.
- Enable `allow_auto_merge` on the three repos. The existing required checks
  (P0 Docker build, Trivy, tests) still decide. Auto-merge merges only after
  they pass, so a bad base still cannot land.
- The weeks-long queue becomes one day, which is Dependabot's schedule.

**This is a policy change that needs your explicit approval:** it lets a bot
land base-image updates without a human click. The gates are unchanged; the
human click goes. Memory note: no PR review is required anywhere today, so
this adds no bypass that does not already exist, but it does add a merger.

### C. Clear the current backlog

Rebase (via `@dependabot rebase`) and land AIFactory#1452 / TFactory#1269 /
PFactory#666 if they are green, or close them if a newer bump supersedes
them. PFactory then moves to the same digest as the others.

## Alternatives rejected

- **Pin `nodejs=<version>` from apk.** apk would record the pin in `world`, and
  then the daily `apk upgrade` security refresh could never move it, so Node
  CVE fixes would silently stop. It also leaves the glibc coupling in place.
- **Unpin the base (`latest-dev` without a digest).** The base and index would
  always agree, but every build would be unreproducible, and
  a CVE or regression in a fresh base would land on every PR with no PR to
  review or revert.
- **A build-time check that every binary's `GLIBC_` need is at most the image's
  glibc.** It gives a better error message for the same outage; it prevents
  nothing. Part B shortens the window instead.
- **Copy Node from the existing `frontend-build` stage.** That stage is
  the frontend build's image, which is a separate concern. The runtime should
  follow `.nvmrc` on its own terms.

## Risks

- **The official Node binary needs `libstdc++`/`libgcc_s` from the base.** Both
  are in the base's pinned world today. If Chainguard ever dropped them from
  `python:latest-dev`, the build fails loudly on the first `node --version`
  step, not at runtime.
- **AIFactory's CLIs move from Node 26 (apk) to 24 (`.nvmrc`).** Declared
  engines: `@openai/codex@0.149.0` needs `>=16`, `@google/gemini-cli@0.56.0` needs
  `>=20`. `claude` 2.1.238 was installed and run under 24. The build step still
  runs every CLI's `--version`. TFactory and PFactory stay on 26.
- **npm version changes** (apk shipped npm 12; the official images ship
  their bundled npm). Only `npm install -g` and `npm config set prefix` are
  used.
- **Auto-merge lands a base that passes CI but misbehaves at runtime.** This is
  the same exposure as a human clicking merge on a green bump. The deploy chain
  (dev is not deployed; `release/X.Y.Z` → `main`) still sits between.
- **Image size.** The official Node replaces apk `nodejs`/`npm`. The net
  difference is measured in the build, not assumed.

## Verification

- **Build**, per repo: the root `Dockerfile` builds, and in the runtime image
  `node --version` is `v24.x`, `npm --version` works, and `claude`, `codex`,
  `gemini`, `antigravity` each print a version.
- **The property itself:** `objdump -T $(readlink -f $(which node))` in the
  built image shows max `GLIBC_2.28`, far below the image's glibc, and the
  major equals `.nvmrc`. No
  `nodejs-*` apk package is installed (`apk info | grep nodejs` returns nothing).
- **CI:** `Build root Dockerfile` and `docker (P0 acceptance)` pass, and Trivy
  shows no new HIGH/CRITICAL.
- **Auto-merge:** the next Dependabot digest PR in each repo merges itself
  after its checks pass, while a non-digest Dependabot PR does not.
- **Live:** after release, the agent pods run a build end to end (the CLIs are
  what the agents spawn).
