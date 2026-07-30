#!/usr/bin/env python3
"""The hub's lint scope covers tests/, and the ratchet can express that scope.

Factory#493. Until this landed, `tests/` was outside every lint gate the repo
has: not `ruff check` (the ratchet ran `--package scripts`), not
`ruff format --check` (it ran `scripts/` only). Eighteen suites were checked by
nothing — and since Factory#496 wired seventeen of them into CI they include the
comparators of all three blocking fleet-wide drift gates, so they are
load-bearing code.

The irony #493 was filed over, corrected by measurement: `ratchet_lint` carries a
deliberate, tested carve-out relaxing the untyped-def bar for test files (#403),
and with `--package scripts` the only file in the hub that could exercise it was
`scripts/test_model_probe.py` — the seventeenth test, and the one that does not
live in `tests/`.

Two rules are locked here, and the second is the one with teeth: the scope is
CONFIGURED, not just supported. A `--package` that accepts a list while CI keeps
passing `scripts` is the same always-green gate one level up.

No `@pytest.mark.parametrize` on purpose. The code-quality job installs ruff and
mypy and nothing else, so `pytest` is an untyped import there and the decorator
would make every case it wraps untyped under `mypy --strict` — a net-new error on
a brand-new file, which the ratchet blocks outright. A plain loop has no such
dependency.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# scripts/ is put on sys.path by tests/conftest.py.
import ratchet_lint as rl
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "code-quality.yml"


def test_package_list_parses() -> None:
    cases = [
        ("scripts", ["scripts"]),
        ("scripts,tests", ["scripts", "tests"]),
        ("scripts, tests", ["scripts", "tests"]),
        # A trailing/doubled comma must not become an empty segment: Path("")
        # is Path("."), which would widen the gate to the whole repo (including
        # the prototypes/, backups/ and review/ trees the config excludes).
        ("scripts,,tests,", ["scripts", "tests"]),
    ]
    for value, expected in cases:
        assert rl.packages(value) == expected, value


def test_mypypath_carries_every_scoped_dir() -> None:
    """A changed test imports the module it gates, which lives in scripts/.

    Scoping MYPYPATH to the file's own directory would leave that import
    unresolved, so every scoped dir has to be on the path at once.
    """
    env = rl._mypy_env("scripts,tests")
    parts = env["MYPYPATH"].split(os.pathsep)
    assert "scripts" in parts
    assert "tests" in parts


def _workflow() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(_WORKFLOW.read_text())
    return loaded


def test_ci_gates_the_tests_directory() -> None:
    """THE ASSERTION WITH TEETH.

    Supporting a comma list changes nothing on its own — the defect #493
    describes is a scope that is configured too narrowly. If someone narrows
    PACKAGE_DIR back to `scripts`, tests/ silently stops being linted again and
    every other test in this file still passes.
    """
    scope = rl.packages(str(_workflow()["env"]["PACKAGE_DIR"]))
    assert "tests" in scope, "the ruff/mypy ratchet must gate tests/"
    assert "scripts" in scope, "widening must not have dropped scripts/"


def test_ci_format_checks_the_tests_directory() -> None:
    """`ruff format --check` is whole-tree and blocking, so it is checked apart.

    It cannot grandfather anything: a directory can only be added once clean.
    That makes it the easiest of the two to quietly leave behind.
    """
    commands = [
        step.get("run", "")
        for job in _workflow()["jobs"].values()
        for step in job.get("steps", [])
        if "ruff format --check" in step.get("run", "")
    ]
    assert commands, "no ruff format --check step found in code-quality.yml"
    assert any("tests/" in cmd for cmd in commands), (
        "ruff format --check must cover tests/; found: " + " | ".join(commands)
    )
