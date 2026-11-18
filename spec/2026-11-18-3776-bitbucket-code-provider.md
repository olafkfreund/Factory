---
status: draft
issue: 3776
intent: intent/2026-11-18-3776-bitbucket-code-provider.md
---

# Spec: Bitbucket code provider

Decisions marked (D) are taken under the owner delegation of 2026-11-18 ("use
the recommendations"); the recommendation is the option that needs no protocol
change and no tenant-visible behaviour.

## Design

**New file** `shared/factory-github/providers/bitbucket_provider.py`:
`BitbucketProvider`, a dataclass in the style of `GitLabProvider`, satisfying
`CodeProvider` (structurally; `isinstance` against the runtime-checkable
`CodeProvider` is asserted in tests). It deliberately has no work-item members.

Fields: `_repo` (`workspace/repo_slug`), `_token` (`repr=False`), `_username`
(optional, `repr=False` not needed but kept out of logs), `_base_url`
(default `https://api.bitbucket.org/2.0`), `_transport` (tests only).

**Auth (D).** One opaque string credential, as today. With `_username` the
header is HTTP Basic `username:token` (Bitbucket app password); without it the
header is `Bearer <token>` (repository/workspace access token). The header is
built once in `_client()` and never logged or placed in `repr`/exception text.

**Transport.** A single `_client()` building `httpx.AsyncClient(...,
follow_redirects=False)` (Factory#825). Two Bitbucket behaviours need care:
`/pullrequests/{id}/diff` answers 302 to a repo-scoped diff URL, and list
endpoints return absolute `next` URLs. Both go through one `_get()` helper that
follows a redirect or `next` link only when its origin equals `_base_url`'s
origin (max 3 redirects, max 20 pages); a foreign origin raises, so the
credential never leaves the configured host.

**Errors (D).** Reads and writes call `raise_for_status()`: 401, 403, 404 and 429
surface as `httpx.HTTPStatusError` (message carries status and URL, never
headers). Exceptions where the protocol already defines a falsy outcome:
`merge_pr` returns `False` on 409/400 (conflict, merge checks failed);
`check_permissions` returns `"none"` on 403/404 (cannot see, so no access,
fail closed) and still raises on 401/429; comment reads wrap any failure in
`ProviderCommentError`. No automatic retry on 429: the caller owns backoff.

**Members.**

| Member | Bitbucket Cloud call |
|---|---|
| `get_repository_info` | `GET /repositories/{ws}/{slug}` (clone URLs are in `links.clone`) |
| `get_default_branch` | `mainbranch.name`, else `main` |
| `fetch_pr` | `GET .../pullrequests/{id}` + paged `diffstat` + `fetch_pr_diff` |
| `fetch_prs` | `GET .../pullrequests` paged via `next`; `state` mapped, `base_branch`/`head_branch`/`author` via `q`, `since` and `limit` applied client-side; `labels` ignored (Bitbucket PRs have none) |
| `fetch_pr_diff` | `GET .../pullrequests/{id}/diff` (same-origin redirect followed) |
| `fetch_pr_comments` | `GET .../pullrequests/{id}/comments` paged, deleted comments dropped, `since` client-side, oldest first, page cap raises `ProviderCommentError` |
| `post_review` | body comment (`POST /comments`), inline findings as `inline` comments, then `approve` or `request-changes` for those events; returns the body comment id |
| `merge_pr` | `POST .../merge`; `merge`->`merge_commit`, `squash`->`squash`, `rebase`->`rebase_fast_forward`, other values raise `ValueError`; a 202 (async merge) re-reads the PR and returns whether it is merged |
| `close_pr` | optional comment, then `POST .../decline` |
| `enable_auto_merge` | raises `NotImplementedError` (no Bitbucket Cloud API; same stance as GitLab) |
| `check_permissions` | `GET /repositories/{ws}/{slug}/permissions-config/users/{username}` (`username` must be the account id or `{uuid}`; needs repo admin, so a 403 reads as `"none"`) |

State mapping: `OPEN`->`open`, `MERGED`->`merged`, `DECLINED` and `SUPERSEDED`->
`closed`, anything else -> `unknown` with a warning (Factory#431 precedent).
`mergeable` is left at the dataclass default; Bitbucket does not report it on
the PR object and this provider does not invent one.

**Not implemented (D, out of scope):** commit statuses/checks, file contents and
branch listing as separate methods (no `CodeProvider` member needs them; clone
URL and default branch are reachable via `get_repository_info`), Bitbucket
issues, auto-merge, Bitbucket Server/Data Center.

**Factory and flag (D).** `protocol.py` is unchanged. `factory.py` gains:
- `get_code_provider(provider_type, repo, **kwargs) -> CodeProvider`: Bitbucket
  branch plus delegation to `get_provider()` for the others (a `GitProvider` is
  a `CodeProvider`). The Bitbucket branch raises `NotImplementedError` unless
  `FACTORY_BITBUCKET_ENABLED` is `1`/`true`/`yes`.
- `get_provider("bitbucket")` keeps raising `NotImplementedError`, now with a
  message naming `get_code_provider` and the flag, so its `GitProvider` return
  type stays honest.
- `list_available_providers()` / `is_provider_available()` include Bitbucket
  only when the flag is on. The flag is read at call time.
`providers/__init__.py` is left alone (no extra eager import, no extra drift).
`scripts/check_factory_github_drift.py` gains the new file in
`CANONICAL_FILES`, so every service copy is byte-checked.

**Vendoring.** `bitbucket_provider.py` and `factory.py` are copied byte-for-byte
to `apps/backend/runners/github/providers/` in AIFactory, PFactory, TFactory and
CFactory (base `dev`), with each repo's `HUB_SHA` pin bumped to the hub-main
merge commit. Because the pin must be on hub main, the four PRs follow the hub
PR and open as drafts until the hub PR merges.

**Docs.** `docs/guides/bitbucket-code-provider.md` (auth kinds, flag, member
table, limits, live-smoke checklist) and RFC-0022 status/Phase 5 updated.

## Alternatives rejected

- **Widen `GitProvider`/`get_provider` return type or add `ProviderType`
  capability metadata**: a protocol change, so four-copy drift and strict pin
  ordering; the additive `get_code_provider` avoids it.
- **Make Bitbucket a `GitProvider` with stubbed work-item methods**: the lie
  RFC-0022 exists to remove.
- **Follow redirects/`next` generally**: leaks the credential on a foreign host.
- **Retry on 429 inside the provider**: hides rate limits from the caller and
  needs sleeps in tests; callers already own backoff.
- **A structured (user + token) credential kind now**: Jira's structured
  credential belongs to rfc22-jira; `_username` plus one opaque token fits the
  current store.

## Risks

- Bitbucket API shapes are recorded from public docs, not a live workspace;
  fixtures may drift from reality until the owner's smoke test. Mitigated by
  the flag defaulting off.
- `check_permissions` needs repo-admin to answer; non-admin callers get
  `"none"` (fail closed), which may under-report.
- Four copies must stay byte-identical; the drift gate enforces it.
- The new client site changes the redirect-posture test's site count (5 -> 6).

## Verification

- Hub: `tests/test_bitbucket_provider.py` (mock transport, recorded-shape JSON
  fixtures): pagination via `next`, cross-origin `next`/redirect refusal,
  401/403/404/429, merge strategies and 409/202, state mapping, comments,
  repr/headers never expose the credential, `isinstance(.., CodeProvider)`,
  flag off/on in the factory. Existing `test_provider_redirect_posture.py`,
  `test_provider_credential_repr.py`, `test_provider_protocol_split.py` and the
  drift checker self-test stay green.
- `ruff` and the hub's CI checks on the PR head SHA.
- Re-vendor PRs: `check_factory_github_drift.py` against the hub merge SHA.
- Live: not run; needs a Bitbucket workspace and app password (owner step).
