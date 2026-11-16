---
status: draft
issue: 1960
spec: spec/2026-11-16-1960-agent-attribution-signals.md
coders:
  1: lead   # small tricky logic across 3 builders; one worktree
  2: lead
  3: lead
  4: lead
  5: lead
reviewers:
  - codex   # final codex review --base origin/<base> per repo
---

# Plan: agent and originator on every emitted signal and agent PR

Approved decisions (spec): additive nullable `agent_identity` and `originator`
keys, always present, values copied unchanged from where each service records
them. No gitops change (flag already on, factory-gitops#326; deployed image
sha-1c4cc96 predates AIFactory#2015, live pod check is a post-release owner
action). Out of scope: PFactory `agents/triager.py` legacy callback; the
`.billing` relative-import bug in the standalone completion load.

## Steps

All worktrees under scratchpad `teams/f1960id/<Repo>`; rebase on `origin/<base>`
before implementing and before the last push.

1. AIFactory `apps/web-server/server/services/completion.py`: add
   `_read_attribution(spec_dir)` next to `_read_tenant_id`; add `originator` and
   `agent_identity` kwargs (default None) to `build_completion_event`,
   `build_worker_event`, `build_worker_progress_event`, always setting both keys;
   pass the helper's values from `emit_terminal_completion`, `emit_usage_snapshot`,
   `emit_worker_completion`, `emit_worker_progress`. Test in
   `apps/web-server/tests/test_completion_emitter.py`: populated, null, garbled
   requirements.json, all four emit paths. Check: `pytest` those files.
   Traps: no relative import in the helper; vendored files untouched.
2. AIFactory `apps/web-server/server/services/pr_endgame.py::_pr_title_body`:
   append `Authored by agent: ...` / `Originator: ...` lines (single printable
   line, skipped if empty/absent). Test in `apps/web-server/tests/test_pr_endgame.py`
   (values, none, newline-bearing). Traps: the evidence-marker scrub stays.
3. AIFactory `apps/backend/pfactory/tfactory_client.py::build_ingest_payload`:
   add `originator` / `agent_identity` from `req` to the payload when set; test
   alongside `test_tfactory_client_issue.py`. Traps: plain imports, ruff.
4. PFactory `apps/backend/plan/completion.py::build_completion_event`: set both
   keys from the session; update `tests/test_plan_completion.py`.
5. TFactory: `SpecIngestRequest` optional fields in `apps/web-server/server/routes/specs.py`,
   forward in the `create_spec_ingest_workspace` call; persist in
   `apps/backend/agents/tools_pkg/tools/task_control.py` source dict; set both in
   `agents/triager.py::_build_completion_envelope`; add to `CompletionEnvelope`.
   Tests: ingest-to-source.json and envelope with/without. Traps: contract-surface
   fields are optional; vendored `artifact_store.py` untouched.
6. Per repo: run the repo's lint and the touched tests, `codex review --base
   origin/<base>`, fix confirmed findings (max 2 rounds), open PRs, tick #1960.

## Tests

Touched test files per repo pass; ruff clean; repo CI green on the head SHA.

## Rollback

Revert the PRs; keys are additive so consumers are unaffected either way.
