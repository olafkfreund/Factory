#!/usr/bin/env python3
"""RFC-0006 VAL execution engine (reference implementation, sub-task #74).

Runs the verification ladder produced by #73 (`verification_profiles`) and feeds
the real results through the #72 gate (`verification_gate`) — closing the loop:

    profiles.plan_verification()  ->  run_verification(plan, backend)  ->  honest block

A *backend* is just a callable `run(level, commands) -> (ok: bool, output: str)`.
Two are provided:
  - `nix_backend(env_pkgs)` — runs each command inside an RFC-0005 Nix sandbox
    (`nix shell nixpkgs#<pkg> ... -c bash -lc <cmd>`). A real sandbox, available
    now; needs nothing from the provisioning epic (#61).
  - the cluster container backend (TFactory `docker_runner` -> shared
    `factory-sandbox`) lands under #61 Phase 1 and implements the same signature.

`run_verification` never decides the assurance level itself — it records what
passed/failed and hands off to the gate, which recomputes `achieved_level`
(a failure caps the ceiling) and forbids overclaiming. Pure orchestration +
dependency-free, so each service vendors it.

Run directly for the self-tests: `python3 scripts/verification_runner.py`.
"""

from __future__ import annotations

import subprocess
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from verification_gate import normalize_verification  # noqa: E402


def run_verification(plan: dict, backend) -> dict:
    """Execute the achievable levels of a #73 plan and return an honest block.

    `plan` is the output of verification_profiles.plan_verification().
    `backend(level, commands) -> (ok, output)` runs the commands in a sandbox.
    """
    block = {
        "target_level": plan["target_level"],
        "achieved_level": plan["achievable_level"],  # gate will recompute from truth
        "levels": [],
    }
    for lvl in plan["levels"]:
        entry = {"level": lvl["level"]}
        if lvl.get("status") == "planned":
            ok, output = backend(lvl["level"], lvl["commands"])
            if ok:
                entry.update(
                    status="passed", ran=lvl["commands"], evidence=(output or "ok").strip()[:200]
                )
            else:
                entry.update(
                    status="failed",
                    ran=lvl["commands"],
                    reason="command failed: " + (output or "").strip()[:200],
                    risk=lvl.get("risk", "behavior unproven"),
                )
        else:
            entry.update(status="not_run", reason=lvl["reason"])
            if "risk" in lvl:
                entry["risk"] = lvl["risk"]
        block["levels"].append(entry)
    # The gate is the safety net: it recomputes achieved_level from the real
    # statuses (so a failed level caps it) and writes the honest claim.
    return normalize_verification(block)


def nix_backend(env_pkgs: list[str], cwd: str = "."):
    """A real RFC-0005 sandbox backend: run each command in `nix shell`."""

    def run(level: str, commands: list[str]):
        outs = []
        for cmd in commands:
            wrapped = (
                ["nix", "shell"] + [f"nixpkgs#{p}" for p in env_pkgs] + ["-c", "bash", "-c", cmd]
            )
            r = subprocess.run(wrapped, cwd=cwd, capture_output=True, text=True)
            outs.append(r.stdout + r.stderr)
            if r.returncode != 0:
                return False, "\n".join(outs)
        return True, "\n".join(outs)

    return run


# --------------------------------------------------------------------------- #
def _test() -> None:
    from verification_profiles import plan_verification

    ans = ["roles/web/tasks/main.yml", "molecule/default/molecule.yml"]

    # Backend that "passes" only the given levels (deterministic, no external deps).
    def fake(pass_levels):
        return lambda level, cmds: (level in pass_levels, f"ran {cmds}")

    # 1. Env reaches VAL-2 (molecule); VAL-3 has no target -> honest gap, no overclaim.
    plan = plan_verification(ans, {"ansible", "molecule", "container_runtime"})
    out = run_verification(plan, fake({"VAL-0", "VAL-2"}))
    assert out["achieved_level"] == "VAL-2", out
    assert "VAL-3 not_run" in out["claim"] and not out["_gate"]["downgraded"], out

    # 2. VAL-2 command FAILS at runtime -> gate caps achieved at VAL-0 (failure floor).
    out = run_verification(plan, fake({"VAL-0"}))  # VAL-2 planned but fails
    by = {l["level"]: l for l in out["levels"]}
    assert by["VAL-2"]["status"] == "failed" and "command failed" in by["VAL-2"]["reason"]
    assert out["achieved_level"] == "VAL-0", out

    # 3. Only lint toolchain present -> VAL-0 runs/passes; VAL-2/3 stay not_run gaps.
    plan = plan_verification(ans, {"ansible"})
    out = run_verification(plan, fake({"VAL-0"}))
    assert out["achieved_level"] == "VAL-0"
    assert all(l.get("reason") for l in out["levels"] if l["status"] != "passed"), out

    print("verification_runner self-tests: 3 passed")


if __name__ == "__main__":
    _test()
