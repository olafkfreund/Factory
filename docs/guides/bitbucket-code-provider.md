---
layout: default
title: "Bitbucket code provider"
permalink: /guides/bitbucket-code-provider/
---

# Bitbucket code provider

Bitbucket Cloud as a **code** provider: pull requests, reviews and merges.
It implements `CodeProvider` from the
[RFC-0022]({{ '/rfc/work-item-and-code-seams/' | relative_url }}) split and
nothing else. Bitbucket issues are a work-item system and are not supported.

**Status: implemented, disabled by default.** Nothing changes for any tenant
until the flag is set.

## Enable it

```
FACTORY_BITBUCKET_ENABLED=1   # also accepts true / yes; read at call time
```

Callers obtain it through `get_code_provider("bitbucket", "workspace/repo", ...)`.
`get_provider("bitbucket")` keeps raising `NotImplementedError` because it
returns a `GitProvider` (code plus work items), which Bitbucket is not.

## Credentials

One opaque string, like every other provider. Atlassian has retired app
passwords, so use one of:

| Kind | How it is sent | Constructor |
|---|---|---|
| API token | HTTP Basic `email:token` | `_token=<token>, _username=<account email>` |
| Repository or workspace access token | `Authorization: Bearer` | `_token=<token>` |

The token is never logged, never in `repr()` and never in an error message. The
client does not follow redirects, and a `next` link or redirect to another host
is refused, so the token cannot be sent anywhere but the configured API host.

## What it implements

| `CodeProvider` member | Bitbucket Cloud |
|---|---|
| `get_repository_info`, `get_default_branch` | repository JSON, `mainbranch.name` (clone URLs under `links.clone`) |
| `fetch_pr`, `fetch_pr_diff` | pull request, paged diffstat, unified diff |
| `fetch_prs` | paged list; `state`, `author`, `base_branch`, `head_branch`, `since`, `limit`; entries carry no diff. A `labels` filter returns `[]`: Bitbucket PRs have no labels |
| `fetch_pr_comments` | paged comments, deleted ones dropped |
| `post_review` | summary comment, inline findings, then approve / request changes |
| `merge_pr` | `merge` = merge commit, `squash`, `rebase` = fast-forward rebase; `False` on conflict; an asynchronous merge is polled up to 5 times, then `BitbucketMergePending` |
| `close_pr` | decline, with an optional comment |
| `check_permissions` | explicit repository grant (admin/write/read/none) |
| `enable_auto_merge` | raises `NotImplementedError`: no such API |

Limits: `check_permissions` needs repository admin and sees explicit user grants
only, so access through a group reads as `none`. HTTP 401/403/404/429 surface as
`httpx.HTTPStatusError`; the provider does not retry on 429. Not implemented:
commit statuses, branch and file-content methods (use `get_repository_info`
for clone URLs), Bitbucket issues, Bitbucket Server / Data Center.

## Live smoke test (owner step)

Tests use a mock transport and never contact bitbucket.org, so the response
shapes are unconfirmed against a live workspace. Before enabling for a tenant:

1. Create a Bitbucket Cloud workspace with a test repository and a PR.
2. Create a repository access token with pull request read/write and repository
   read scopes (or an API token and the account email).
3. Set `FACTORY_BITBUCKET_ENABLED=1` in a test environment and exercise
   `fetch_prs`, `fetch_pr`, `fetch_pr_comments`, `post_review` and `merge_pr`.
4. Confirm the `q` author filter and the permissions endpoint behave as above.
