---
layout: default
title: "Provider capability matrix"
permalink: /dev/provider-capability-matrix/
---

# Provider capability matrix

> **Status:** Published · **Owner:** the fleet ·
> **From:** [RFC-0020](../rfc/0020-multi-provider-git-integration-and-tenant-configured-projects.md) section 3.5,
> Factory#366 · **Applies to:** CFactory, PFactory, AIFactory, TFactory

## The user story

> As a team whose code is on GitLab, I want to know *before* I connect it what
> the fleet will and will not do for me, so that I find out about a missing
> auto-merge while I am choosing a provider rather than two days later when a
> finished build is sitting on a merge request that nothing merges.

That is the whole reason this page exists. The reduction below is real, it is
not recoverable by configuration, and until RFC-0020 phase 5 it was discoverable
only by running into it.

## The declaration travels with the work

Before phase 5, a tenant's provider choice stopped at CFactory's boundary. Each
downstream service picked a git host from its own configuration:

| Service | Where it used to get the host |
|---|---|
| PFactory | `PFACTORY_RECON_GIT_HOST`, defaulting to `github.com` |
| AIFactory | the project's `gitProvider` setting, defaulting to `github`; the auto-PR endgame shelled out to `gh` unconditionally |
| TFactory | the project's `gitProvider` setting, defaulting to `github`; the verdict comment shelled out to `gh pr comment` |

The consequence was blunt: **a GitLab tenant's PARR run reconnoitred github.com
and opened a GitHub pull request.**

What changed is one field. The task contract's repo reference
(`provenance.repo`, mirrored on `baseline.repo`) is now optionally
**provider-qualified**:

| Provider | Reference |
|---|---|
| GitHub | `owner/repo` |
| GitLab | `gitlab:group/subgroup/project` |
| Azure DevOps | `azure_devops:organization/project/repo` |

Three rules, and they are the whole contract:

1. **GitHub is the unqualified default.** An unqualified reference reads as
   `github:`. A pre-RFC-0020 contract and every GitHub contract are unchanged,
   and there is no backfill of stored references.
2. **Only a known provider name is a qualification.** `https://gitlab.example/g/p`
   is a clone URL, not a `https`-hosted project — PFactory's reconnaissance
   accepts one, so a parser that split on the first colon regardless would break
   the caller that was already working.
3. **There is no sibling `provider` field.** Two fields is two sources of truth,
   and the one that got read would be whichever service happened to look at it
   first.

## The matrix

Everything that differs by host, and nothing that does not:

| Capability | GitHub | GitLab | Azure DevOps |
|---|---|---|---|
| Board sync and issue import | works | works | works |
| Label intake (RFC-0011) | works | works | works |
| PARR run (plan, build, verify) | works | works | works |
| Delegate an issue to a coding agent (`assign_to_user`) | works | **partial** | **not available** |
| Auto-merge when green (`enable_auto_merge`) | works | **not available** | **not available** |
| Automatic PR on a clean build | works | **not available** | **not available** |

Stated the way it matters: **a GitLab tenant gets board sync, intake and PARR.
It does not get Copilot-style delegation or auto-merge.**

### The reductions, in full

**`assign_to_user` on GitLab is PARTIAL, not absent.** It dispatches a GitLab Duo
Workflow (`gitlab_provider.py`), which needs a Duo entitlement and an
OAuth-scoped credential — the Duo endpoints reject `PRIVATE-TOKEN`. Without
either, the call is accepted and the workflow never starts. Treat a delegated
issue as unconfirmed until the issue itself shows it was picked up.

> Factory#366's summary sentence says `assign_to_user` "raises
> `NotImplementedError` on GitLab and Azure DevOps (GitLab Duo Workflow is
> partial)", which cannot be both. It does not raise on GitLab. The issue's own
> parenthetical is the accurate half, and it is what is published here.
> Publishing it as absent would be wrong in the other direction: a tenant that
> *has* Duo would be told a working feature is missing.

**`assign_to_user` on Azure DevOps raises `NotImplementedError`.** A permanent
gap, not a backlog item: Azure DevOps has no autonomous coding agent to delegate
to, so there is nothing for the method to call.

**`enable_auto_merge` is GitHub-shaped.** The RFC-0011 low-tier
auto-merge-when-green path and the RFC-0009 merge gate both rest on it, and it
raises `NotImplementedError` on GitLab and on Azure DevOps. The run still opens
its merge request and still records the `merge_policy` decision; a person or
your CI performs the merge.

**AIFactory's automatic PR is GitHub-shaped for a different reason.** The
endgame is driven through the `gh` CLI, not the provider protocol, so it cannot
be pointed at another host at all. On a non-GitHub reference it is **skipped
loudly** — the branch is pushed, the reason is recorded, and nothing fails
halfway through a `gh` call against a repo that is not there.

## Where it is published

Four surfaces, one source, so they cannot disagree:

| Surface | How to read it |
|---|---|
| CFactory Settings panel | Under the provider selector, on both the add-a-connection card and each connection's edit form, following the live selection |
| REST | `GET /api/tenants/{tenant}/git-capabilities` (read scope) |
| MCP | `cfactory_git_capabilities` (read scope) |
| Docs | this page, and CFactory's planning-board guide |

`apps/backend/cfactory/capabilities.py` is the source, and CFactory's
`tests/test_capabilities.py` asserts every claim in it against the vendored
provider layer. If a canonical provider under `shared/factory-github/providers/`
grows a real `enable_auto_merge`, or loses one, that test fails and the matrix
has to be told — which is what stops this page becoming a stale promise.

## What happens when it is unset or wrong

- **No reference at all** (a tenant with nothing configured): each service
  behaves exactly as it did before phase 5, from its own default. That is the
  only honest answer available for a deployment that never filled the panel in,
  and it is what makes the change safe to ship.
- **An unqualified reference**: reads as GitHub, which is what it always meant.
- **An unrecognised qualification** (`bitbucket:team/repo`): the whole string is
  the project and the provider is GitHub. Bitbucket and Gitea are declared in
  the provider protocol but unimplemented, so offering them would be a lie —
  they are not in `SUPPORTED_PROVIDERS` and therefore never parse as a
  qualification.
- **Auto-merge enabled on a GitLab project anyway**: the build completes, the
  branch is pushed, the endgame is skipped with the reason recorded. Nothing is
  force-merged and nothing half-runs.

## Recommended

1. **Read the matrix before connecting, not after.** It is next to the selector
   in the Settings panel for exactly this reason.
2. **On GitLab or Azure DevOps, leave `AIFACTORY_AUTO_MERGE` off** and merge from
   your own CI on a green pipeline. The merge decision is still recorded; only
   the button-press is yours.
3. **If you want Duo delegation on GitLab, verify it once by hand.** Delegate a
   throwaway issue and confirm the workflow actually started — a silent no-op is
   the failure mode, and one manual check tells you whether the entitlement and
   the credential are right.
4. **Mixed estates are fine.** Resolution is per card, through that card's
   repository (RFC-0020 phase 8), so a tenant with a GitHub connection and a
   GitLab connection gets auto-merge on the GitHub repos and not on the GitLab
   ones, in the same board.
5. **Do not work around a gap by hard-coding a host.** The two remaining
   GitHub-shaped paths are GitHub-shaped because the provider protocol has no
   implementation behind them, not because anyone chose GitHub. Implementing
   `enable_auto_merge` on `GitLabProvider` in `shared/factory-github/` is the fix,
   and it closes the gap for all four services at once.
