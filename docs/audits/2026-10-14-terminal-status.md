# Terminal-status audit (Factory#971), 2026-10-14

**Question asked of every write that records a final status:** if this
outcome happened at the earliest possible moment, would the status still land
where its reader reads?

Each write was also checked for:
- **symmetry:** does the opposite outcome on the same path also write?
- **loudness:** is a failed write logged at error level or raised?
- **wiring:** is the failing path actually called, and is there a test
  proving it?

The method is in [plan](../../plan/2026-10-14-971-terminal-status-audit.md).
The audit was read-only, against each repo's `origin/dev`:

| Service | Commit audited |
|---|---|
| AIFactory | `33f8433b` |
| PFactory | `47f47c8` |
| TFactory | `2affdb81` |
| CFactory | `49541fc` |

Deployed settings were read from factory-gitops. Several findings only matter
in one mode, and those are noted below.

## Summary

| Service | Audited by | Instances claimed | Verified and filed | Not filed (why) | Rejected |
|---|---|---|---|---|---|
| CFactory | session | 3 | 3 | — | 0 |
| PFactory | session | 5 | 4 issues (2 instances share a root cause) | — | 0 |
| AIFactory | Codex, verified by a fresh Opus agent and the session | 3 | 1 | 2 (not live with deployed config, or self-heals) | 0 |
| TFactory | agy, verified by a fresh Opus agent and the session | 15 | 4 issues (6 root causes verified) | 2 (not live in deployed mode, or corrected on refresh) | 6 |
| Fleet | session | — | 1 (`fix-stuck-tasks.py`) | — | — |

That is **13 issues filed**. None duplicates an existing issue, and the
already-fixed instances (AIFactory #1430 and #1431, TFactory #1161,
CFactory #431) were not re-reported. Two filed issues are siblings their
fixes did not cover: PFactory#861 is TFactory#1161's twin, and TFactory#1369
is the MCP reader that #1259 left out.

## Filed

| Issue | What stays wrong, and when |
|---|---|
| [CFactory#478](https://github.com/olafkfreund/CFactory/issues/478) | A board-dispatched card stays `in_progress` when AIFactory finishes CODE. The card is joined on `<project>:<spec>`, but the event is keyed on the issue number or `af-<spec>` |
| [CFactory#479](https://github.com/olafkfreund/CFactory/issues/479) | A stalled test stage is pruned, and its plan-DAG node turns green ("completed") |
| [CFactory#480](https://github.com/olafkfreund/CFactory/issues/480) | A hung build never shows as stalled: `prune_stalled` deletes it and `hydrate` re-creates it fresh |
| [PFactory#860](https://github.com/olafkfreund/PFactory/issues/860) | Status stays planning, generating or pending on cancel or process death. `CancelledError` is not caught, handoff states aren't in the stall check, and the sweep is off |
| [PFactory#861](https://github.com/olafkfreund/PFactory/issues/861) | `lane_progress` stays all-pending (TFactory#1161's twin) |
| [PFactory#862](https://github.com/olafkfreund/PFactory/issues/862) | A plan session stays processing or ingested when `process()` raises. The failure is recorded only in the unread `job_states` |
| [PFactory#863](https://github.com/olafkfreund/PFactory/issues/863) | A Kanban card stays `in_progress` after a restart mid-run: `except CancelledError: pass` |
| [AIFactory#1771](https://github.com/olafkfreund/AIFactory/issues/1771) | The board stays `in_progress` when the subprocess monitor raises. No reaper heals it |
| [TFactory#1366](https://github.com/olafkfreund/TFactory/issues/1366) | The CFactory completion never arrives for any terminal status written before the Triager |
| [TFactory#1367](https://github.com/olafkfreund/TFactory/issues/1367) | A pipeline board card stays active on `failed` or `generated_empty` |
| [TFactory#1368](https://github.com/olafkfreund/TFactory/issues/1368) | A build task stays `in_progress` after the web-server dies. A stale `active` phase always wins |
| [TFactory#1369](https://github.com/olafkfreund/TFactory/issues/1369) | MCP `task_status` `lane_progress` stays pending after `evaluator_failed` |
| [Factory#3589](https://github.com/olafkfreund/Factory/issues/3589) | `fix-stuck-tasks.py` rewrites a terminal `failed` back to `in_progress` |

Each issue carries the scenario, the write and the reader by `file:line`, the
four answers, and the wiring test that would catch it.

## Verified but not filed

- **AIFactory: a failed build shows as backlog.** It fails before a plan
  exists, and with no control write the board maps `failed` to `backlog`
  (`services/agent_service.py:442-528`, `routes/task_service.py:1099-1127`).
  - Not live: the durable store is on (`DATABASE_URL` is deployed), and
    `overlay_durable_status` corrects it. It only happens on a single-pod
    setup with the store off.
- **AIFactory: a user-stopped Job shows `in_progress`.** The stop path writes
  only the durable row (`services/agent_kubejob.py:1142-1156`).
  - It self-heals: `reap_abandoned_tasks` writes the plan and control files
    after about 600 s of idleness, so the window is about 10 minutes.
- **TFactory: a restart mid-stage leaves `evaluating` or `triaging` stuck.**
  - Only in in-pod mode. Deployed is `TFACTORY_VERIFY_EXEC=kubejob` with
    `APP_LIVENESS_SWEEP_ENABLED=true`.
- **TFactory: a stopped task shows `backlog` in the live kanban.** The
  `human_review` from `stop_task` is overridden by the route's `backlog` emit
  (`routes/execution.py:572`).
  - A refresh shows the correct `human_review`. The leaked `job_states`
    running row has no reader.

## Rejected (TFactory, agy's report)

The fresh verifier found six claims that describe code which doesn't exist or
behaves differently. They are recorded here so the next audit doesn't redo
them.

| # | Claim | Why rejected |
|---|---|---|
| 4 | `task_cancel` | No such tool exists, and nothing writes `cancelled` |
| 7 | `verify_pipeline.main()` loses state | A non-zero Job is reaped to `failed`; it's delayed, not lost |
| 8 | `active_cap_reached` | It doesn't exist. The cap is enforced at admission, and `None` falls back to in-pod |
| 9 | `overlay_job_state` | It doesn't exist. The API returns `failed` correctly; the display is #1367 |
| 10 | `liveness.py` is "dead code" | It's wired through the sweep loop, and planning and generating are reconciled at startup |
| 11 | `load_spec_metadata` ignores failed phases | It checks them (`routes/tasks.py:533-541`) |
| 12 | Exit 0 leaves `in_progress` | It auto-continues, or ends `completed` |
| 15 | `reject_plan` | "Rejected" is an iterate request, not a terminal state |

Claims 1, 6 and 13 were only partly true, and only the true parts were filed.
That's eight entries for six rejections because 7 and 9 overlap with filed
issues rather than being wrong outright.

Lesson for the next audit: agy's report had many wrong function names and
line numbers. Every coder-reported instance needs independent verification
before filing, which is what the plan required.

## Open questions (need-check, not filed)

- **CFactory:**
  - card settlement runs only on events, and `stalled` isn't in the stuck set
    (N1);
  - list endpoints may hide failures (N2);
  - a poll can regress a terminal state (N3);
  - a plan-child node shows "completed" while its tests still run (N4);
  - the poll loop and WebSocket errors are logged at debug only (N5).
- **PFactory:**
  - the triager completion webhook fires only on triaged, and its reader is
    outside the repo;
  - a spec-creation failure is treated as success;
  - a stop shows `backlog` live but `human_review` after refresh;
  - delegation reports "delegated" on failure.
- **AIFactory:** QA approve/reject writes only the worktree plan.

## `fix-stuck-tasks.py`: what each repair says about the source

The script is forked into AIFactory, PFactory and TFactory, about 270 lines
each. It repairs only `implementation_plan.json` / `test_plan.json` and
`review_state.json`, never control files, `status.json`, durable rows or
`task_logs.json`.

| Repair | Upstream write that should have prevented it |
|---|---|
| Missing plan (reported, not repaired) | The terminal helper's missing-plan write (AIFactory `agent_service.py:442-493`). PFactory's `_update_plan_status` returns early when the file is missing |
| Creates `review_state.json` | `human_review` writers that skip review-state creation (PFactory `qa.py:121-128`, `agent_service.py:362-366`, `plan.py:141-144`). Risk: `approved:false` reads as "awaiting approval" |
| Backlog with subtask progress → in_progress | Raw JSON writers that bypass `update_status_from_subtasks` (PFactory `subtask.py:97`, `session.py:133`, `execution.py:655`). The reader already derives this status itself |
| Invalid status → in_progress | Rewrites terminal values such as `failed` back to running. **Filed as [Factory#3589](https://github.com/olafkfreund/Factory/issues/3589)** |

It does not repair the restart-mid-run state (PFactory#863, TFactory#1368)
or AIFactory#1771.

## What would prevent recurrence

These come from the issue and are unchanged. A structural guard is a separate
task, to be decided from these findings.
1. A terminal status must not depend on an artifact the outcome can prevent.
2. Every `on_done` needs its `on_fail` reviewed.
3. A dropped terminal write must be loud.
4. Test the wiring, not the helper.

The recurring shapes in these findings:
- **Cancellation is not an exception.** `except Exception` misses
  `CancelledError`: PFactory#860 and #863, TFactory#1368.
- **Two stores, one reader.** CFactory#478, PFactory#862, TFactory#1366.
- **Deletion presented as success.** CFactory#479 and #480.
