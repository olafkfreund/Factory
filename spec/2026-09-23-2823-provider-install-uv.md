---
status: approved
issue: 2823
intent: intent/2026-09-23-2823-provider-install-uv.md
---

# Spec: provider install runs through uv, and moves only what was asked for

## Open questions, resolved

**1. Does anything else assume pip in the service venv?** No. Swept both
services' `apps/backend` and `apps/web-server` for `-m pip`, `pip install` and
`ensurepip`:

| Hit | Verdict |
| --- | --- |
| `provider_runtime.install_argv` (PFactory:368, TFactory:355) | **the only service-venv pip execution** |
| TFactory `agents/evaluator.py:401,416,435` | runs in a fresh `venv.create(with_pip=True)` — has pip |
| TFactory `agents/nix_env.py:690` | runs in the Nix job's interpreter with `--target`, not the service venv |
| `tools_pkg/http_client.py`, `core/workspace/display.py`, `core/worktree.py:697` | message/suggestion strings, never executed here |
| `analysis/analyzers/framework_analyzer.py`, `agents/dependency_review.py:91` | the literal `"pip"` as an ecosystem label |

**2. May an install move transitive dependencies?** No. It installs or upgrades
the named package only. Rationale below.

**3. Verification depth.** Dry runs in both live pods, plus a real install into
a throwaway venv built from the service venv's own interpreter. No mutation of
a running service's site-packages.

## Design

`install_argv`'s `pip` branch, in both repos, becomes:

Pseudocode — each repo raises **its own** existing exception, see below:

```python
uv = shutil.which("uv")
if uv is None:
    raise <that repo's install-rejection error>(
        f"cannot install {rt.name}: uv is not on PATH and the runtime image "
        "ships no pip, so a pip-kind provider cannot be installed "
        "(Factory#2823)"
    )
return [
    uv_path, "pip", "install",
    "--python", sys.executable,
    "--upgrade-package", rt.package,
    spec,
]
```

- `--python sys.executable` targets the service venv explicitly rather than
  whatever interpreter uv would pick.
- `--upgrade-package <package>` is the whole point: it upgrades the named
  package and leaves every other pin alone. Measured in the TFactory pod, a
  plain `--upgrade` would have moved `starlette` `1.3.1 -> 1.7.0`; the
  constrained form moved only `claude-agent-sdk 0.2.157 -> 0.2.158`.
- `spec` keeps today's shape: `package==version` when a version is given,
  bare `package` otherwise.
- The npm and gh branches are untouched.

### Failing loudly when uv is absent

Today a missing tool produces a non-zero `InstallResult` that nothing reads —
which is why this went unnoticed for three weeks. A missing uv now raises,
using **whichever exception that repo's `install_argv` already raises** for an
unmanaged runtime: `InputRejectedError` in PFactory, plain `ValueError` in
TFactory, which its route converts to a client error. Matching each repo's own
convention beats importing one repo's exception into the other. Either way the
API surfaces a message naming the cause — deliberately a different failure
class from "the install ran and failed".

### Why the two repos change identically

`provider_runtime.py` is the same module in both services. Divergence here is
how one feature grows two behaviours, so both get the same diff in the same
sitting, and the tests are the same tests.

## Alternatives rejected

- **Put pip back in the image.** Reverses PFactory#681 / TFactory#1284 /
  AIFactory#1482 and reinstates the vendored-SBOM HIGHs that #858 cleared.
- **`python -m ensurepip` then pip.** Works (ensurepip 26.2.1 is present), but
  it installs pip into the service venv at runtime — the thing the image
  removals were for — and leaves it there.
- **`uv pip install --upgrade <spec>`.** The literal port. Measured to move
  `starlette` off a pin the fleet holds deliberately; an "install provider"
  click must not restart-break the service it runs in.
- **`--no-deps`.** Would avoid collateral, but a genuinely new dependency of
  the provider would then be missing and the failure would appear later, at
  import time, far from the cause.
- **Leave it dead and document it.** The action is in the portal; a button that
  cannot work is worse than no button.

## Risks

- **A provider that needs a newer shared dependency now fails** rather than
  silently upgrading it. That is the intended trade: the failure names the
  conflict instead of moving a pin under a running service. Its message must
  therefore be legible, which the test below pins.
- **uv's resolver differs from pip's.** Mitigated by targeting the venv
  explicitly and constraining to one package; the dry runs above show the
  resolution it actually performs.
- **uv could disappear from a future image.** That is now a loud failure with a
  named cause rather than a silent one.
- **Two repos, one change.** If only one lands, the feature behaves differently
  per service. Mitigated by landing both before closing the issue.

## Verification

1. Unit, both repos: `install_argv` for a pip-kind runtime returns the uv argv
   with `--python`, `--upgrade-package` and the spec; with a version, the spec
   is `package==version`.
2. Unit, both repos: uv missing → raises, with a message naming uv and #2823.
   **Mutation:** restore the old pip argv and this test must fail.
3. Unit: the npm and gh branches are byte-identical to today's output.
4. Live, both pods, read-only: `--dry-run` with the new argv shape shows only
   the named package moving; the same command with `--upgrade` instead shows
   `starlette` moving, which is the hazard being avoided.
5. Live, one pod: a real install into a **throwaway** venv created from the
   service interpreter, proving the argv works end to end without mutating a
   running service.
6. Gates per repo: ruff, ruff format, the strict ratchet with its `--package`
   flags, and the full test suite.
