---
status: approved
issue: 3776
spec: spec/2026-11-18-3776-bitbucket-code-provider.md
coders:   # you = the lead (Claude) does the step itself
  1: you
  2: codex
  3: codex
  4: you
  5: you
reviewers:
  - codex
---

# Plan: Bitbucket code provider

Coder routing reasons: step 1 is the security-sensitive transport and merge
logic, kept with the lead; steps 2 and 3 are contained edits Codex can do from
the spec; steps 4 and 5 are docs and byte-copies. Codex also reviews the final
diff (`codex review --base origin/main`). Agy is off by owner decision.

## Decisions carried over from the approved spec

- Additive: `protocol.py` unchanged. New `providers/bitbucket_provider.py`
  holds `BitbucketProvider`, a dataclass implementing `CodeProvider` only, with
  fields `_repo` (`workspace/slug`), `_token` and `_username` (both
  `repr=False`), `_base_url` (`https://api.bitbucket.org/2.0`), `_transport`.
- Auth: `_username` set -> Basic `email:token` (API token); unset -> `Bearer`
  (access token). App passwords are retired; not mentioned as supported.
  Header built in `_client()` only; never logged, never in repr or exceptions.
- One `_client()`: `httpx.AsyncClient(follow_redirects=False)`. One `_get()`
  helper follows a redirect or `next` link only if its origin equals
  `_base_url`'s origin (max 3 redirects, max 20 pages); otherwise raise.
- Errors: `raise_for_status()` so 401/403/404/429 are `httpx.HTTPStatusError`;
  `merge_pr` -> `False` on 409/400; `check_permissions` -> `"none"` on 403/404
  (explicit grants only; group-only access reads `"none"`), raises on 401/429;
  comment reads wrap failures in `ProviderCommentError`. No 429 retry.
- Members (all under `/repositories/{ws}/{slug}` on `_base_url`):
  `get_repository_info` = `GET` repo JSON (clone URLs in `links.clone`);
  `get_default_branch` = `mainbranch.name`, else `"main"`; `fetch_pr` = `GET
  /pullrequests/{id}` + paged `/diffstat` (files, additions = `lines_added`,
  deletions = `lines_removed`) + `fetch_pr_diff` (`GET /pullrequests/{id}/diff`);
  PRData: number=id, body=description, author=`author.nickname` else
  `display_name`, url=`links.html.href`, created/updated from `created_on` /
  `updated_on`, reviewers from `participants` with role REVIEWER, `is_draft`
  from `draft`, provider BITBUCKET, `raw_data` the PR JSON.
- Checker tolerance (found by Codex plan review, P1): all four service workflows
  take the checker from hub `main` but the canonical from their old `HUB_SHA`.
  Adding the file to `CANONICAL_FILES` would raise `FileNotFoundError` for every
  service until it bumps. So `check_drift` and `compared_evidence` treat a
  listed file that is absent from the canonical tree as "pin predates this file"
  (skip, and print it as `not in this canonical`), never a crash and never a
  silent pass of a file the canonical does have.
- State map: OPEN->open, MERGED->merged, DECLINED/SUPERSEDED->closed, other ->
  `unknown` + warning. `mergeable` left at default.
- `fetch_prs`: `q` for author/base/head (quotes escaped), `since`/`limit`
  client-side, non-empty `labels` -> `[]`.
- `merge_pr`: merge->`merge_commit`, squash->`squash`, rebase->
  `rebase_fast_forward`, else `ValueError`. 202 -> follow same-origin task
  `Location`, poll max 5 times (module constant delay 1s, patchable), SUCCESS ->
  True, terminal failure -> False, still pending -> `BitbucketMergePending`
  (a `RuntimeError` subclass defined in the provider module).
- `close_pr`: optional comment, then `POST .../decline`.
  `enable_auto_merge`: `NotImplementedError`.
- `post_review`: body comment, inline findings as inline comments, then
  `approve`/`request-changes` per `review.event`; returns the body comment id.
- `fetch_pr_comments`: paged, drop `deleted`, client-side `since`, oldest
  first, cap 20 pages -> `ProviderCommentError`.
- Factory: `get_code_provider(provider_type, repo, **kwargs) -> CodeProvider`;
  Bitbucket needs env `FACTORY_BITBUCKET_ENABLED` in `1/true/yes` (read at call
  time) else `NotImplementedError`; GitHub with `token` kwarg ->
  `NotImplementedError`; other kinds delegate to `get_provider`.
  `get_provider("bitbucket")` keeps raising, message names `get_code_provider`
  and the flag. `list_available_providers`/`is_provider_available` include
  Bitbucket only when the flag is on. `providers/__init__.py` untouched.
- Drift: add `providers/bitbucket_provider.py` to `CANONICAL_FILES` in
  `scripts/check_factory_github_drift.py`.
- Re-vendor `bitbucket_provider.py` + `factory.py` byte-for-byte into
  AIFactory, PFactory, TFactory, CFactory `apps/backend/runners/github/providers/`
  (base `dev`), bump `HUB_SHA` in each `.github/workflows/factory-github-drift.yml`
  to the hub merge commit (must be on hub main), after the hub PR merges.

## Steps

1. `shared/factory-github/providers/bitbucket_provider.py` (new): implement the
   decisions above, structure like `gitlab_provider.py`, imports from
   `.protocol`. -> verify by `ruff check` + `python -c "from providers.bitbucket_provider import BitbucketProvider"` with `shared/factory-github` on `sys.path`.
   Traps: `repr=False` on credential fields (AST test); `follow_redirects=False`
   on the client (AST test); no `print`; no credential in any message.
2. `shared/factory-github/providers/factory.py`, `scripts/check_factory_github_drift.py`:
   `get_code_provider`, flag helper, `list_available_providers`,
   `is_provider_available`, the `get_provider` message; add the file to
   `CANONICAL_FILES`; make `check_drift`/`compared_evidence` tolerate a listed
   file absent from an older canonical (see Checker tolerance), and add
   regression tests in `tests/test_check_factory_github_drift.py` for an old
   canonical (no bitbucket file, service lacks it too -> no problems, no
   crash) and a new one (file present, service missing it -> problem).
   -> verify by `python scripts/check_factory_github_drift.py --self-test` and `python -m pytest tests/test_check_factory_github_drift.py -q`.
   Traps: keep `get_provider` return type `GitProvider`; flag read at call time;
   `_missing_from_contract` must keep failing for a canonical file NOT listed.
   Coordinate: rfc22-jira edits the same list; rebase on whichever merges first.
3. `tests/test_bitbucket_provider.py` (new): `httpx.MockTransport` fixtures,
   no network. Cover: pagination via `next`; cross-origin `next` and diff
   redirect refused; same-origin diff redirect followed; 401/403/404/429; merge
   strategies, 409, 202 multi-read success/failure/pending; state mapping;
   comments (deleted dropped, since, oldest first, page cap); empty-label
   filter; `isinstance(p, CodeProvider)`; credential absent from repr/str and
   exceptions; Basic vs Bearer header; `enable_auto_merge`; group-only
   permission limitation; factory flag off/on, GitHub-with-token rejected.
   -> verify by `python -m pytest tests/test_bitbucket_provider.py tests/test_provider_redirect_posture.py tests/test_provider_credential_repr.py tests/test_provider_protocol_split.py -q`.
   Traps: conftest puts `shared/factory-github` on `sys.path`; set the flag
   with `monkeypatch.setenv`, never globally.
4. `docs/guides/bitbucket-code-provider.md` (new, Jekyll front matter like
   `docs/guides/boards.md`), link from `docs/guides/index.md`;
   `docs/rfc/0022-work-item-and-code-seams.md`: Status line and Phase 5 note
   (implemented behind `FACTORY_BITBUCKET_ENABLED`, flag off);
   `docs/guides/boards.md` lines 22-31: replace the claim that Bitbucket is
   unimplemented and the stub error text; `shared/factory-github/README.md`:
   one line for the new file. The guide covers: credential kinds (API token via
   Basic `email:token`, access token via Bearer; app passwords retired), the
   flag and how to enable it, the member table, limits (permissions explicit
   only, no auto-merge, no statuses/issues), and the live-smoke checklist.
   -> verify by a python check that every relative link in the new/edited docs
   resolves to a file and the front matter has `layout`, `title`, `permalink`;
   no MkDocs nav change (`mkdocs.yml` covers `techdocs/` only).
   Traps: no secrets, no real workspace names.
5. Re-vendor (after the hub PR is open and green; pins need the hub merge SHA):
   copy the two files to the four service repos in their own worktrees, bump
   `HUB_SHA`, run `check_factory_github_drift.py` against the hub branch tree,
   open draft PRs to `dev`. -> verify by the drift checker exit 0.
   Traps: AIFactory ruff alias rule (copies are byte-exact, do not reformat);
   `HUB_SHA` must be on hub main, so PRs stay draft until the hub PR merges.

## Tests

`python -m pytest tests/test_bitbucket_provider.py tests/test_provider_redirect_posture.py tests/test_provider_credential_repr.py tests/test_provider_protocol_split.py tests/test_provider_comments.py -q` green;
the CI ratchets: `python scripts/ratchet_lint.py --base origin/main --package scripts`
and `... --package tests` (ruff), the same with `--tool mypy`, plus `ruff check`
and `mypy --strict`-free spot check on `bitbucket_provider.py`, and `ruff format --check`
on the touched files; `python scripts/check_factory_github_drift.py --self-test`
exit 0; clone budget (mandatory): `npx --yes jscpd@4 --config .jscpd.json .`
then `python scripts/check_jscpd_budget.py`, existing budget and exclusions
unchanged.

## Rollback

Flag off is the default, so a bad merge is inert. To undo: revert the hub PR
and the four re-vendor PRs (additive new file plus factory.py).

## Deviations (recorded with the code)

- Final Codex review round 1: (a) the credential is stripped of edge whitespace
  and a value still containing whitespace, control or non-ASCII characters is
  rejected with a credential-free `ValueError` (httpx otherwise quotes the whole
  header value in its error); (b) a merge task poll answering 400/409 returns
  `False` like the merge call itself. Tests added for both.
- Step 2 as done by Codex was amended by the lead: no `noqa`/`from None` churn
  in `factory.py`, and the Bitbucket guard in `get_provider` sits after the
  registry lookup so a registered Bitbucket factory still wins.
