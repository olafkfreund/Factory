---
status: draft
issue: 1710
author: olafkfreund
---

# Intent: the runtime image's Node cannot outrun its glibc

## Problem

The AIFactory, TFactory and PFactory runtime images install Node, which they
need for `npm install -g` of the Claude, Codex and Gemini CLIs that the agents
spawn. Node's glibc requirement can move ahead of the glibc in the image:

- The runtime stage is `cgr.dev/chainguard/python:latest-dev`, pinned by
  digest (AIFactory L72, TFactory L58, PFactory L59). PFactory is on a
  different digest from the other two.
- `nodejs` and `npm` come from the live Wolfi apk index, unpinned (AIFactory
  L137-138, TFactory L142-143, PFactory L130-131).

On 2026-09-03 this broke `Build root Dockerfile` / `docker (P0 acceptance)` on
**every** PR in all three repos for about two days
(`node: ... GLIBC_2.44 not found`). While it was red the gate checked nothing,
and it hid two HIGH CVEs (PFactory#679). The 09-05 fixes (AIFactory#1482,
TFactory#1284) bumped the base digest. That fixed that instance but left the
mismatch in place. TFactory#1277's own analysis says it will recur.

Measured today: the gate is green in all three repos, and the structure that
broke it is unchanged in all three.

## Proposed outcome

- A new Node package in the apk index cannot break the runtime build by
  needing a newer glibc than the image provides.
- If the Node or glibc pairing does need to change, it happens as a visible,
  reviewable change (a PR), never as a surprise failure on unrelated PRs.
- The three repos use the same approach, so a fix lands once and doesn't drift.

## Affected users and systems

- The root `Dockerfile` runtime stage in AIFactory, TFactory and PFactory, and
  the images they build (the service pods that run the agent CLIs).
- `Build root Dockerfile` / `docker (P0 acceptance)` CI in all three repos.
- Anyone whose PR was blocked on 09-03..05.

## Constraints

- The agent CLIs must keep working: `claude`, `codex`, `gemini` / `antigravity`
  installed with `npm install -g` at the pinned versions.
- The security refresh must keep working: `apk upgrade` with the daily
  `SECURITY_REFRESH` cache-bust exists to clear fixable CVEs between digest
  bumps (see the cached-security-layer lesson, CFactory#440). Fixing this must
  not freeze packages again.
- Trivy HIGH/CRITICAL gates stay as they are.
- Keep one approach across the three repos (one engine, no drift).

## Open questions

1. **Why did `apk upgrade` not bring glibc forward with Node?** The runtime
   stage runs `apk upgrade` before `apk add nodejs`, from the same index, and
   the failure still happened. This mechanism is not yet measured. It decides
   whether the fix is about pinning, ordering, or the Chainguard base's package
   set, so the spec must establish it first.
2. **Scope:** only Node, or every apk package installed on top of the pinned
   base (`gh`, `git`, `curl`...)? They have the same structure; only Node has
   broken so far.
3. **PFactory#674** reports the same thing for one repo. Proposed: close it in
   favour of #1710 once this lands.
