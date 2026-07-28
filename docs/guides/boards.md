---
layout: default
title: "Boards and work items: GitHub, GitLab, Azure DevOps"
permalink: /guides/boards/
---

# Boards and work items

**User story.** As a team lead, I want the board we already use to be the place
work is requested, tracked and approved, so that adopting Factory does not mean
adopting a second backlog nobody looks at.

---

## What is supported today

| Provider | Status | Repositories | Work items |
|---|---|---|---|
| **GitHub** | shipped | yes | issues, PRs, reviews, comments |
| **GitLab** | shipped | yes | issues, MRs, notes |
| **Azure DevOps** | shipped | yes | work items, PRs |
| Bitbucket | **not implemented** | — | — |
| Gitea | **not implemented** | — | — |
| Jira | **not implemented** | n/a | — |

Bitbucket and Gitea appear in the `ProviderType` enum but raise
`NotImplementedError` when constructed:

```
NotImplementedError: Bitbucket provider not yet implemented.
See providers/bitbucket_provider.py.stub for interface.
```

An enum member is not a capability. Jira has no implementation at all; it is
tracked under RFC-0022 as a work-item seam, because Jira has work items and no
repositories, which is a different shape from the three that are shipped.

If you need Bitbucket, Gitea or Jira today, the honest answer is that Factory
cannot drive them yet.

---

## The model: one board, one thread

A work item on your board becomes a card. The card carries a
**`correlation_key`** — the thread the work runs on. Every stage (plan, build,
verify) records against the same key, so the board shows one item moving rather
than four disconnected records.

That key is reused across stages by design. Per-stage idempotency is kept
separately, so re-running a stage does not duplicate the card.

---

## Setting up GitHub

**1. Provide a token.** It needs to read issues and open pull requests on the
repositories you will drive.

**2. Label the issues you want picked up.** Intake is label-driven, so an
unlabelled issue is ignored — which is what you want in a busy repository.

| Label | Effect |
|---|---|
| `factory:low`, `factory:medium` | direct build, no separate planning stage |
| `factory:hard` | full PFactory planning first |
| `factory:parallel` | wave execution across subtasks |

**3. Confirm intake sees it.** The issue should appear as a card. If it does not,
check the label spelling before anything else — a near-miss label is silently
ignored, exactly like an unlabelled issue.

**Checkpoint.** The issue appears on the board with a correlation key.

---

## Setting up GitLab

GitLab is shipped and exercised by the same canonical provider layer as GitHub.
The concepts map directly:

| GitHub | GitLab |
|---|---|
| pull request | merge request |
| review comment | note |
| issue | issue |

Give it a token with API scope on the target projects. Nested groups are handled
— a project at `group/subgroup/project` resolves correctly.

---

## Setting up Azure DevOps

Azure DevOps is shipped. Two differences worth knowing before you wire it up:

- **Authentication is Basic, not Bearer.** The client sends
  `Authorization: Basic base64(:PAT)` — note the leading colon, the username is
  empty.
- **There is no batch comments API.** `workitemsbatch` expands fields, relations
  and links, but not comments, so bulk comment reads fall back to one call per
  work item. That is bounded and predictable rather than fast: it costs exactly
  one call per item.

---

## Driving development from the board

Once intake is wired, the loop is:

1. Someone files an issue and labels it.
2. The card appears; planning runs if the tier calls for it.
3. A human approves the plan. This is a real gate, not a formality — see
   [Working as a team]({{ '/guides/teams/' | relative_url }}).
4. The build runs and opens a pull request.
5. Verification runs against the acceptance criteria.
6. The card closes when the change lands.

**The board is the control surface.** Moving a card, approving a plan, or
rejecting a build are all actions you take where you already work.

---

## Comments are read, not just written

The provider protocol includes comment reads, so a discussion on the issue is
available to the pipeline rather than lost. Ordering is normalised across
providers — each returns comments in whatever order its pagination needed, and
the protocol promises one order to the caller.

---

## Options reference

| Setting | Options | Default | Unset behaviour |
|---|---|---|---|
| Provider | `github`, `gitlab`, `azure_devops` | `github` | GitHub is assumed |
| Intake label | `factory:low`, `factory:medium`, `factory:hard`, `factory:parallel` | none | issue is ignored |
| Token | provider PAT | none | provider calls fail with an auth error |

---

## Common problems

**An issue never becomes a card.** Almost always the label. Check exact
spelling, including the colon.

**Comments appear out of order.** Only if you are reading the provider directly
rather than through the protocol; the protocol sorts.

**Bitbucket or Gitea "does not work".** It is not implemented. The
`NotImplementedError` is the feature working as designed — it tells you
immediately rather than failing subtly later.
