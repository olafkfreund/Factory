#!/usr/bin/env python3
"""A linter that never ran must fail the ratchet, not read as "no violations".

PFactory#455 (ruff), same shape found and fixed in TFactory#951. Swept across
the fleet because two repos finding it independently makes it a class rather
than an instance: a subprocess whose stdout is read for results while its
``returncode`` is ignored.

``ruff check`` exits 0 clean, 1 with violations, and >=2 on its OWN failure -
binary missing, config parse error, bad argv - writing nothing to stdout. A
CLEAN run prints ``[]``, never nothing. So empty stdout was never the clean
case, and treating it as one let both sides of the base-vs-head comparison come
back 0 - the cause is environmental, so it hits base and head alike - and the
gate report "no regression" having measured nothing.

``mypy`` has the same three-way exit code with one wrinkle: it also exits 2 on a
BLOCKING error (a syntax error in the file under test). That case still emits an
error line, so it is counted and gated normally; only a failed run that produced
no error line at all is treated as "did not run".

The controls are the assertions with teeth in the other direction. A guard that
fired on every non-zero exit would break the ordinary "violations found" path
(exit 1), and for mypy it would abort the ratchet on a syntax error rather than
blocking it as the regression it is.
"""

from __future__ import annotations

import pytest

# scripts/ is put on sys.path by tests/conftest.py.
import ratchet_lint as rl

_FILE = "scripts/check_factory_github_drift.py"


class _Res:
    """The subset of CompletedProcess the ratchet reads."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _stub(monkeypatch: pytest.MonkeyPatch, res: _Res) -> None:
    """Replace the tool invocation with *res*, leaving the rest of the run real."""
    monkeypatch.setattr(rl, "_run", lambda *_a, **_k: res)


# --------------------------------------------------------------------------- #
# ruff                                                                         #
# --------------------------------------------------------------------------- #


def test_ruff_own_failure_exits_rather_than_reporting_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, _Res(2, stderr="error: invalid value for '--config <CONFIG_OPTION>'"))
    with pytest.raises(SystemExit) as exc:
        rl.ruff_counts("x = 1\n", _FILE)
    assert exc.value.code == 2


def test_ruff_failure_surfaces_stderr_for_diagnosis(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub(monkeypatch, _Res(2, stderr="does not point to a configuration file"))
    with pytest.raises(SystemExit):
        rl.ruff_counts("x = 1\n", _FILE)
    assert "does not point to a configuration file" in capsys.readouterr().err


def test_ruff_clean_file_still_counts_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    # Control: exit 0 with "[]" is ruff saying "checked it, nothing wrong".
    _stub(monkeypatch, _Res(0, stdout="[]"))
    assert rl.ruff_counts("x = 1\n", _FILE) == {}


def test_ruff_violations_are_still_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    # Control: exit 1 is the ordinary "found something" path, not a failure.
    _stub(monkeypatch, _Res(1, stdout='[{"code": "S101"}, {"code": "S101"}]'))
    assert rl.ruff_counts("x = 1\n", _FILE)["S101"] == 2


# --------------------------------------------------------------------------- #
# mypy                                                                         #
# --------------------------------------------------------------------------- #


def test_mypy_own_failure_exits_rather_than_reporting_zero_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, _Res(2, stderr="mypy: error: Cannot find config file 'mypy.ini'"))
    with pytest.raises(SystemExit) as exc:
        rl.mypy_count("x = 1\n", _FILE, "scripts")
    assert exc.value.code == 2


def test_mypy_failure_surfaces_stderr_for_diagnosis(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub(monkeypatch, _Res(2, stderr="mypy: error: unrecognized arguments: --bogus"))
    with pytest.raises(SystemExit):
        rl.mypy_count("x = 1\n", _FILE, "scripts")
    assert "unrecognized arguments" in capsys.readouterr().err


def test_mypy_clean_file_still_counts_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    # Control: exit 0 with no error lines is a genuinely clean file.
    _stub(monkeypatch, _Res(0, stdout="Success: no issues found in 1 source file\n"))
    assert rl.mypy_count("x = 1\n", _FILE, "scripts") == 0


def test_mypy_blocking_error_is_counted_not_treated_as_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Control with teeth: a syntax error exits 2 as well, but still emits an
    # error line. Keying the guard on the exit code alone would abort the
    # ratchet here instead of blocking the regression.
    _stub(monkeypatch, _Res(2, stdout="_ratchet_x__drift.py:1: error: invalid syntax  [syntax]\n"))
    assert rl.mypy_count("x = 1\n", _FILE, "scripts") == 1


def test_mypy_errors_are_still_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    # Control: exit 1 is the ordinary "found something" path.
    out = (
        "_ratchet_x__drift.py:3: error: Function is missing a type annotation  [no-untyped-def]\n"
        "_ratchet_x__drift.py:9: error: Returning Any from function  [no-any-return]\n"
    )
    _stub(monkeypatch, _Res(1, stdout=out))
    assert rl.mypy_count("x = 1\n", _FILE, "scripts") == 2
