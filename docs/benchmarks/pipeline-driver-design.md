# Design: SWE-bench pipeline driver (`scripts/benchmarks/run_pipeline_task.py`)

Status: IMPLEMENTED and smoke-proven 2026-07-11 (issue #271). One instance
(sympy__sympy-22914) driven through a local AIFactory end to end and scored
RESOLVED 1/1 by the official harness (919k tokens, USD 0.45, ~3 min build).
Every claim below carries file:line evidence from the service repos.

## Smoke-run findings (2026-07-11)

- AIFactory bug found and fixed: `/api/tasks/from-issue` never wrote
  `spec.md`, so every tier died at spawn with "Spec not found" (only the
  banner line survives into task_logs - stdout is lost in the pty read race
  on fast exit). Fixed in AIFactory #806 / PR #807 (merged to dev). A local
  benchmark server must run dev >= 5a05584f.
- Stale credential profiles poison spawns: `~/.aifactory/claude-profiles.json`
  with an old OAuth token is preferred over `~/.claude/.credentials.json`.
  Move it aside for benchmark sessions; the health endpoint's provider_auth
  tile only checks env vars and reports a false negative for OAuth-file auth.
- Local server needs `APP_HOST=127.0.0.1` when a leftover dev `.env` sets
  `APP_DISABLE_AUTH=true` (the server rightly refuses 0.0.0.0 without auth).
- Builds can finish with the patch UNCOMMITTED in the task worktree (the
  build parks in human_review before its commit step when the repo's tests
  cannot run locally). The driver recovers it: when the branch diff is
  empty, it diffs the worktree working tree against base
  (`extract_worktree_patch`). Untracked `.aifactory/` artifacts never appear
  in git diff.
- The coding agent could not run sympy's tests (immutable NixOS python, no
  mpmath) yet still produced the correct patch. For the 50-task run, per-task
  venv provisioning (`--provision-venv`) raises the odds the agent can
  iterate against real tests; it is best-effort - the agent is not
  guaranteed to discover `.venv`.

## Reuse first

- `scripts/parr_regression.py` is the template: it already drives ingest ->
  create -> start -> poll against the live cluster (service base URLs at
  `parr_regression.py:61-64`; poll loop `check_build_lifecycle` at `:216-255`).
- `shared/factory-common/factory_common/http.py` `HttpClient` is the HTTP
  layer (retries, Cloudflare-friendly, `(status, json)` returns). No new HTTP
  client, no new poller. New code is limited to the SWE-bench-specific parts:
  scratch-repo pinning and diff extraction.

## Intake: three doors, one correct one

`/from-issue` and `/from-plan` are AIFactory endpoints, not PFactory.

| Endpoint | Service | Raw text | Needs GH issue | Auth |
|---|---|---|---|---|
| `POST /api/plan/sessions/ingest-text` | PFactory | yes (`{text,title,channel}`) | no | Bearer APP_API_TOKEN |
| `POST /api/tasks/from-issue` | AIFactory | yes via `payload` dict | no, when `payload` given | Bearer APP_API_TOKEN |
| `POST /api/tasks/from-plan` | AIFactory | signed contract only | no | Bearer APP_API_TOKEN |

Evidence: PFactory ingest-text `plan_intake.py:48-61`, `plan_pipeline.py:132`;
AIFactory from-issue `from_issue.py:143-213` (mounted `main.py:467-469`;
`payload` skips any GitHub fetch, `from_issue.py:57-59,156-157`; body becomes
`requirements.description`, `:117-120`); from-plan `execution.py:1120-1243`
(query params + `{"plan": <signed contract>}`, 422 on unsigned `:1180-1187`).
Auth: shared service principal `APP_API_TOKEN` (PFactory `auth.py:251-256`,
AIFactory `auth.py:16,69,287`).

Decision: **`from-issue` is the primary intake** because it is the only door
that threads `base_branch` through to the worktree (`from_issue.py:67,
200-201`). `from-plan` never sets `baseBranch` on its contract POST
(`contract_emit.py:217-227`), so it always builds off detected `main`. The
portal-visible PFactory two-hop (ingest-text -> process -> approve ->
emit-contract) is a valid variant only because the scratch repo pins
`main == base_commit` (below).

## Repo pinning and test-leak guard

AIFactory cuts `git worktree add -b aifactory/<spec_id> <path> <base_branch>`
(`worktree.py:611-628`); `base_branch` is honored when `git rev-parse
--verify` succeeds, else falls back to `DEFAULT_BRANCH` env -> `main`
(`worktree.py:194-223,295-354`). Project registration takes exactly one of
local `path` or `gitUrl` (`projects.py:80,143-153`); `file://` URLs are
rejected (`projects.py:119-124`).

Decision: per-instance local scratch repo, registered in `path` mode:

```
git clone --no-tags <upstream> /scratch/<instance_id>
git -C /scratch/<instance_id> checkout -B main <base_commit>
git -C /scratch/<instance_id> remote remove origin
```

`main` IS `base_commit`, there is no remote and no future history, so the
agent physically cannot see the gold fix or gold tests. The normal local
build path never fetches (the only `git fetch` sites live in the GitHub
PR-reviewer/orchestrator paths: `parallel_orchestrator_reviewer.py:176`,
github `context_gatherer.py:377,398` - not exercised here). Do not set a
global `DEFAULT_BRANCH` env; do not enable `auto_handover_tfactory` or the
PR routes (the only seams that touch a remote).

## Unattended mode

- `payload.labels` sets the RFC-0011 tier; low/medium ride the skip-planning
  fast path, hard keeps full planning (`from_issue.py:20-21,179-188,240-241`).
- `auto_continue: true` drives phase transitions without prompts
  (`execution.py:43`, threaded `from_issue.py:200-201`).
- Terminal detection: poll `GET /api/tasks/{id}/status` until
  `is_running == false` (`execution.py:179-185,208-214`), then read
  `GET /api/tasks/{id}` for `status` and `branch_name`
  (`task_models.py:131,136-139`). `human_review` maps from both `completed`
  and `qa_failed` (`task_models.py:29-37`) - `is_running == false` is not a
  verdict on its own.
- Evidence gate: a terminal event with `usage.total_tokens <= 0` is
  auto-downgraded to failed with `halt_reason="no_evidence"`
  (`completion.py:402-416`). The driver re-checks this.
- Poll every 20-30 s; hard timeout 60-90 min per task.

## Diff extraction (the scored artifact)

The change lives on local branch `aifactory/<spec_id>` (`worktree.py:460-466,
611-628`; reported as `Task.branch_name`). The model patch for the official
harness is:

```
git -C /scratch/<instance_id> diff <base_commit> aifactory/<spec_id>
```

Two-dot form against the pinned base commit; no PR, no push required.

## Cost and tokens

Source of truth `<spec_dir>/token_usage.json`
(`token_attribution.py:40,58,346`), where
`spec_dir = <project>/.aifactory/specs/<spec_id>` (`from_issue.py:111-114`).
With `AIFACTORY_COMPLETION_SENTINEL=1` the full terminal event including the
v1.3 per-worker `usage` block is written to `<spec_dir>/COMPLETED.json`
(`completion.py:768-780,874`). First cut reads the filesystem; the CFactory
webhook (`routes_events.py:23-40`) is optional later.

## Endpoint sequence

```
prepare_scratch_repo(upstream, base_commit)          local, per instance
POST {AIF}/api/projects                              {"path": scratch, "name": "swebench-<instance_id>"}
POST {AIF}/api/tasks/from-issue                      {"project_id": pid,
                                                      "payload": {"title": instance_id,
                                                                  "body": problem_statement,
                                                                  "labels": ["tier:medium"]},
                                                      "base_branch": "main",
                                                      "auto_continue": true}
GET  {AIF}/api/tasks/{task_id}/status                poll until is_running == false
GET  {AIF}/api/tasks/{task_id}                       status + branch_name
git diff <base_commit> aifactory/<spec_id>           model patch
read <spec_dir>/token_usage.json / COMPLETED.json    cost + evidence check
```

## Risks

1. `from-plan` ignores base pinning - use `from-issue` (above).
2. Hollow pass on expired provider credential - re-check
   `evidence.total_tokens > 0` even on green.
3. Test leak via a live `origin` - stripped in the scratch repo.
4. `aifactory/<spec>` branch-name collisions across runs - fresh scratch repo
   per instance avoids the namespace entirely (`worktree.py:578-609`).
5. `human_review` is ambiguous - always read `Task.status` for
   `completed` vs `qa_failed`.

## Open questions for the implementation PR

- Tier label choice: medium (skip-planning fast path) vs hard (full
  planning) - decide per benchmark arm; confirm the mapping in
  `AIFactory/apps/backend/intake/` first.
- Concurrency: N registered projects at once vs serialized run; serialize
  the first baseline.
- Confirm the official harness accepts the raw two-dot diff (gold tests were
  never present in the scratch repo, so the patch cannot contain them).
