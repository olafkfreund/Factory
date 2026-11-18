---
status: draft
issue: 3776
intent: intent/2026-11-18-3776-mixed-tenant-config.md
---

# Spec: mixed tenant configuration (RFC-0022 Phase 4)

All code is in olafkfreund/CFactory (base `dev`), `apps/backend/cfactory/`.

## Design

**Decision (owner delegation 2026-11-18): the work-item side is a reference to
a second connection of the same tenant.** The issue's recommended shape was a
"nullable work_item_provider (kind + credential reference)". A connection
already is exactly that triple (provider kind, host, sealed credential, bound to
its own id by AAD), so the reference IS the credential reference: no second
credential table, no change to the crypto binding, and a work-item provider
that arrives later (Jira, rfc22-jira) is just another connection kind with its
own structured credential. Least risky to operate; reuses #373.

### Data model
- `git_connection.work_item_connection_id` INTEGER NULL (no FK, like
  `git_repository.connection_id`). NULL = today's behaviour: this connection
  serves both sides.
- `git_repository.work_item_project` VARCHAR(256) NULL: the project path on the
  work-item provider (a connection names a host, projects belong to
  repositories). Only meaningful when the connection has a work-item reference.
- Alembic revision on top of head `b8d47e1f2a63` adds both columns
  (`downgrade` drops them via batch ops for SQLite). Live `create_all`
  deployments get the same columns from `_ensure_late_columns`
  (idempotent ALTER guard). No data backfill: NULL is the correct value for
  every existing row.

### Validation (connection create/update, repository create/update)
- Reference must be a connection of the SAME tenant (store lookup is
  tenant-scoped; otherwise 400 "no such connection"), must not be itself, must
  not itself carry a reference (no chains), and its provider must be in
  `WORK_ITEM_PROVIDERS`. The referencing connection's provider must be in
  `CODE_PROVIDERS`. Both tuples equal `SUPPORTED_PROVIDERS` today; Jira joins
  the first and Bitbucket the second when those teams land.
- A connection that other connections reference cannot take a reference of its
  own, and cannot be deleted while referenced (400 naming the referrer). These
  checks and the write run in ONE transaction that locks the two connection
  rows in id order (`SELECT ... FOR UPDATE` on PostgreSQL; SQLite serialises
  writers), so a concurrent reference/delete or two chain-forming updates
  serialise on the referenced row. A dangling reference (manual DB edit) resolves
  to a nested target with `provider=""`; `sync_enabled` treats that as ON so
  the call fails inside the existing never-raises handlers ("unknown git
  provider") and the reason lands on the card or the import result. Resolution
  itself never raises, and nothing falls back to the code provider.
- **Existing cards.** A card's `issue_ref` project is interpreted by the
  resolved side, so switching a repository between providers would re-point
  tracked issues at an unrelated project. Policy: setting, replacing or clearing
  a connection's reference, or changing a repository's `work_item_project`, is
  REFUSED (400, count named) while any non-deleted card of the tenant holds an
  `issue_ref` whose project is one of that connection's repositories'
  `project`, `intake_project` or `work_item_project`. Detach or finish those
  cards first. Re-pointing in place is a follow-up, not Phase 4.
- **No deployment-token fallback on the work-item side.** The referenced
  connection's credential must be its own stored credential or install: when
  `connection_credential` would return the deployment's environment token
  (`source == "env"`) for a work-item side, the nested target gets an
  unconfigured credential instead, so a GitHub deployment token is never sent
  to another provider. An unconfigured work-item side reads as "sync not
  configured" exactly like a single connection with no credential. Unmixed
  connections keep the env fallback unchanged.
- On a mixed connection `work_item_project` and `intake_project` are validated
  against the WORK-ITEM provider's path rules; `project` against the code
  provider's. Clearing the reference clears `work_item_project` on its
  repositories (so a stale path cannot be misread).

### Resolution
`GitTarget` (git_config.py) gains `work_item: GitTarget | None = None` and the
property `work_item_side` returning `work_item or self`. The nested target
carries the referenced connection's provider, host, credential handle,
`project = repository.work_item_project`,
`import_project = intake_project or work_item_project`, and the repository's
`default_labels` (labels are a work-item concept, RFC-0011). `CardStore.git_target_for`
builds it when the connection has a reference; otherwise `work_item` stays None
and every consumer sees the same object as today (single-provider unchanged).
The resolver pair the issue asks for is `target.work_item_side` and `target`
(code side). `resolve_repository(project=...)` also matches `work_item_project`,
because a card's `issue_ref` project is the work-item project on a mixed
connection.

### Call-site audit (every place that gets "the provider")
| Site | Operation | Side |
|---|---|---|
| github_sync.py `_provider` (used by `_open_issue`, `_fetch_issue`) | create_issue, fetch_issue | work-item |
| github_sync.py `_open_issue` (`target.project`, labels, stored `IssueRef`) | which project the issue is filed in | work-item (project and ref both from the work-item side) |
| github_sync.py `sync_enabled`, `maybe_sync` (`target.project`) | is issue sync on / is there a project | work-item |
| issue_import.py `import_issues` (`build_provider`, `import_project`) | fetch_issues | work-item |
| issue_import.py poll loop lease key (`intake_project or work_item_project or project`) | scheduling key | work-item |
| issue_import.py `_sync_comments` (`fetch_comments_bulk` on the provider `import_issues` built) | comments | work-item |
| git_config_ops.py `_verify_target` | get_repository_info | code (the work-item connection verifies itself as its own connection) |
| card_intake.py `repo_ref`, `card_clone_url`, `aifactory_project_id` (lines 190-230) | dispatch repo, clone URL, build project | code (target, not `work_item_side`) |
| cards.py `git_target*`, `resolve_repository` | resolution | both (see above) |
There are no PR, branch or merge calls in CFactory; "a code event does not call
the work-item provider" is asserted on verify and build-project paths.

### API / MCP / UI
- Wire models (additive, all optional): `GitConnection.work_item_connection_id`
  and `GitConnectionCreate/Update.work_item_connection_id`;
  `GitRepository.work_item_project` and `GitRepositoryCreate/Update.work_item_project`.
  MCP create/update connection and repository tools accept the same fields.
  `apps/frontend-web/src/api-contract.json` is regenerated
  (`scripts/dump_api_contract.py`). The curated `openapi.yaml` has no
  git-connections paths; the live `/openapi.json` carries the fields, so
  nothing is added to the curated file.
- The repository editor gains a "Work-item project" field, shown when its
  connection has a work-item reference (independent of the flag below), so a
  referenced connection can be completed from the cockpit.
- `GitConnections` response gains `mixed_providers_enabled: bool` from a new
  setting `CFACTORY_MIXED_TENANT_UI` (default false). The connection editor
  shows a "Work items from" select (another connection of this tenant, or "same
  as this connection") only when it is true. rfc22-jira turns it on when Jira is
  enabled. The REST/MCP API works regardless of the flag.

### Azure DevOps
One provider serving Boards and Repos keeps working as a single connection
(no reference). Later split: kinds `azure_boards` (work-item) and `azure_repos`
(code) as two connections to the same organisation host sharing one PAT value
stored on each. Not implemented here.

### Phase 5 / IssueRef
`IssueRef.number` stays an int here; string keys arrive with the Jira provider.
Bitbucket (rfc22-bitbucket) only adds to `CODE_PROVIDERS`.

## Alternatives rejected
- Kind + base_url + credential columns on the connection row: a second
  credential per connection needs a role column, a changed unique index and
  AAD binding, i.e. a crypto-adjacent migration, for no gain over a reference.
- A tenant-level work-item provider setting: breaks the per-repository mixing
  RFC-0020 gave us (one tenant, GitHub repos plus GitLab repos).
- Synthesising work-item projects from `project`: wrong for any non-same-host
  pair.
- Falling back to the code provider when the reference is unusable: silently
  redirects issue writes to the wrong system.

## Risks
- Migration head: rfc22-jira or rfc22-bitbucket may add a revision; whichever
  merges second rebases and re-points `down_revision`. Test asserts a single head.
- Project-path collisions across hosts in `resolve_repository(project=...)`:
  default wins the tie, same ambiguity as today.
- Vendored hub files untouched (drift gates unaffected).

## Verification
New tests in `tests/test_git_mixed_tenant.py`: single-provider connection
resolves identically (work_item None, same provider/credential/project);
mixed resolution; validation (cross-tenant, self, chain, referenced delete);
setting/clearing a reference or `work_item_project` is refused while cards
track issues there; the env token is never used for a work-item side; a
dangling reference fails visibly and never calls the code host; referenced
delete and chain checks (incl. an interleaved-transaction check on SQLite);
issue sync/import hit only the work-item host with only its token, verify hits
only the code host with only its token (recording transports, no cross-leak);
migration upgrade/downgrade on SQLite incl. single head; contract and zod tests;
`PYTHONPATH=apps/backend pytest`, `npm run typecheck && npm run build`,
`scripts/dump_api_contract.py --check`, per-file ruff and `mypy --strict`.
