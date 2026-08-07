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
# Factory#600 — a partial count is not a measurement                           #
# --------------------------------------------------------------------------- #

# Captured verbatim from mypy 2.1.0 run on a file with FOUR real errors that
# imports a stub the declared --python-version cannot parse. mypy stops before
# type-checking, so three of the four are never found; the one line naming the
# target is left over from module discovery.
_BROKEN_IMPORT_STDOUT = (
    "target.py:2: error: Cannot find implementation or library stub for module named "
    '"nosuchmodule_xyz"  [import-not-found]\n'
    "target.py:2: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html"
    "#missing-imports\n"
    "lib/brokenstub.pyi:1: error: Type statement is only supported in Python 3.12 and "
    "greater  [syntax]\n"
)


def test_partial_count_from_an_unparseable_import_is_not_a_measurement() -> None:
    # THE DEFECT (Factory#600). Exit 2, one error attributed to the target, and
    # the arm meant for a blocking error in the target waves it through — while
    # mypy stopped at an IMPORT and the file's real count is 4. PFactory gated 5
    # files this way, TFactory 3, one of them at 1 against a real 28.
    with pytest.raises(SystemExit) as exc:
        rh.require_tool_ran("mypy", _res(2, stdout=_BROKEN_IMPORT_STDOUT), measured=1)
    assert exc.value.code == 2


def test_partial_count_failure_names_the_files_it_blamed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        rh.require_tool_ran("mypy", _res(2, stdout=_BROKEN_IMPORT_STDOUT), measured=1)
    err = capsys.readouterr().err
    assert "partial count" in err
    assert "lib/brokenstub.pyi" in err


def test_blocking_error_in_the_file_under_test_is_still_measured() -> None:
    # Control with teeth, the shape the arm exists for: mypy exits 2, but every
    # error line names ONE file, so nothing was left unchecked elsewhere. A
    # guard that fired on any exit-2 run would abort the ratchet here instead of
    # gating the syntax error as the regression it is.
    out = "target.py:1: error: invalid syntax  [syntax]\n"
    rh.require_tool_ran("mypy", _res(2, stdout=out), measured=1)


def test_clean_file_with_a_broken_import_is_not_newly_hard_failed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The inverse case. A file with NO errors of its own whose import will not
    # parse counts 0, so it lands in the pre-existing zero-count arm — the same
    # verdict, with the same message, as before this change. TFactory measured
    # 21 such files; turning them into a NEW class of block would be worse than
    # the undercount, so the diagnostic must still read "did not run".
    out = "lib/brokenstub.pyi:1: error: Type statement is only supported in Python 3.12\n"
    with pytest.raises(SystemExit) as exc:
        rh.require_tool_ran("mypy", _res(2, stdout=out), measured=0)
    assert exc.value.code == 2
    assert "did not run" in capsys.readouterr().err


def test_ruff_own_failure_is_unaffected() -> None:
    # ruff writes nothing on its own failure, so there is no path to blame and
    # the default measured=0 keeps the original arm.
    with pytest.raises(SystemExit) as exc:
        rh.require_tool_ran("ruff", _res(2, stderr="error: invalid value for '--config'"))
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
