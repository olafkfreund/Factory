#!/usr/bin/env python3
"""Behaviour lock for the canonical ratchet rules (Factory#403, Factory#590).

``scripts/ratchet_helpers.py`` is the byte-exact drift-gated canonical every
service vendors, so a defect here reaches five repos and a fix here reaches five
repos. That is the point: the "did the linter actually run" rule used to be
restated inline in nine places, and correcting it cost five PRs and shipped one
half-fix on the way (PFactory#455, TFactory#951, Factory#590).

These tests are on the CANONICAL, not on any one ratchet. The per-repo
``test_ratchet_tool_failure.py`` suites still exist and still exercise each
service's own counters end to end — they prove the wiring; this proves the rule.

No ``@pytest.mark.parametrize``, per the convention ``tests/test_ratchet_scope.py``
records: the code-quality job installs ruff and mypy and nothing else, so under
``mypy --strict`` there ``pytest`` is an untyped import whose decorator makes
every case it wraps untyped. Plain loops instead.
"""

from __future__ import annotations

import subprocess

import pytest

# scripts/ is put on sys.path by tests/conftest.py.
import ratchet_helpers as rh


def _res(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["ruff"], returncode=returncode, stdout=stdout, stderr=stderr
    )


# --------------------------------------------------------------------------- #
# require_tool_ran                                                             #
# --------------------------------------------------------------------------- #


def test_normal_exit_codes_are_a_measurement() -> None:
    # 0 is "clean", 1 is "found something". Both mean the tool ran.
    for returncode in (0, 1):
        rh.require_tool_ran("ruff", _res(returncode, stdout="[]"))


def test_tool_own_failure_aborts_rather_than_reading_as_clean() -> None:
    # THE DEFECT. Exit >= 2 with nothing measured is the linter failing to run;
    # returning 0 findings from it makes base and head compare equal and the
    # gate report "no regression" having measured nothing.
    with pytest.raises(SystemExit) as exc:
        rh.require_tool_ran("ruff", _res(2, stderr="error: invalid value for '--config'"))
    assert exc.value.code == 2


def test_failure_surfaces_the_tool_output_for_diagnosis(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        rh.require_tool_ran("ruff", _res(2, stderr="does not point to a configuration file"))
    err = capsys.readouterr().err
    assert "did not run" in err
    assert "does not point to a configuration file" in err


def test_mypy_blocking_error_is_a_measurement_not_a_crash() -> None:
    # Control with teeth. mypy exits 2 on a syntax error too, but it NAMES the
    # file, so the caller counted it. Keying the guard on the exit code alone
    # would abort the ratchet here instead of blocking the regression.
    rh.require_tool_ran("mypy", _res(2, stdout="x.py:1: error: invalid syntax"), measured=1)


def test_mypy_failure_with_nothing_counted_still_aborts() -> None:
    # The other half of the same call: exit 2 having named no file at all.
    with pytest.raises(SystemExit) as exc:
        rh.require_tool_ran(
            "mypy", _res(2, stderr="mypy: error: Cannot find config file"), measured=0
        )
    assert exc.value.code == 2


# --------------------------------------------------------------------------- #
# is_test_file / ruff_stdin_argv — the two rules that came first (Factory#403)  #
# --------------------------------------------------------------------------- #


def test_test_paths_are_recognised() -> None:
    for path in ("tests/helpers.py", "apps/backend/tests/x.py", "test_thing.py", "a/b/x_test.py"):
        assert rh.is_test_file(path), path


def test_production_paths_are_not_test_files() -> None:
    # `latest.py` is the trap: it ENDS with "test.py" but is not "*_test.py".
    for path in ("scripts/ratchet_lint.py", "apps/backend/latest.py"):
        assert not rh.is_test_file(path), path


def test_ruff_argv_judges_the_real_path_not_a_temp_copy() -> None:
    argv = rh.ruff_stdin_argv("ruff.toml", "tests/helpers.py")
    assert "--stdin-filename" in argv
    assert argv[argv.index("--stdin-filename") + 1] == "tests/helpers.py"
    assert argv[-1] == "-"
