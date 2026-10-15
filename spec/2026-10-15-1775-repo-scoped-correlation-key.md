---
status: draft
issue: 1775
intent: intent/2026-10-15-1775-repo-scoped-correlation-key.md
---

# Spec: scope the correlation key to the repository, and let the newest task own a stage

Covers olafkfreund/AIFactory#1775 and olafkfreund/CFactory#484. File and line
references are to `origin/dev` of each service repo on 2026-10-15.

## Design

### D1. Key format

The issue key becomes `<repo>#<n>`, where `<repo>` is the repo reference the
service already stores for the issue, written exactly as RFC-0020 §3.5 writes
it: `owner/repo` for GitHub (no prefix), `gitlab:group/project`,
`azure_devops:org/project/repo`. Examples: `olafkfreund/CFactory#484`,
`gitlab:grp/app#7`.

This is not a new format. PFactory already sends it for issue-born plans
(`plan/completion.py:61` `origin_key`), and CFactory already stores issues
this way (`cards.py:203` `issue_ref`, "owner/repo#123").

Fallbacks, in order:

- A bare `str(n)` only when the producer has no repo for the issue. This is
  today's behaviour, and those keys can still collide.
- The synthetic `af-` / `pf-` / `tf-` keys, unchanged.

RFC-0001 §2 is amended in this hub PR to say this. The wire type is still
`string`, so `shared/factory-contracts` does not change.

Where the repo comes from (data each side already has, no new setting):

| Service | Source of `<repo>` |
| --- | --- |
| AIFactory | `requirements.json` `provenance.repo`, else `githubIssue.repo` (both written by `routes/from_issue.py:188,201`), else `owner/repo` parsed from `githubIssue.url` when it has the GitHub shape `/<owner>/<repo>/issues/<n>`. The last case covers specs from the `gh issue view` import (`routes/github.py:1850`), which store `url` but no `repo`. |
| TFactory | `context/source.json` `repo_slug` + `provider` (`tools_pkg/tools/task_control.py:546-547`). The `provider:` prefix is added back when the provider is not `github`. |
| PFactory | `session.repo` (unchanged). On GitHub emit, `session.repo` is filled from the emit target if it is empty (D5). |

### D2. Producers declare their key; CFactory stops re-deriving it

Today CFactory rebuilds each producer's key from a raw issue number in four
places: `card_intake.py:513-515` and `adapters/{aifactory,pfactory,tfactory}.py`.
That copied rule is how the collision got in. With this change each producer
returns the key it uses on its own events, and CFactory uses that key as-is:

- AIFactory `/api/tasks` rows add `correlationKey`, and the from-issue
  response (both the new-spec and dedup returns, `routes/from_issue.py:327`
  and `:394`) adds `correlation_key`. Both come from the same function and
  readers as the completion event, so the poll key and the event key cannot
  drift.
- TFactory `/api/tfactory/tasks` rows (`routes/tfactory_tasks.py:125`
  `_summary_row`) add `correlation_key`, computed by the same
  `agents/triager.py:728` `_correlation_key` the completion event uses.
- PFactory session rows already include `correlation_key`
  (`plan/service.py:219-238`).
- CFactory adapters read `first(row, "correlation_key", "correlationKey")`
  first and keep the current issue-number/task-id rule only as the fallback.
  `_upstream_key` already prefers a `correlation_key` in the response body,
  so it needs no change for new producers.

A side effect, and a fix: PFactory's poll rows are keyed today on the emitted
epic number (`issue_number`), while its events are keyed on the origin key.
With D2 the poll uses the event key.

### D3. Producer key functions

- **AIFactory** `services/completion.py`: `correlation_key(spec_id,
  issue_number, repo=None)` returns `f"{repo}#{issue_number}"` when both are
  set. A new `read_issue_repo(spec_dir)` implements the D1 order. The four
  event builders (`build_completion_event`, `build_worker_event`,
  `build_worker_progress_event`, and the terminal/usage emitters that call
  them) gain `repo: str | None = None`. Their callers pass
  `read_issue_repo(spec_dir)` next to the existing
  `read_issue_number(spec_dir)` (`:774`, `:862`, `:1042`, `:1108`). The
  `correlation` block also carries `repo` (additive).
- **AIFactory** `routes/from_issue.py:240-257` `_find_existing_spec`: the
  idempotency guard matches on the issue number alone, so issue #7 from repo
  B is answered with repo A's spec. It now also requires the repo to match
  when both the stored and the requested repo are known. When either is
  missing it behaves as today, so a redelivered legacy issue still dedups.
- **TFactory** `agents/triager.py:728` `_correlation_key` and
  `agents/handback/send.py:83` `_correlation_key_for`: the issue-number
  fallback becomes `<repo>#<n>` when `source.json` has a repo. The contract
  key still wins. `task_control.py:517-522` also reads the issue number from
  the end of a `…#<n>` contract key. Today it reads only an all-digit key, so
  a PFactory origin key leaves `github_issue` null.
- **PFactory** `plan/completion.py:70` `correlation_key_for`: the
  emitted-epic fallback uses `origin_key(session.repo,
  session.emitted_issue_number)` instead of `str(...)`. The epic is an issue
  in a repo, and the AIFactory import of that epic keys it as `<repo>#<n>`
  under D3. Without this, the two would split where today they collide.

### D4. Compatibility window (CFactory accepts both formats)

These carry the old key when CFactory is deployed:

- (a) cards whose `correlation_key` was written as a bare number at
  dispatch;
- (b) work-item rows keyed on a bare number;
- (c) events from producers not yet upgraded;
- (d) PFactory sessions with a persisted bare `session.correlation_key`.

CFactory handles each:

1. **Old-format events and poll rows** (c, d) keep working as they do today.
   Nothing rejects a bare key.
2. **Card lookup fallback** (a). `CardStore.get_by_correlation_key(K)`
   (`cards.py:813`): if no card holds `K` and `K` is `<repo>#<n>`, look up a
   card holding the bare `<n>`. If one is found, rewrite its
   `correlation_key` to `K` once and log `legacy correlation key migrated`.
   This one-time rewrite is the only exception to the write-once rule
   (`card_intake.py:562-566`), and it changes only the format, never the
   work the card points at.
3. **Row adoption** (b). In `WorkItemStore.upsert_from_event` and
   `upsert_snapshot` (`store.py:484`, `:543`): if no row holds `K`, `K` is
   `<repo>#<n>`, and the row keyed `<n>` holds a slice for the same service
   **with the same `task_id`**, rename that row to `K` instead of starting a
   new one. The timeline, usage, other slices and `updated_at` all stay. The
   `task_id` check makes this safe: task ids are unique per service, so a row
   is never adopted by a different repo's task. Without adoption,
   `prune_duplicate_stages` (`store.py:671`) would clear the old row's slice,
   usage included, the first time the poll sees the re-keyed task. That
   would lose the cost history of every task still listed upstream.
4. Both migrations log at INFO with the old and new key, so the end of the
   window can be measured.

**Merge and deploy order.** Hub PR → CFactory PR → producer PRs (AIFactory,
TFactory and PFactory, in any order among themselves). Each step starts only
after the one before it is deployed. If a producer ships before CFactory,
its qualified events open new rows and cards stop settling. That is the
failure this order prevents.

**Window.** It opens when the CFactory PR is deployed. It closes 14 days
after the **last** producer PR is deployed, and only once the CFactory logs
show no `legacy correlation key migrated` line for 7 days in a row. A
follow-up CFactory issue, opened with the CFactory PR, then removes:

- the card fallback and row adoption from D4;
- the bare-number branch of `_upstream_key` (`card_intake.py:513-515`);
- the adapters' issue-number fallback (the task-id/synthetic fallback stays).

Rows still keyed on a bare number at that point are finished history and are
left as they are.

### D5. PFactory emit repo

`plan/service.py` `emit` (around `:1975-2045`) sets `session.repo = repo`
before `correlation_key_for` at `:2045`, but only when `session.repo` is
empty. The epic is created in that repo, so the emitted key names it, and the
later recomputes at `:908`, `:1777`, `:1830` and `:2134` give the same answer
rather than falling back to a bare number. Sessions that already have
`session.repo` are untouched.

### D6. Newest task owns the stage (CFactory#484)

Timestamps the upstreams actually return in their list rows:

| Service | Field | Source |
| --- | --- | --- |
| AIFactory | `createdAt` | `routes/task_service.py:1322`. Recorded at intake (`requirements.json` `created_at`), or estimated from file times for old specs (#1569). |
| PFactory | `created_at` | `plan/service.py:141`, `summary()`. |
| TFactory | none today | The row has only `updated_at`, which moves on every write and so is not a creation time. `created_at` is written to `status.json` at ingest (`task_control.py:564`) but not returned. The TFactory PR adds `"created_at": status_doc.get("created_at")` to `_summary_row`. Until that is deployed, TFactory keys fall back to the #483 rule. |

CFactory:

- `AdapterItem` gains `created_at: str | None`, filled by
  `first(row, "createdAt", "created_at")`. It is **not** added to
  `ServiceState`, so no new persisted field, no change to the "unchanged"
  check, and no new `updated_at` stamps.
- `progress.py:120-134`: group one poll's items by `correlation_key`. In a
  group where **every** item has a parseable `created_at` (ISO-8601; `Z` and
  offsets accepted; a naive time is read as UTC), only the item with the
  latest `created_at` is hydrated, dead or alive. A group with any missing or
  unparseable timestamp keeps the #483 rule exactly as it is.
- `upsert_snapshot` gets `newest: bool = False`. When the poll chose the
  item by recency it passes `newest=True`, and the `superseded` check
  (`store.py:567-572`) is skipped, so the stalled re-run `c` replaces the
  older `a`'s done status. With `newest=False` the #483 check is unchanged.
- `hydrate` (`adapters/__init__.py:38`) passes `newest` through for the
  chosen task ids.

The live-progress hub (`LiveProgressHub`), `reconcile_snapshot`,
`prune_dead` and the 24 h stall pruning do not change. Adoption keeps the
row's `updated_at`, so the pruning clock does not move.

### Non-goals

- AIFactory's job-state, log and artifact-path key
  (`agent_service.py:216` `_read_correlation_key`,
  `core/artifact_store.py:69`) stays the bare issue number. It is not a
  CFactory join key, and a `/` in it would nest object-store paths.
- PFactory `contract_builder.py:263` `epic_ref` keeps its all-digit rule. An
  emitted-epic session's contract will show the plan id instead of the epic
  number in that one field (a description string). Accepted: the alternative
  threads a new parameter through three PFactory signatures for a label.
- No backfill or rewrite of existing rows outside the two lazy migrations
  in D4.

## Alternatives rejected

- **Key on the AIFactory project id instead of the repo.** A project is
  AIFactory-local. PFactory, TFactory and CFactory cards do not share it, and
  one project can build against more than one repo. The issue's repo is what
  every service already has.
- **A one-shot migration of all rows and cards at deploy.** It would need the
  repo for every historical bare-number row, which the rows do not carry
  (AIFactory's `repo` list field is never populated: `task_service.py:1038`
  builds `Task` without it). The lazy migrations touch only what is still
  live, and they match on `task_id`.
- **Producers switch first, consumer second.** Cards dispatched before the
  switch would never settle, which is the very bug being fixed.
- **Keep deriving the key in CFactory, with a repo added.** That keeps four
  copies of each producer's rule in CFactory, and copied rules are how this
  bug happened. AIFactory's `repo` list field is also empty today.
- **Use `updated_at` for recency where `created_at` is missing.** It moves on
  every write, so a stalled old task that was just touched would win over a
  newer re-run.
- **Persist `created_at` in the work-item slice so the store compares it.**
  It changes the "unchanged" check, and the write after an upgrade would
  re-stamp `updated_at` (an `onupdate` column) on every row, which resets
  the stall clock and delays the 24 h pruning. Deciding in the poll avoids
  that.

## Risks

- **Deploy order slips** (a producer before CFactory). New cards and rows
  split from in-flight ones until CFactory deploys. The order is in the plan
  and in each PR body. Rollback: revert the producer PR.
- **Card fallback picks the wrong card during the window.** It matches the
  bare number, as `get_by_correlation_key` does today. It is never worse
  than today and ends with the window.
- **Adoption when a bare row holds another repo's slice** (the collision
  this fixes). The whole row is renamed, so a PFactory slice from a
  different repo's issue #7 moves with it. Rare, display-only, and the next
  poll's `prune_duplicate_stages` re-keys that slice to its own qualified
  key.
- **Code reading the key as an integer.** TFactory `int()`s an issue number
  at `triager.py:705` and `handback/send.py:102`, and checks `isdigit()` at
  `task_control.py:522`. With a qualified key these lose only the
  `correlation.issue_number` detail, never the key. `task_control.py` is
  fixed in D3; the other two read a separate issue-number field, not the
  key. PFactory's `contract_builder.py:264` and `contract_sync.py` use exact
  string match and degrade as described under Non-goals.
- **Host:** the CFactory, AIFactory, PFactory and TFactory deployments on
  the fleet. No schema migration: `work_items.correlation_key` and
  `cards.correlation_key` are already `String(128)`, and a qualified key is
  well under that (CFactory card keys already hold `owner/repo#n` in
  `issue_ref` at 256).

## Verification

- Each service PR adds a regression test that fails on `origin/dev` and
  passes with the change:
  - AIFactory: two specs with issue 7 in different repos give different
    `correlation_key`s on the completion event and on the `/api/tasks` row,
    and `_find_existing_spec` does not dedup across repos.
  - CFactory: two AIFactory rows with issue 7 from two repos (using
    `correlationKey`) land on two work items. A legacy bare-keyed card and
    row are adopted by a qualified event for the same task. For #484, a
    newer stalled task replaces an older done one when both have
    `created_at`, and the #483 behaviour holds when one lacks it.
  - TFactory: `_correlation_key` without a contract key gives `<repo>#<n>`,
    and `_summary_row` returns `correlation_key` and `created_at`.
  - PFactory: an emitted-epic session's `correlation_key_for` gives
    `<repo>#<n>`.
- Each repo's own checks (pytest on the touched modules, `ruff check`,
  `ruff format --check`, and mypy where the repo uses it) pass in CI.
- After deploy (lead's runtime check, not part of the PRs): two issue-#N
  cards from two repos settle independently on the board, and the
  `legacy correlation key migrated` count falls to zero within the window.
