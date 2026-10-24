---
layout: default
title: "RFC-0023: Repository Onboarding at Scale — one action, many repos, any provider"
permalink: /rfc/repository-onboarding-at-scale/
---

# RFC-0023 — Repository Onboarding at Scale

> **Status:** Proposed · **Created:** 2026-08-25 · **Owner:** Factory hub (`shared/factory-github/`), consumed by all four services ·
> **Extends:**
> [RFC-0020](./0020-multi-provider-git-integration-and-tenant-configured-projects.md) (multi-provider git — this RFC adds the scope above its per-repo protocol),
> [RFC-0022](./0022-work-item-and-code-seams.md) (work-item vs code seams — onboarding must register both, and they are not the same system),
> [RFC-0016](./0016-horizontal-concurrent-execution.md) (concurrency — onboarding 1000 repos is only useful if more than a few can run) ·
> **Affects:** `shared/factory-github/providers/protocol.py` and its four vendored copies; the four service registries; CFactory's `git_repository` table.

## 1. Motivation

An enterprise has between 10 and 1000 repositories. Factory can onboard **one
repository, by hand, four times.** There is no discovery, no bulk path, and no
way to answer "is this repo onboarded?" without inspecting four services
individually.

### 1.1 Onboarding is four registrations with four identity schemes

| Service | Store | Key | Identity |
|---|---|---|---|
| PFactory | `projects.json` | slug | `olafkfreund-aifactory-demo` |
| AIFactory | `projects.json` | UUID | `5d78d4b9-35f9-4445-92c1-78f3ff60a494` |
| TFactory | `projects.json` | its own | — |
| CFactory | SQLite `git_repository` | repo + `default_for_tenant` | carries `aifactory_project_id` |

These must agree exactly. When they do not, a stage **dispatches into nothing
and reports success** — the single most common cause of a card that runs and
produces no work. Today the only mapping between a PFactory slug and an
AIFactory UUID is a column in CFactory's SQLite and an operator's memory.

At one repo this is a fiddly checklist. At 1000 it is 4000 registrations with a
cross-product of identity mappings and no verification.

### 1.2 The provider layer is repo-scoped by construction

`GitProvider` has 26 members and a `repo` property. Every provider is built from
a repository:

```python
def create_custom(repo: str, **kwargs) -> GitProvider: ...
def get_provider(...)
```

Implementations exist for GitHub, GitLab and Azure DevOps — the multi-provider
work of RFC-0020 is done. But a grep for `list_repositories`, `/orgs/`,
`installation/repositories` or any equivalent across the whole provider package
returns **nothing**.

This is not an oversight to patch. The layer is correct: it answers "do X to
repository R". Onboarding is the one operation that does not yet know R. It
needs a scope **above** the per-repo protocol, and that scope is what this RFC
introduces.

### 1.3 The registration mode that scales is the one that is broken

PFactory supports registering a repo without cloning it — deliberately:

```python
"path": "",  # repo-only; no local clone yet
```

That is precisely the mode bulk onboarding would use: nobody clones 1000 repos
to register them. But consumers do `Path(project_data["path"])` unguarded, so
`FilePath("") / ".pfactory"` yields a **relative** path that resolves against
the process CWD. On the read-only container root it raises
`OSError: [Errno 30] Read-only file system: '.pfactory'`; the portal reports
"Failed to refresh project index" and nothing else (PFactory#647).

Note the shape: on a writable filesystem it would not error at all. It would
silently create `.pfactory` wherever the CWD happened to be. The read-only root
is the only reason anyone noticed.

**A capability nobody uses at scale is untested at scale.** Fixing this bug is a
prerequisite, not a footnote.

## 2. Goals

1. Onboard every repository in a GitHub organisation with one action.
2. One identity per repository, mapped once, rather than four maintained by hand.
3. Answer "is repo X fully onboarded?" in a single call.
4. Detect drift continuously, rather than discovering it when a dispatch does nothing.
5. Do all of the above without assuming GitHub.

### 2.1 Non-goals

- Onboarding across multiple orgs or enterprises in one action (§7).
- Deciding *what work* each repo receives. Onboarding makes a repo eligible; intake (RFC-0011) decides what runs.
- Changing the per-repo `GitProvider` protocol. This RFC sits above it.

## 3. GitHub first, but not GitHub-shaped

The immediate need is one GitHub org. The design risk is that "one org" and
"GitHub" get baked into the same assumption, and every later provider becomes a
retrofit.

They are separable, and the seam is **account scope**:

| Provider | Scope that lists repositories | Native identity |
|---|---|---|
| GitHub | org, or App installation | `owner/repo` |
| GitLab | group (**nested subgroups**) | numeric project id, plus a path |
| Azure DevOps | organization → **project** → repo | project + repo GUID |
| Bitbucket | workspace | workspace/repo-slug |

Three properties differ in ways that break a GitHub-shaped design:

- **Hierarchy.** GitLab groups nest arbitrarily; Azure DevOps has a mandatory project level between org and repo. A flat `org -> [repo]` model cannot express either.
- **Identity.** GitHub's `owner/repo` is a stable natural key. GitLab's is a numeric id whose *path changes on rename*. Azure DevOps uses GUIDs. Keying the fleet on a name works on GitHub and silently corrupts on GitLab the first time someone renames a group.
- **Auth scope.** A GitHub App installation is itself a repo list. A GitLab PAT is user-scoped and sees whatever that user sees. "Which repos can I see?" has a different answer per provider and per credential.

### 3.1 The seam

One new protocol, deliberately small, sitting above `GitProvider`:

```python
class GitAccount(Protocol):
    """Account-scoped discovery. Distinct from GitProvider, which is repo-scoped.

    Exists because onboarding is the one operation that does not yet know which
    repository it is talking about.
    """

    @property
    def provider_type(self) -> ProviderType: ...

    async def list_repositories(
        self, *, scope: str | None = None, include_archived: bool = False
    ) -> list[RepositoryRef]: ...
```

```python
@dataclass(frozen=True)
class RepositoryRef:
    provider: ProviderType
    external_id: str      # numeric id / GUID — STABLE across rename
    path: str             # owner/repo, group/sub/project — display, may change
    default_branch: str
    archived: bool
    clone_url: str
```

`external_id` is the key the fleet stores. `path` is for humans. That distinction
is the whole reason a rename on GitLab does not orphan a project — and it costs
nothing to get right now, versus a migration later.

Two members. Anything larger is the per-repo protocol leaking upward.

## 4. One identity, mapped once

Today each service invents its own key. Instead, onboarding mints **one
`repository_id`** and every service stores it alongside its own local id.

```
repository_id  = provider + external_id       (stable, opaque)
      |
      +-- PFactory  project slug
      +-- AIFactory project uuid
      +-- TFactory  project id
      +-- CFactory  git_repository row
```

The mapping lives in **one** place — the hub — and each service records only its
own side. "Is repo X onboarded?" becomes one lookup returning four booleans,
rather than four investigations.

This also removes the failure in §1.1: a stage cannot dispatch into a service
that never registered, because the mapping says so before dispatch, not after.

## 5. Onboarding is declarative, not a script

A one-shot import handles day one and nothing after it. Repos are created,
archived, renamed and transferred continuously; at 1000 repos this is weekly.

The source of truth is a **manifest**, reconciled on a schedule:

```yaml
onboarding:
  - provider: github
    scope: olafkfreund           # org
    include: ["*"]
    exclude: ["*-archive", "sandbox-*"]
    defaults:
      tier: medium
      verify: [unit, api]
```

Reconciliation is a diff, and each side of it has one correct action:

| State | Action |
|---|---|
| in manifest, not registered | onboard |
| registered, not in manifest | flag — **never auto-remove** |
| registered, archived upstream | mark dormant, keep history |
| renamed upstream | update `path`, keep `external_id` and all history |

Auto-removal is deliberately excluded. Deleting a repo's Factory identity throws
away every card, spec and verdict attached to it, and a transient API failure
that returns an empty list would look exactly like "everything was removed".
Backstage already runs in this fleet and `catalog-info.yaml` is a reasonable
carrier for per-repo defaults; that is an integration, not a dependency.

## 6. Phases

| Phase | Delivers | Done when |
|---|---|---|
| 0 | Fix `path=''` (PFactory#647) | a repo-only project loads its index |
| 1 | `GitAccount` + GitHub implementation | `list_repositories` returns the org, archived flagged |
| 2 | `repository_id` + hub-owned mapping | one call reports onboarding state across four services |
| 3 | Bulk onboard, idempotent + resumable | 100 repos onboarded twice, second run changes nothing |
| 4 | Manifest reconciliation on a schedule | a rename upstream updates `path`, keeps history |
| 5 | GitLab `GitAccount` (nested groups) | a group tree onboards; a rename does not orphan |

Phase 0 first because it blocks everything: bulk onboarding produces exactly the
project shape that is currently broken.

Phase 5 is scheduled rather than deferred. A second provider is what proves the
seam is real — a `GitAccount` with one implementation is an interface with one
implementation, which this RFC would otherwise be introducing as an
anti-pattern.

## 7. What this does not solve

**Scale of execution.** Onboarding 1000 repos makes 1000 repos *eligible*. Concurrency is capped at 5 (AIFactory#1425 raises it to 20) and the real ceiling is storage: RWO PVCs strand each Job on one node. Tracked in Factory#959; onboarding at scale without that work produces a large, mostly idle queue.

**Credentials per repo.** One token for 1000 repos is a blast radius. Per-repo or per-team credential scoping is out of scope here and needs its own design.

**Multi-org / multi-enterprise.** §2.1. The `scope` parameter is shaped to allow it — a list of scopes rather than one — but nothing here implements it.

**Cost.** 1000 repos of intake is a real spend. RFC-0014's routing applies, but nobody has costed onboarding-scale traffic.

## 8. Open questions

1. Does `repository_id` belong in the hub or in CFactory? CFactory already carries the cross-service mapping; the hub is where the vendored code lives. Both are defensible and this RFC does not settle it.
2. Should a repo be onboardable to *some* services (code but not verify)? Partial onboarding is coherent and may be common; it also multiplies the state space.
3. What is the correct behaviour when a repo is onboarded but its provider credential later loses access? Dormant, or an error state that blocks dispatch?
