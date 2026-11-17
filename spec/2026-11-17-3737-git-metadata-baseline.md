---
status: draft
issue: 3737
intent: intent/2026-11-17-3737-git-metadata-baseline.md
---

# Spec: git metadata baseline for PFactory and TFactory

## Design

1. Hub `shared/factory-sandbox/agent_sandbox/git_metadata.py`: the AIFactory module minus
   the base-SHA records and minus its two service imports. The dangerous-key predicate is a
   small copy of AIFactory `_is_dangerous_git_config`; the child env for its own git calls is
   `PATH` and `HOME` only; baselines go to `$FACTORY_GIT_BASELINE_DIR`, default
   `~/.factory/git-baselines`; the late-baseline warning goes to stderr. API:
   `snapshot`, `record_baseline`, `record_worktree_baseline`, `check_git_metadata`,
   `GitMetadataChangedError`, and `python -m agent_sandbox.git_metadata --rebaseline PATH`.
2. The drift checker lists `git_metadata.py` in `CANONICAL_FILES` and skips a listed file
   that an older pinned canonical lacks, so a service still on the old pin keeps passing.
3. PFactory and TFactory: `core/worktree.py` `create_worktree` records the project and
   worktree baselines after `git worktree add` (a failure raises `WorktreeError`, as in
   AIFactory). `core/child_env.merge_driver_pins` gets `baseline: bool = False`; when true it
   passes `check_git_metadata` as `check`. It is true in `core/workspace/git_utils.py`
   (two sites) and `tools/git_writer.py`; the web-server git helpers keep `False`.
4. AIFactory vendors the new file (the gate requires it) and does not use it.

## Alternatives rejected

- Per-service copy of `core/git_metadata.py`: three diverging copies of a security check.
- Bind in every `merge_driver_pins` call: the web UI would fail after a user edits their
  own repo config.
- Fail closed when no baseline exists: AIFactory deliberately takes a late baseline with a
  warning (#1832, owner decision); PF/TF match it so a repo without a worktree still works.

## Risks

- The drift checker skips only `git_metadata.py` when an older pinned canonical lacks it;
  every other listed file stays mandatory.
- A user who changes `merge.*`, `diff.*` or `filter.*` in the project repo after a
  baseline is recorded gets a refusal in PF/TF merge and write paths until they run the
  re-baseline command. Same behaviour as AIFactory.
- `FACTORY_GIT_BASELINE_DIR` / `~/.factory` must be writable by the control plane;
  otherwise `create_worktree` fails with a clear message. The agent's HOME is the private
  AgentHome, a different directory, so the baseline is not in the agent's tree. A process of
  the same UID could still delete it (the next check then takes a late baseline); the owner
  accepted same-UID reads with `PR_SET_DUMPABLE=0` and deferred the UID split (#3737), so this
  is a documented residual, not a new one.
- Check and use are not atomic: a writer that adds a key after the check and before the git
  call is not caught. The empty merge/filter pins cover keys present at probe time only.
  Same window as AIFactory.
- Merge window: services pin a hub SHA that must be on hub `main`, so the service PRs wait
  for the hub PR.

## Verification

The `--rebaseline` hint names the checked worktree. Config values keep their order, so a
reordered duplicate is detected. Hub tests (`shared/factory-sandbox/tests/test_git_metadata.py`): an untouched repo passes;
a tampered `merge.*.driver`, `filter.*.smudge`, `diff.*.textconv`, `core.fsmonitor` or
`info/attributes` is detected; a re-baseline accepts the change; `merge_driver_pins` with
the check bound refuses a tampered repo. Service tests: `create_worktree` records, and a
tampered worktree makes the bound `merge_driver_pins` raise. Drift script exit 0 per service.
