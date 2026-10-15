---
status: approved
issue: 1775
spec: spec/2026-10-15-1775-repo-scoped-correlation-key.md
---

# Plan: scope the correlation key to the repository, and let the newest task own a stage

Closes olafkfreund/AIFactory#1775 and olafkfreund/CFactory#484 (via the hub PR).

## Approved decisions (copied from the spec)

1. **Key format.** The key is `<repo>#<n>`, where `<repo>` is the RFC-0020
   §3.5 repo reference: `owner/repo` for GitHub, `gitlab:grp/proj`,
   `azure_devops:org/proj/repo`. A bare `str(n)` is used only when the
   producer has no repo. The `af-`/`pf-`/`tf-` synthetic keys stay.
2. **Where the repo comes from.**
   - AIFactory: `requirements.json` `provenance.repo`, then
     `githubIssue.repo`, then `owner/repo` parsed from `githubIssue.url`
     when it matches `^/([^/]+/[^/]+)/issues/\d+$`.
   - TFactory: `source.json` `repo_slug`, prefixed with `<provider>:` when
     `provider` is not `github`.
   - PFactory: `session.repo`, filled from the emit target on GitHub emit
     if empty.
3. **Producers declare their key** and CFactory uses it as given:
   - AIFactory adds `correlationKey` to `/api/tasks` rows and
     `correlation_key` to the from-issue response.
   - TFactory adds `correlation_key` (and `created_at`) to
     `/api/tfactory/tasks` rows.
   - PFactory rows already have `correlation_key`.
   - CFactory adapters read `correlation_key`/`correlationKey` first and
     keep the old rule only as a fallback.
4. **AIFactory idempotency** (`_find_existing_spec`) also matches the repo
   when both the stored and the requested repo are known.
5. **CFactory accepts both formats for a window.**
   - Card lookup falls back from `<repo>#<n>` to bare `<n>` and rewrites the
     card's key once.
   - A work-item row keyed `<n>` is adopted (renamed) by a `<repo>#<n>`
     write for the same service **and the same `task_id`**. The row keeps
     its timeline, usage, other slices and `updated_at`.
   - Both migrations log `legacy correlation key migrated` at INFO.
6. **Window.** It opens when CFactory deploys. It closes 14 days after the
   last producer deploys, and only after 7 days with no
   `legacy correlation key migrated` log line. A follow-up CFactory issue
   (opened in step C6) then removes:
   - the card fallback;
   - the row adoption;
   - the bare-number branch of `_upstream_key`;
   - the adapters' issue-number fallback.
7. **Newest task owns the stage (#484).**
   - `AdapterItem.created_at` comes from `createdAt`/`created_at`.
   - In one poll, a key group where every item has a parseable timestamp
     hydrates only the newest item, dead or alive, with `newest=True`, which
     skips the #483 `superseded` check in `upsert_snapshot`.
   - Any group with a missing timestamp keeps the #483 rule unchanged.
   - Nothing new is persisted. `prune_dead`, the 24 h pruning,
     `reconcile_snapshot` and the live hub are untouched.
8. **Non-goals.**
   - AIFactory's artifact, job and log key (`agent_service.py:216`) stays
     bare.
   - PFactory `epic_ref` keeps its all-digit rule (accepted cosmetic
     change).
   - No bulk migration.

## Merge and deploy order (required)

1. **Hub PR** (this one: artifacts and the RFC-0001 §2 amendment). It merges
   **last**, after the four service PRs, so its `Closes` lines close the
   issues only once the code has landed. The service PRs link to the hub
   branch until then.
2. **CFactory PR** merges and deploys first among the code PRs (the
   consumer accepts both formats).
3. **AIFactory, TFactory and PFactory PRs**, in any order among themselves,
   but each only after the CFactory PR is **deployed**, not just merged.
4. Then the hub PR.
5. The window runs. The follow-up CFactory issue removes the legacy paths.

## Environment and traps (all steps)

- Work in worktrees under the lane scratchpad, `<repo>-1775` (CFactory:
  `cfactory-484`). Branch `fix/1775-repo-scoped-correlation-key` (CFactory:
  `fix/484-repo-scoped-correlation-key`), from `origin/dev`.
- Never touch a main clone's checkout. Never `git stash`.
- `PATH=<main clone>/apps/backend/.venv/bin:$PATH` for hooks and tests.
- Commit with `git commit -F -`. Each commit ends with the two trailer lines
  from the lane brief.
- Read code from the worktree, not `origin/dev` excerpts. The line numbers
  below are from `origin/dev` on 2026-10-15 and may have drifted by a few
  lines.
- CFactory: `mypy --strict` and ruff run as a per-file ratchet on changed
  files, so a touched file may not gain violations. No emojis. Tests run with
  `PYTHONPATH=apps/backend`.
- Prove each regression test fails without the fix. Run it in a detached
  scratch worktree of `origin/dev` with only the test file copied in.

## Steps

### CFactory (`fix/484-repo-scoped-correlation-key`)

C1. **Adapters declare the key and timestamp.**
    `apps/backend/cfactory/adapters/base.py:24-37`: add
    `created_at: str | None = None` to `AdapterItem`, and do not pass it to
    `to_state`.
    In each of `adapters/aifactory.py:39-52`, `pfactory.py:27-55` and
    `tfactory.py:118-139`:
    - set `correlation_key=str(first(row, "correlation_key", "correlationKey")
      or (issue if issue is not None else task_id))`;
    - set `created_at=first(row, "createdAt", "created_at")`, coerced with
      `str(...)` when not None.

    Mark the issue-number fallback with a comment:
    `# legacy (window, #484 follow-up): bare issue number`.

    Verify: `PYTHONPATH=apps/backend pytest tests/test_adapters.py -q`.
    Traps: `first()` returns a falsy `""` as a present value. Use `or`, so
    an empty key falls back.

C2. **Card lookup fallback.** `apps/backend/cfactory/cards.py:813-826`
    `get_by_correlation_key`:
    - On a miss, when the key matches `^(.+)#(\d+)$`, look up the oldest card
      whose `correlation_key` is the bare group 2.
    - If found, set its `correlation_key` to the qualified key in the same
      session, commit, and log
      `logger.info("legacy correlation key migrated card=%s %s -> %s", ...)`,
      passing the values through `sanitize_log` as nearby code does.
    - Return the updated card.

    Verify: `pytest tests/test_card_intake.py tests/test_cards_api.py -q`.
    Traps: the card store uses `self._session()` (a sessionmaker context, not
    `begin()`), so commit explicitly. Keep tenant scoping by using
    `self._select()`.

C3. **Row adoption.** `apps/backend/cfactory/store.py`: add a private helper
    `_adopt_legacy_row(session, key, service, task_id) -> WorkItemRow | None`
    near `_get_row` (`:725`):
    - If `key` matches `^(.+)#(\d+)$`, load the row keyed on group 2.
    - If `(getattr(row, service.value) or {}).get("task_id") == task_id`, set
      `row.correlation_key = key` and keep `row.updated_at` as it was
      (assign the old value back explicitly, because the column has
      `onupdate`).
    - Log as in C2 and return the row. Otherwise return None.

    Call it in `upsert_from_event` (`:484`, with `event.task_id`) and in
    `upsert_snapshot` (`:543`, with `state.task_id`), only when `_get_row`
    returned None.

    Verify: `pytest tests/test_store.py tests/test_store_concurrency.py -q`.
    Traps:
    - `correlation_key` is unique. The rename runs only when the qualified
      row does not exist, which `_get_row` just checked in the same
      transaction. Keep it inside the existing retry loop.
    - Pass `updated_at` explicitly; `onupdate` would otherwise re-stamp it
      and reset the 24 h pruning clock.

C4. **Newest owns the stage.**
    `apps/backend/cfactory/store.py:526` `upsert_snapshot`: add a
    keyword-only `newest: bool = False`, and AND `not newest` into
    `superseded` (`:567-572`).
    `apps/backend/cfactory/adapters/__init__.py:38-42` `hydrate`: add
    `newest_ids: frozenset[str] = frozenset()` and pass
    `newest=item.task_id in newest_ids`.
    `apps/backend/cfactory/progress.py:120-136`:
    - Before the #483 block, group `items` by `correlation_key`.
    - For each group where every item's `created_at` parses (a helper
      `_created(item) -> datetime | None` using `datetime.fromisoformat`;
      naive means UTC; `ValueError`/`TypeError` gives None), the owner is
      `max` by that datetime.
    - `live` = the owners of the timestamped groups, plus the existing #483
      selection applied only to the items in the other groups.
    - Call `hydrate(store, live, newest_ids=frozenset(owner task_ids))`.
    - `reconcile_snapshot` and `prune_duplicate_stages` keep receiving
      `live`.

    The hub feed loop (`:114-119`) is unchanged.

    Verify: `pytest tests/test_progress.py tests/test_store.py -q`.
    Traps:
    - A dead newest owner must still be hydrated. The `stuck_ids` filter for
      the hub stays.
    - Do not touch `prune_dead`.

C5. **Tests.** Add `tests/test_correlation_key_scope.py`:
    1. Two AIFactory rows, both with issue 7, `correlationKey`s `a/x#7` and
       `b/y#7` (use `httpx.MockTransport` as `tests/test_adapters.py` does),
       hydrate to two work items.
    2. A card and a row keyed `7` with aifactory `task_id` `t1`. An
       `upsert_from_event` for `a/x#7` / `t1` renames the row, keeping the
       timeline and usage, and `get_by_correlation_key("a/x#7")` returns
       that card with its key rewritten.
    3. #484: task `a` is done, and task `c` is stalled with a later
       `created_at`, on one key. After `poll_progress_once` the row shows
       `c`'s stalled status.
    4. The same as 3 with `created_at` missing on one task: the row keeps
       `a`'s done status (the #483 rule).

    Prove 1-3 fail on `origin/dev`. Verify:
    `PYTHONPATH=apps/backend pytest tests/test_correlation_key_scope.py tests/test_progress.py tests/test_store.py tests/test_adapters.py tests/test_card_intake.py -q`,
    then `ruff check` and `ruff format --check` on changed files, and
    `mypy --strict` on changed files.

C6. **Open the follow-up issue** in CFactory, "Remove legacy bare-number
    correlation-key paths (end of #484 window)". Give the exit condition
    from decision 6, and list the code removed: the C2 fallback, the C3
    helper and calls, the `card_intake.py` `_upstream_key` aifactory
    bare-number branch, and the C1 issue-number fallbacks. Link it from the
    PR body.

### AIFactory (`fix/1775-repo-scoped-correlation-key`)

A1. **Key function and readers.**
    `apps/web-server/server/services/completion.py:188-208`:
    - Add `read_issue_repo(spec_dir) -> str | None`, implementing decision 2
      (AIFactory row) with a module-level compiled regex for the URL path.
      Use `urllib.parse.urlparse(url).path`.
    - Change `correlation_key(spec_id, issue_number, repo=None)` to return
      `f"{repo}#{issue_number}"` when both are set, else the old result.
    - Update the module docstring sentence about the key (`:9-11`).

    In `build_completion_event` (`:499`), `build_worker_event` (`:608`) and
    `build_worker_progress_event` (`:682`):
    - add the keyword `repo: str | None = None`;
    - pass it to `correlation_key(...)`;
    - add `"repo": repo` to the `correlation` block.

    Callers in `emit_worker_completion` (`:774`), `emit_worker_progress`
    (`:862`), `emit_terminal_completion` (`:1042`) and `emit_usage_snapshot`
    (`:1108`) pass `repo=read_issue_repo(spec_dir)`.

    Verify: `apps/backend/.venv/bin/pytest apps/web-server/tests/test_completion_emitter.py -q`.
    Traps:
    - grep for every caller of the three builders, tests included
      (`git grep -n "build_completion_event\|build_worker_event\|build_worker_progress_event"`).
      Keyword-only with a default keeps them working.
    - The #1418 log at `:551` keeps the bare `correlation_key(spec_id, None)`.

A2. **Declare the key.**
    `apps/web-server/server/routes/task_service.py:1259` `task_to_dict`: in
    the `if spec_dir.exists()` branch, compute
    `correlation_key(task.spec_id, read_issue_number(spec_dir),
    read_issue_repo(spec_dir))`, and add `"correlationKey": <that or None>`
    to the result next to `githubIssueNumber`.
    `apps/web-server/server/routes/from_issue.py` dedup return (`:327`) and
    new-spec return (`:394`): add
    `"correlation_key": correlation_key(<spec_id>, issue_number, _declared_repo(request) or None)`.

    Verify: `apps/backend/.venv/bin/pytest tests/test_from_issue_route.py tests/test_task_service_module.py -q`.
    Traps:
    - Check for an import cycle (`server.services.completion` importing
      `routes`). If one exists, import lazily inside the function, as this
      file already does for `load_projects`.
    - In the dedup case the stored spec's repo is the truth. Use
      `read_issue_repo(project_path/.aifactory/specs/<existing>)` there.

A3. **Repo-aware idempotency.** `from_issue.py:228-257`
    `_find_existing_spec`: add a parameter `repo_ref: str | None` and skip a
    spec when `repo_ref` and `provenance.get("repo")` are both non-empty and
    differ. Pass `_declared_repo(request) or None` at the call (`:325`).

    Verify: as A2.

A4. **Tests.** In `apps/web-server/tests/test_completion_emitter.py` add:
    - two spec dirs with issue 7, `provenance.repo` `a/x` and `b/y`, give
      `a/x#7` and `b/y#7` from `build_completion_event`;
    - `read_issue_repo` parses `githubIssue.url`
      `https://github.com/o/r/issues/7` to `o/r`, and returns None with no
      repo, in which case the key stays `"7"`.

    In `tests/test_from_issue_route.py`: an existing spec for `a/x#7` does
    not dedup a request for `b/y` issue 7, but does dedup a request with no
    repo.

    Prove failure on `origin/dev`. Run `ruff check`/`ruff format --check` on
    changed files.

### TFactory (`fix/1775-repo-scoped-correlation-key`)

T1. **Qualified fallback key.** `apps/backend/agents/triager.py:728-739`
    `_correlation_key`: after the contract key, when `issue` is not None and
    `_source_repo(source)` returns a value, return `f"{repo}#{issue}"`.
    Add `_source_repo(source) -> str | None` next to it:
    `slug = source.get("repo_slug")`; when `source.get("provider")` is set
    and not `github`, return `f"{provider}:{slug}"`.
    `apps/backend/agents/handback/send.py:83-104` `_correlation_key_for`:
    apply the same qualification (import `_source_repo` from
    `agents.triager` lazily, as the function already does for
    `read_task_contract`).

    Verify: `pytest tests/test_handback_send.py tests/test_correlation_sync.py -q`
    plus whatever `git grep -ln "_correlation_key" tests/` lists.
    Traps: `_correlation_issue_number` still `int()`s a separate field; leave it.

T2. **Issue number from a qualified contract key.**
    `apps/backend/agents/tools_pkg/tools/task_control.py:517-522`: replace
    the `str(corr).isdigit()` test with
    `tail = str(corr).rsplit("#", 1)[-1]` and `if tail.isdigit(): github_issue = int(tail)`.

    Verify: `pytest tests/test_mcp_task_control.py -q`.

T3. **Declare the key and creation time.**
    `apps/web-server/server/routes/tfactory_tasks.py:125-166`
    `_summary_row`: add
    `"correlation_key": _correlation_key(spec_dir, status_doc, source_doc)`
    and `"created_at": status_doc.get("created_at") or source_doc.get("created_at")`.
    Import `_correlation_key` the way this module imports other
    `agents.*` code. If it imports none, import lazily inside the function,
    and fall back to omitting the field on `ImportError`.

    Verify: the TFactory test that covers `_summary_row`
    (`git grep -ln "_summary_row\|tfactory/tasks" tests/`).

T4. **Tests.** Add:
    - `_correlation_key` with no contract, `source.json` `{"repo_slug": "o/r",
      "provider": "github", "aifactory": {"github_issue": 7}}`, gives
      `o/r#7`;
    - provider `gitlab` gives `gitlab:o/r#7`;
    - no repo gives `"7"`;
    - `_summary_row` includes `correlation_key` and `created_at`.

    Prove failure on `origin/dev`. Run ruff on changed files.

### PFactory (`fix/1775-repo-scoped-correlation-key`)

P1. **Qualified emitted-epic key.** `apps/backend/plan/completion.py:86-89`:
    `return origin_key(session.repo, session.emitted_issue_number)`.
    `apps/backend/plan/service.py` `emit` (around `:2040-2045`): before
    `session.correlation_key = correlation_key_for(session)`, add
    `if not session.repo: session.repo = repo`, with a one-line comment
    "the epic lives in the emit target; name it in the key (#1775)".

    Verify: `pytest tests/test_plan_completion.py -q`.
    Traps:
    - `git grep -n "emitted_issue_number" tests/` and update any test that
      asserts the bare epic key. Those asserts are the old behaviour, so
      change them, and say so in the PR.
    - Persisted `session.correlation_key` values are not recomputed for
      in-flight sessions. That is intended (the CFactory window handles
      them).

P2. **Test.** In `tests/test_plan_completion.py`: a session with no origin
    issue, `repo="o/r"` and `emitted_issue_number=12` gives `o/r#12`, and
    with `repo=None` gives `"12"`. Prove failure on `origin/dev`. Run ruff on
    changed files.

### Hub (this branch)

H1. `docs/rfc/0001-correlation-key-and-completion-event.md` §2 (`:28-55`):
    - change "Canonical form" to `<repo>#<n>` with the RFC-0020 §3.5 repo
      reference and the examples from decision 1;
    - mark the bare number as the fallback when the repo is unknown
      (deprecated);
    - add one dated line, "Amended 2026-10-15 (AIFactory#1775 /
      CFactory#484)".

    Update the `correlation_key` row in the table at `:63`. Do not edit
    `shared/factory-contracts`: CFactory vendors it behind a drift gate, and
    the type is unchanged.

    Verify: the ratchet command from the lane brief passes. Markdown only.

## Handoff

Per the managed model split (more than three file-editing steps):

- one `coder` agent implements C1-C5, then A1-A4, T1-T4 and P1-P2. It is
  started with this plan path and C1, and each later step goes to the same
  agent by `SendMessage`;
- the lane agent does H1, C6, the PR bodies, CI and review;
- review is a fresh Opus agent given only this plan and each `git diff`.

## Tests (summary)

| Repo | Command | Expected |
| --- | --- | --- |
| CFactory | `PYTHONPATH=apps/backend pytest tests/test_correlation_key_scope.py tests/test_progress.py tests/test_store.py tests/test_adapters.py tests/test_card_intake.py tests/test_cards_api.py -q` | pass; the new tests fail on `origin/dev` |
| AIFactory | `apps/backend/.venv/bin/pytest apps/web-server/tests/test_completion_emitter.py tests/test_from_issue_route.py tests/test_task_service_module.py -q` | pass |
| TFactory | the T1-T4 test files | pass |
| PFactory | `pytest tests/test_plan_completion.py -q` | pass |
| all | `ruff check` and `ruff format --check` on changed files; `mypy --strict` on changed CFactory files | clean |

## Rollback

- A producer PR: revert it. Its events return to bare keys, which CFactory
  still accepts during the window. Rows and cards already migrated keep
  their qualified keys, and the reverted producer's bare events then open
  new bare rows. To recover, re-deploy the producer or revert CFactory too.
- The CFactory PR: revert only after reverting every producer PR. Otherwise
  qualified events open rows that no card finds.
- The hub PR: revert the RFC text.
