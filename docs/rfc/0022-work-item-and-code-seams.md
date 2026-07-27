---
layout: default
title: "RFC-0022: Work-Item and Code Seams — Jira for planning, GitHub for code"
permalink: /rfc/work-item-and-code-seams/
---

# RFC-0022 — Work-Item and Code Seams

> **Status:** Proposed · **Created:** 2026-07-27 · **Owner:** Factory hub (`shared/factory-github/`), consumed by all four services ·
> **Extends:**
> [RFC-0003](./0003-github-agentic-integration.md) (GitHub as the record of truth — this RFC has to qualify that claim),
> [RFC-0020](./0020-multi-provider-git-integration-and-tenant-configured-projects.md) (multi-provider git — this is the seam RFC-0020 Phase 5 could not cross),
> [RFC-0011](./0011-label-driven-intake-and-difficulty-tiers.md) (label intake — labels are a work-item concept and must survive the split) ·
> **Affects:** `shared/factory-github/providers/protocol.py` and its four vendored copies; the tenant connection model in CFactory; `apis/task-contract.schema.json` if the record-of-truth decision in §5 goes one way rather than the other.

## 1. Motivation

Jira is one of the largest work-item and planning systems, and the fleet cannot
talk to it. But "add a fourth provider" is the wrong description of the work, and
acting on that description would produce a bad result.

### 1.1 The protocol is two protocols, and this is measurable

`GitProvider` has **26 members**. Classifying them:

| Group | Count | Members |
|---|---|---|
| **Code / VCS** | 9 | `fetch_pr`, `fetch_prs`, `fetch_pr_diff`, `post_review`, `merge_pr`, `close_pr`, `enable_auto_merge`, `get_default_branch`, `check_permissions` |
| **Work items** | 12 | `fetch_issue`, `fetch_issues`, `create_issue`, `close_issue`, `add_comment`, `fetch_comments`, `fetch_comments_bulk`, `assign_to_user`, `apply_labels`, `remove_labels`, `create_label`, `list_labels` |
| **Neither** | 5 | `repo`, `get_repository_info`, `provider_type`, `api_get`, `api_post` |

So 21 of 26 members fall cleanly into one of two groups that share nothing. This
is not a judgement call about tidiness — it is the shape of the interface.

**Jira implements the 12 and none of the 9.** It has no pull requests, no diffs,
no merges, no branches. Implementing it against today's protocol means stubbing
nine methods that can never work, and every caller then has to know which
provider it is holding. At that point the abstraction is not abstracting; it is
lying, and each caller pays for the lie.

### 1.2 The five leftovers are not a rounding error

- `repo` and `get_repository_info` are **repository** concepts. Jira has
  projects, not repositories, and a Jira project does not have a default branch
  or a clone URL. These belong to the code seam, and a work-item provider must
  not be asked for them.
- `provider_type` is identity and belongs to both.
- **`api_get` and `api_post` are raw HTTP escape hatches sitting inside the
  abstraction**, and they are used: **6 call sites per service** call
  `provider.api_get(...)` directly (AIFactory, PFactory and TFactory each; plus
  14 more against `GHClient` outside the protocol). Every one of them passes a
  hard-coded GitHub REST path such as `/repos/{owner}/{repo}/issues/...`.

  That last point matters more than the count. A caller reaching through the
  protocol to a GitHub URL **is not provider-agnostic no matter what the type
  says**, so those six sites would fail against Jira while type-checking
  perfectly. They are the concrete reason §6 Phase 2 is a caller audit and not a
  formality.

### 1.3 The prize is not Jira

The common enterprise arrangement is not "Jira instead of GitHub". It is **Jira
for work items and planning, GitHub or GitLab or Bitbucket for code**.

Today's model cannot express that at all. A tenant picks `github` *or* `gitlab`
*or* `azure_devops` and gets issues and code from that one host. RFC-0020 made
that choice tenant-scoped and per-repository, which was the right move and did
not touch this: the choice is still *one provider for both jobs*.

Splitting the protocol yields:

- **work-item providers:** Jira, GitHub Issues, GitLab Issues, Azure Boards
- **code providers:** GitHub, GitLab, Azure Repos, Bitbucket
- a tenant pairing **any** of the first with **any** of the second

That mixed configuration is worth more than Jira alone, and it is what large
organisations actually run. Bitbucket also arrives nearly free once the split
exists — it is a code provider only, which today's protocol can no more express
than it can express Jira.

## 2. Design

### 2.1 Two protocols, one type-level split

```
WorkItemProvider   the 12 work-item members + provider_type
CodeProvider       the 9 code members + repo, get_repository_info + provider_type
```

`GitHubProvider`, `GitLabProvider` and `AzureDevOpsProvider` already implement
both sets, so **they satisfy both protocols unchanged**. This is a type-level
split, not a rewrite, and the existing classes need no edit to keep working.

`HttpGitHubProvider` (Factory#370) is already a `WorkItemProvider` and nothing
else — it was written to that shape before the shape had a name, which is
corroboration that the seam is real rather than invented for Jira.

### 2.2 The escape hatches do not survive the split

`api_get` and `api_post` are removed from both protocols. A raw HTTP method on a
provider-agnostic interface is a hole through the abstraction, and §1.2 shows it
is a hole that is being used.

They stay available on the concrete clients (`GHClient`, and the concrete
provider classes), so the GitHub-specific callers that legitimately need a
GitHub-specific API keep working — they simply have to hold a GitHub-specific
type to do it, which is exactly the information those call sites currently hide.

### 2.3 What a `JiraProvider` maps, and where it is lossy

Jira REST v3, as a `WorkItemProvider` only. The mapping is **not clean**, and
the RFC states the lossy edges rather than discovering them in production:

| Canonical | Jira | Lossy? |
|---|---|---|
| issue number | issue key (`PROJ-123`) | **Yes — the canonical model assumes an integer.** See §4 |
| open / closed | configurable workflow status per project | **Yes.** See §3 |
| labels | labels | No |
| comments | comments | No |
| assignee | assignee (accountId, not username) | Partly — identity is an opaque account id |
| — | issue type, epic link, story points, custom fields | **Dropped.** No canonical equivalent |

## 3. Jira has no "closed", and pretending otherwise is the worst option

GitHub, GitLab and Azure DevOps all have a two-state issue. **Jira does not.** It
has per-project configurable workflow statuses, and "is this done?" is a
*resolution* question whose answer differs between projects in the same
instance.

Three options, and the choice must be explicit:

1. **Map by status category.** Jira groups every status into `To Do`, `In
   Progress` or `Done`. This is instance-wide, always present, and cannot be
   configured away. `Done` → closed, everything else → open.
2. Map by the `resolution` field being set.
3. Let the tenant configure which statuses mean closed.

**Recommended: option 1**, with option 3 as a later override. It is the only one
that works out of the box on an unseen project, and the failure mode of the
others is silent: a board that thinks finished work is still open will re-plan
it.

The canonical `state` stays a two-state field. Widening it to "whatever the
provider says" would push per-provider knowledge into every caller — the same
mistake as §1.1, one layer up.

## 4. `PROJ-123` is not an integer

`IssueData.number` is an `int` throughout the fleet, and RFC-0001 correlation
keys are built from it. A Jira key is a string.

Options: widen the canonical identifier to a string; carry both; or synthesise an
integer from the Jira key. The third is tempting and wrong — a synthesised
integer cannot round-trip back to `PROJ-123`, so the board could display an issue
it could not then update.

**Recommended: widen to a string identifier**, with a compatibility note that
every existing key remains its decimal representation, so existing correlation
keys are unchanged. This is the single most invasive part of this RFC and the
reason §6 sequences it before the Jira provider itself rather than alongside.

## 5. Which system is the record of truth?

RFC-0003 says GitHub is the record of truth. RFC-0020 kept that intact by moving
the *host* but not the *model*: whichever provider a tenant chose was the record
for both issues and code.

With a split, that sentence no longer has one referent. A tenant running Jira +
GitHub has **two** records of truth: Jira for the work item, GitHub for the code
and the pull request.

This RFC proposes stating that directly rather than picking a winner:

> The record of truth for a **work item** is the tenant's work-item provider.
> The record of truth for **code** is the tenant's code provider. Where a fact
> exists in both (a PR that closes an issue), the code provider owns the PR, the
> work-item provider owns the issue, and the link between them is a *reference*
> held by the factory rather than a fact owned by either.

The consequence worth naming: a PR cannot close a Jira issue by GitHub's
`Closes #123` convention, because GitHub has never heard of `PROJ-123`. The
factory has to perform that transition against Jira explicitly. That is a real
behaviour change, not a mapping detail, and it is why this section is a decision
rather than an appendix.

## 6. Phases

- **Phase 1 — the canonical identifier (§4).** Widen the issue identifier to a
  string across the contract and the providers, with decimal-string compatibility
  so nothing existing changes. Ships alone, no Jira.
- **Phase 2 — the protocol split and the caller audit (§2.1, §2.2).** Define both
  protocols; remove the escape hatches; fix the 6 call sites per service that
  reach through them. The type-level split is the easy half; the audit is the
  work.
- **Phase 3 — `JiraProvider`.** REST v3, `WorkItemProvider` only, with the §3
  status-category mapping.
- **Phase 4 — mixed tenant configuration.** A tenant connection gains a
  work-item provider distinct from its code provider, extending the
  multi-connection model shipped in Factory#373.
- **Phase 5 — Bitbucket** as a code provider, which the split makes small.

Phases 1 and 2 have value with no Jira at all: they remove a lie from an
interface every service depends on. If this RFC stalls after Phase 2, the fleet
is still better off.

## 7. Credentials: a two-part secret

RFC-0020 Phase 3's store holds an **opaque string** per connection. Jira Cloud
needs either *email + API token* or OAuth 2.0 3LO — two parts, not one.

Encoding both into one string (`email:token`) would work and is what the current
store forces, but it silently makes the credential un-rotatable in halves and
un-inspectable ("is this an email?"). Preference is to let a connection carry a
structured credential, with the existing single-string form remaining valid.
This is a small change to a store that is already encrypted per-record, and it
should land in Phase 3 rather than being worked around.

## 8. Risks

- **The caller audit is the real cost**, not the Jira API. §1.2 quantifies the
  part we can see (6 sites per service through the protocol); the part we cannot
  see is callers that hold a provider and assume PR methods exist.
- **Vendoring.** `protocol.py` has four vendored copies behind pinned-SHA drift
  gates. A protocol change is a fleet-wide re-vendor and must land in all four or
  none.
- **Widening the identifier (§4) touches correlation keys**, which are how the
  cockpit joins work across the three services. A mistake here is not a bad
  mapping; it is a board that cannot find its own work.
- **Jira instances vary enormously.** Custom workflows, required fields on
  transition, and screens that reject an API-created issue for missing a
  mandatory custom field. Phase 3 must fail loudly with the field name rather
  than reporting a generic 400.

## 9. Open questions

- Should a work-item provider and a code provider be allowed to be the *same*
  object (GitHub for both), or should a tenant always configure two connections
  even when they point at one host? The first is less configuration; the second
  is fewer special cases.
- Does RFC-0011 label intake work on Jira? Jira labels exist, but the
  `factory:low|medium|hard` convention assumes a label is cheap to create and
  apply — on a locked-down Jira project it may be neither.
- Azure DevOps has *both* Boards and Repos and today is one provider. Under the
  split it becomes two, which is more honest but changes an existing tenant's
  configuration shape.
