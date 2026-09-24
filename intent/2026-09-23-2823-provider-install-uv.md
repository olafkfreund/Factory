---
status: approved
issue: 2823
author: olafkfreund
---

# Intent: provider install works again, without putting pip back

## Problem

The "install / update provider" action for pip-kind runtimes (for example
`claude-agent-sdk`) cannot work in PFactory or TFactory. `install_argv` builds

```python
[sys.executable, "-m", "pip", "install", "--upgrade", spec]
```

and `sys.executable` is the service venv, which has no pip. Measured in both
live pods, 2026-09-23:

```
pfactory / tfactory:  python -m pip --version -> No module named pip
                      uv                      -> /usr/sbin/uv   (uv 0.12.16)
                      ensurepip               -> 26.2.1 available
```

pip was removed from the runtime images on 2026-09-03..05 (PFactory#681,
TFactory#1284, AIFactory#1482) to clear the pip-vendored-SBOM HIGHs. Factory#858
warned that this call site depended on it; the removal went ahead anyway.

`run_install` does not crash — it returns a non-zero `InstallResult` — so the
feature is quietly dead rather than loudly broken, and has been for three weeks.

Call sites, measured on `origin/dev`:

- `PFactory apps/backend/provider_runtime.py:368`
- `TFactory apps/backend/provider_runtime.py:355`

Not affected: TFactory's `agents/evaluator.py` pip calls run inside a fresh
`venv.create(..., with_pip=True)`, where `ensurepip` still bootstraps pip.
AIFactory has no runtime pip install.

## Proposed outcome

Clicking "install / update provider" installs or upgrades the named package into
the service venv again, on both services, without reintroducing pip into the
runtime image.

## Affected users and systems

- Anyone using the provider install/update action in the PFactory or TFactory
  portals.
- The service venv of two **running** services — this changes what is installed
  into a live process's interpreter.
- Not AIFactory, and not TFactory's evaluator lane.

## Constraints

- **Must not reintroduce pip** into the runtime image: that is what #858
  removed, and the SBOM findings would come back.
- **Must not disturb pinned transitive dependencies.** Measured hazard: a
  literal port to `uv pip install --upgrade <spec>` resolves the whole
  environment and would move `starlette` from `1.3.1` to `1.7.0`. That pin is
  deliberate — fastapi 0.137 / starlette 1.7 broke routing fleet-wide. The
  constrained form `uv pip install --python <venv> --upgrade-package <package>
  <spec>` — the bare package NAME for `--upgrade-package`, the (optionally
  pinned) requirement as the argument — moves only the requested package (verified by dry run in the pod:
  `claude-agent-sdk 0.2.157 -> 0.2.158`, everything else untouched).
- The two services must stay consistent: this is the same function in both
  repos, and divergence here is how the fleet gets two behaviours for one
  feature.
- If uv is ever absent, the action must fail **loudly** with a message naming
  the cause, not return a non-zero result nobody reads — the failure mode that
  hid this for three weeks.

## Open questions

1. **Does anything else assume pip in the service venv?** I checked
   `provider_runtime.py` and the evaluator in both repos; a wider sweep of the
   portal/API surface should confirm before changing behaviour.
2. **Should an install be allowed to move transitive dependencies at all?**
   `--upgrade-package` says no. That is stricter than the original `pip install
   --upgrade`, and arguably more correct for a running service — but it means a
   provider needing a newer shared dependency will fail rather than silently
   upgrade it. I think failing is right; it should be a deliberate choice.
3. **Verification depth.** A dry run in the pod proves the command shape. Proving
   the feature end to end means actually installing into a live service venv,
   which mutates a running pod. Acceptable on one service as evidence, or should
   this be proven on a scratch venv only?
