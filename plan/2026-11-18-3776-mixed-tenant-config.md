---
status: approved
issue: 3776
spec: spec/2026-11-18-3776-mixed-tenant-config.md
coders:
  # agy is off by owner decision for this round. Codex only, or the lead.
  1: lead   # tricky resolution logic, credential safety
  2: lead   # tricky store logic (locking, card guard)
  3: codex  # contained edit: migration, late-column guard, migration test
  4: codex  # small tricky logic: two consumers, exact edits listed
  5: codex  # contained edit: wire models, MCP schemas, settings, contract regen
  6: codex  # contained edit: cockpit selector, field, zod schema, test
  7: lead   # new test file, final review
reviewers:
  - codex   # independent read of the final diff (codex review --base origin/dev)
---

# Plan: mixed tenant configuration (RFC-0022 Phase 4)

Repo olafkfreund/CFactory, base `dev`, branch `feat/3776-mixed-tenant-config`.
Self-contained summary of the approved spec decisions (spec/2026-11-18-3776-mixed-tenant-config.md):

- A connection may reference a second connection of the same tenant as its
  work-item side: `git_connection.work_item_connection_id` (NULL = serves both,
  today's behaviour, no data migration). Repositories gain `work_item_project`.
- Resolution: `GitTarget.work_item: GitTarget | None`, property
  `work_item_side` = `work_item or self`. Issue paths (sync, import, comments,
  lease key) use `work_item_side`; verify and dispatch (`repo_ref`,
  `card_clone_url`, `aifactory_project_id`) use the code target.
- Validation: same tenant; not self; no chains; referenced kind in
  `WORK_ITEM_PROVIDERS`, referrer kind in `CODE_PROVIDERS` (both
  `SUPPORTED_PROVIDERS` for now); referenced connection cannot be deleted or
  take a reference of its own while referenced; checks and write in one
  transaction that first runs a no-op `UPDATE git_connection SET
  updated_at = updated_at WHERE id IN (...)` over the two rows in id order, then
  reads the invariants (row lock on PostgreSQL, write lock on SQLite). On a mixed connection
  `work_item_project` and `intake_project` follow the work-item provider's path
  rules, `project` the code provider's. Clearing the reference clears the
  repositories' `work_item_project`.
- Existing cards: set/replace/clear of a reference, or a `work_item_project`
  change, is refused (GitConfigError, 400) while a non-deleted card of the
  tenant has `issue_ref` starting `<project>#` for one of that connection's
  repositories' `project`, `intake_project` or `work_item_project`.
- Credentials: the work-item side uses only the referenced connection's own
  stored credential or install. If `connection_credential` yields
  `source == "env"` for it, use an empty `Credential()` instead (no deployment
  token to another provider). Unmixed connections keep the env fallback.
- Dangling reference: nested target with `provider="unresolved"` (constant
  `UNRESOLVED_PROVIDER`; NOT the empty string, which `build_provider` maps to
  GitHub); `sync_enabled` is True for it so `build_provider` raises "unknown git
  provider" before any credential fetch or network call, inside the existing
  never-raises handlers.
  Resolution never raises; no fallback to the code provider.
- `resolve_repository(project=...)` also matches `work_item_project`.
- API: additive optional fields `work_item_connection_id` (connection
  create/update/read), `work_item_project` (repository create/update/read), MCP
  tool schemas the same; `GitConnections.mixed_providers_enabled` from setting
  `mixed_tenant_ui` (env `CFACTORY_MIXED_TENANT_UI`, default false). UI: a
  "Work items from" select in the connection editor only when that flag is true;
  a "Work-item project" input in the repository editor when its connection has a
  reference. Azure DevOps unchanged (single provider). IssueRef stays int.

## Steps

1. `apps/backend/cfactory/git_config.py` (GitTarget ~l.419, constants ~l.96) and
   `git_connections.py` (GitConnectionRow ~l.88, GitRepositoryRow ~l.123,
   `target_from_repository` ~l.322, wire models, `repository_fields/patch`):
   add `WORK_ITEM_PROVIDERS`, `CODE_PROVIDERS`; columns; `GitTarget.work_item` and
   `work_item_side`; `UNRESOLVED_PROVIDER`; `target_from_repository(..., work_item=None)` building the
   nested target (project = `work_item_project`, `import_project =
   intake_project or work_item_project`, default_labels copied); wire fields;
   validators take an optional work-item provider kind. Lead.
   Check: `PYTHONPATH=apps/backend python -c "import cfactory.git_connections"`.
   Traps: ruff/mypy --strict per-file ratchet; plain imports, no `as` aliases in
   parenthesised imports.
2. `apps/backend/cfactory/cards.py` (`create_connection`, `update_connection`,
   `delete_connection`, `create_repository`, `update_repository`,
   `resolve_repository`, `git_target_for`): validation, locking, existing-card
   guard, env-token strip, dangling marker, project matching. Lead.
   Check: step 7 tests. Traps: `list` method shadows builtin in annotations.
3. Codex. Alembic revision on head `b8d47e1f2a63` adding the two nullable
   columns (SQLite-safe `batch_alter_table`, working `downgrade`);
   `_LATE_CONNECTION_COLUMNS` / `_LATE_REPOSITORY_COLUMNS` guards in
   `_ensure_late_columns` (cards.py ~l.633-700; add the two models to the loop);
   test in `tests/test_git_mixed_tenant.py::test_migration_*`: upgrade head,
   columns exist and NULL, downgrade one revision drops them, single head,
   `create_all` and migrations agree (existing `tests/test_schema_bootstrap.py`
   keeps passing). Also extend the guard rewind test in
   `tests/test_schema_bootstrap.py` (the `late` map ~l.154) with
   `git_connection` and `git_repository` so both new guards are exercised
   (columns absent, guards run, schema equals `create_all`, rows preserved).
   Check: `PYTHONPATH=apps/backend pytest tests/test_schema_bootstrap.py tests/test_git_mixed_tenant.py -k "migration or bootstrap or agree" -q`.
   Traps: do not edit existing migrations; keep one head.
4. Codex. `github_sync.py`: `sync_enabled` checks `target.work_item_side`
   (True when `work_item_side.provider == ""`); `_provider` builds from
   `target.work_item_side`; `_open_issue` uses `side.project`, `side.default_labels`
   and stores `IssueRef(side.project, ...)`; `maybe_sync` uses `side.project`;
   error text says "work-item project". `issue_import.py`: `import_issues` uses
   `git.work_item_side` for `sync_enabled`, `import_project`, `build_provider`;
   poll lease key `repo.intake_project or repo.work_item_project or repo.project`.
   Do NOT touch `card_intake.py` or `git_config_ops._verify_target` (code side).
   Check: `PYTHONPATH=apps/backend pytest tests/test_github_sync.py tests/test_issue_poll.py tests/test_git_multi_connection.py -q` (unchanged results).
   Traps: never-raises contract; resolution stays before the try (it no longer raises).
5. Codex. `routes_git_config.py`/`git_config_ops.py` (create/update connection and
   repository pass the new fields through, `list_git_connections` adds
   `mixed_providers_enabled=settings.mixed_tenant_ui`), `config.py` setting
   `mixed_tenant_ui: bool = False`, `mcp.py` tool input schemas and handlers
   for the same fields, regenerate `apps/frontend-web/src/api-contract.json`
   with `PYTHONPATH=apps/backend python scripts/dump_api_contract.py`.
   Check: `PYTHONPATH=apps/backend pytest tests/test_mcp.py tests/test_git_config.py -q` and
   `PYTHONPATH=apps/backend python scripts/dump_api_contract.py --check`.
   Traps: additive only; no credential ever in a response.
6. Codex. `apps/frontend-web/src/api.ts` (zod: `work_item_connection_id`,
   `work_item_project`, `mixed_providers_enabled` all optional/defaulted; update
   bodies), `GitConnectionsPanel.tsx` (select in the connection editor behind
   `mixed_providers_enabled`; repository editor input when the connection has a
   reference), test in `gitConnections.test.tsx` (selector hidden by default,
   shown with the flag).
   Check: `cd apps/frontend-web && npm run typecheck && npm test -- --run gitConnections apiContract && npm run build`.
   Traps: older backend omitting the fields must still parse.
7. `tests/test_git_mixed_tenant.py` (lead; beside codex's migration test):
   single-provider identical resolution; mixed resolution and project matching;
   validation (cross-tenant, self, chain, delete referenced, bad kind);
   existing-card refusal; env token never used for the work-item side;
   dangling reference fails visibly with zero outbound calls (no host, no
   credential fetch); sync and
   import call only the work-item host with only its token while verify and
   dispatch use only the code host (recording `httpx.MockTransport` per host);
   interleaved-transaction check with two independent engines on a FILE
   SQLite database (second writer blocks or times out until the first commits;
   chain and referenced-delete races leave one winner). Then final review: `codex review --base
   origin/dev`, own read against this plan, max 2 rounds. Lead.
   Check: `PYTHONPATH=apps/backend pytest -q` (full), 
   `ruff check apps/backend/cfactory scripts` (blocking whole-tree gate),
   `ruff format --check` on changed files, and the ratchets exactly as CI runs
   them: `python scripts/ratchet_lint.py --base origin/dev --package
   apps/backend/cfactory --package scripts` and the same with `--tool mypy`.

## Tests

Full backend suite `PYTHONPATH=apps/backend pytest`; `cd apps/frontend-web &&
npm run typecheck && npm run build`; `scripts/dump_api_contract.py --check`;
the two ratchet commands above (`.github/workflows/code-quality.yml`).
Expected: all green, no change to any existing test's expectation.

## Rollback

The feature is inert unless a connection sets `work_item_connection_id`.

- No mixed connection exists: revert the PR; `alembic downgrade b8d47e1f2a63`
  drops the two nullable columns (or leave them, older code ignores them).
- A mixed connection exists: older code would read its cards' work-item
  `issue_ref`s through the CODE connection (unrelated issues). Before reverting:
  stop issue sync and import (`CFACTORY_IMPORT_POLL=false`, and stop card sync
  by clearing the work-item connection's credential), keep the columns in place
  (no downgrade), and forward-fix instead of rolling back past this change.

## Deviations (recorded at implementation, 2026-11-18)

- Step 7 tests live in `tests/test_git_mixed_resolution.py` (lead); Codex's step 3
  migration tests are in `tests/test_git_mixed_tenant.py`. Same coverage as planned.
- Codex final review (2 rounds) added, beyond the plan: connection updates re-check
  referrers and the existing-card guard inside the locked transaction; existing
  `intake_project` and `work_item_project` paths are validated against the new
  issue-side provider on attach/replace (`_assert_paths_fit`); the repository
  guard covers `project`, `intake_project` and `work_item_project`; repository
  writes lock and re-read the connection (`_assert_side_unchanged`); an import
  discards issues if the side was re-pointed while the provider call was in flight.
- Known residual: on PostgreSQL a card insert by an unrelated writer can still
  land between the existing-card guard and the commit (the guard locks the
  connection rows, not the cards table). The import-time revalidation closes the
  import path; a manual card create naming an `issue_ref` in the window is not
  covered. Operationally negligible (admin-only reconfiguration).
- `openapi.yaml` is the curated subset with no git-connections paths; the live
  `/openapi.json` carries the new fields, so the curated file is unchanged.
