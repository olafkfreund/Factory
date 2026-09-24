---
status: approved
issue: 2823
spec: spec/2026-09-23-2823-provider-install-uv.md
---

# Plan: provider install runs through uv

## Approved decisions (self-contained)

- **Why.** `install_argv` builds `[sys.executable, "-m", "pip", ...]`, and the
  service venv has no pip (removed 2026-09-03..05 to clear vendored-SBOM HIGHs).
  The action has been dead for three weeks, failing as a non-zero
  `InstallResult` nobody reads. Measured in both live pods: no pip, `uv 0.12.16`
  at `/usr/sbin/uv`, `ensurepip 26.2.1`.
- **Fix.** `uv pip install --python <sys.executable> --upgrade-package <package>
  <spec>` in both PFactory and TFactory.
- **`--upgrade-package`, not `--upgrade`.** Measured hazard: plain `--upgrade`
  would move `starlette 1.3.1 -> 1.7.0`, a pin the fleet holds because fastapi
  0.137 / starlette 1.7 broke routing. The constrained form moved only
  `claude-agent-sdk 0.2.157 -> 0.2.158`.
- **Missing uv raises**, in the `InputRejectedError` family the function already
  uses, naming uv and this issue — a different failure class from "the install
  ran and failed".
- **Only `install_argv` changes.** Swept both repos: every other pip reference
  is message text, an ecosystem label, or runs in an interpreter that has pip
  (the evaluator's fresh venv, the Nix job's `--target` install).
- **Both repos in one sitting**, same diff, same tests, or the feature grows two
  behaviours.
- **No running service is mutated** to prove this: dry runs plus a throwaway
  venv.

## Steps

1. **PFactory `apps/backend/provider_runtime.py`:** replace the pip branch of
   `install_argv` with the uv argv; add the missing-uv raise.
   → verify: unit tests for the argv (with and without a version), the raise,
   and the untouched npm/gh branches.
2. **TFactory `apps/backend/provider_runtime.py`:** the identical change.
   → verify: the same tests, in that repo's suite.
3. **Live check, read-only, both pods:** run the new argv shape with
   `--dry-run`, and the `--upgrade` variant alongside it, recording that only
   the first leaves `starlette` alone.
4. **Live check, one pod:** create a throwaway venv from the service
   interpreter, run the real argv against it, confirm the package installs.
   Delete the venv.
5. **Gates, per repo:** `ruff check`, `ruff format --check` over the paths that
   repo's CI checks, `scripts/ratchet_lint.py --base origin/dev` with its
   `--package` flags, and the full suite.
6. **Two PRs**, one per repo, each carrying the live evidence. Land both before
   closing #2823.

## Tests

```sh
# per repo
apps/backend/.venv/bin/python -m pytest tests/ -q -k provider_runtime
apps/backend/.venv/bin/ruff check apps/backend tests scripts
apps/backend/.venv/bin/ruff format --check <repo's CI path list>
apps/backend/.venv/bin/python scripts/ratchet_lint.py --base origin/dev \
  --package apps/backend --package apps/web-server --package scripts
```

Expected: the new tests fail before the change and pass after; restoring the
pip argv fails the missing-uv test; the dry run shows one package moving.

## Rollback

Revert the two PRs. `install_argv` returns to the pip argv, which means the
action goes back to being dead — no worse than today, and no service state to
unwind. Nothing else calls this function.
