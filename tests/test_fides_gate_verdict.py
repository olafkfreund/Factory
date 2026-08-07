#!/usr/bin/env python3
"""Mutation table for the Fides change-gate verdict assertion (Factory#618).

Every fixture in ``tests/fixtures/fides_change_gate_verdicts.json`` is verbatim
output from a real Fides server (evidance-vault @1fc2aa6, driven by the real
``fides`` CLI against a real Postgres), and every one of them is a PASSING gate:
``"approved": true``, summary "safe to approve", ``fides change-gate`` exit 0.

They differ in exactly one thing -- who the committer is:

  =========================== ============================ ===========
  case                        committer                    fides exit
  =========================== ============================ ===========
  pr_time_four_eyes           dev@company.com                       0
  no_committer_supplied       ''                                    0
  committer_is_the_approver   alice@company.com  (== approver)      0
  committer_differs_only_by_case Alice@Company.com (same human)     0
  committer_is_github_noreply 12345+dev@users.noreply.github.com    0
  =========================== ============================ ===========

That is the defect: exit 0 is the same code for "compared nobody", "compared and
FAILED" and "compared and passed", because the server's ``approved`` is
``len(failed)==0 && len(missing)==0 && humanApprovers>=1`` and the
segregation-of-duties verdict is not an input to it.

So each case below holds the whole gate constant and changes only the identity.
One passes. The other four must be red, and they are red only because of
``scripts/fides_gate_verdict.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "fides_gate_verdict.py"
_FIXTURES = json.loads(
    (_REPO_ROOT / "tests" / "fixtures" / "fides_change_gate_verdicts.json").read_text(
        encoding="utf-8"
    )
)


def _run(gate: dict, tmp_path: Path, committer: str = "") -> subprocess.CompletedProcess[str]:
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(gate), encoding="utf-8")
    argv = [sys.executable, str(_SCRIPT), str(path)]
    if committer:
        argv += ["--committer", committer]
    return subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603


def test_every_fixture_is_a_gate_the_fides_cli_itself_passes() -> None:
    """The premise. If a fixture ever stops being a pass, the table proves nothing."""
    for name, gate in _FIXTURES.items():
        assert gate["approved"] is True, f"{name} is not a passing gate; the table is invalid"


def test_genuine_four_eyes_passes(tmp_path: Path) -> None:
    out = _run(_FIXTURES["pr_time_four_eyes"], tmp_path, "dev@company.com")
    assert out.returncode == 0, out.stderr
    # The pass path names who it compared, not just that it passed.
    assert "committer          dev@company.com" in out.stderr
    assert "approvers          alice@company.com" in out.stderr


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("no_committer_supplied", "committer identity unknown"),
        ("committer_is_the_approver", "is also an approver"),
        ("committer_differs_only_by_case", "is also an approver"),
        ("committer_is_github_noreply", "privacy-masked"),
    ],
)
def test_the_gate_passes_but_the_verdict_check_does_not(
    tmp_path: Path, case: str, expected: str
) -> None:
    out = _run(_FIXTURES[case], tmp_path)
    assert out.returncode == 1, f"{case} must be red: {out.stdout}{out.stderr}"
    assert expected in out.stderr
    # A failing run must not also claim OK: the header is printed after the check.
    assert "verdict OK" not in out.stderr


def test_a_gate_with_no_sod_payload_is_not_checked_rather_than_passed(tmp_path: Path) -> None:
    """An older server that returns no SoD payload must not read as a pass."""
    gate = dict(_FIXTURES["pr_time_four_eyes"])
    del gate["segregation_of_duties"]
    out = _run(gate, tmp_path, "dev@company.com")
    assert out.returncode == 1, out.stderr
    assert "not_checked" in out.stderr


def test_a_committer_the_run_did_not_supply_is_rejected(tmp_path: Path) -> None:
    """Guards a trail that already existed with somebody else's identity on it."""
    out = _run(_FIXTURES["pr_time_four_eyes"], tmp_path, "someone.else@company.com")
    assert out.returncode == 1, out.stderr
    assert "not the one under test" in out.stderr


def test_missing_deployer_alone_does_not_sink_the_pr_gate(tmp_path: Path) -> None:
    """A pull request has no deployer; that leg belongs to the deploy gate."""
    sod = _FIXTURES["pr_time_four_eyes"]["segregation_of_duties"]
    assert sod["violations"] == ["no deployer recorded"]
    assert sod["compliant"] is False  # the server says non-compliant...
    out = _run(_FIXTURES["pr_time_four_eyes"], tmp_path, "dev@company.com")
    assert out.returncode == 0, out.stderr  # ...and the PR gate still passes


def test_a_verdict_over_zero_controls_is_not_a_verdict(tmp_path: Path) -> None:
    """Coverage of zero controls is a risk score nobody could falsify."""
    gate = json.loads(json.dumps(_FIXTURES["pr_time_four_eyes"]))
    gate["passed"] = []
    out = _run(gate, tmp_path, "dev@company.com")
    assert out.returncode == 1, out.stderr
    assert "zero controls" in out.stderr


def test_a_held_gate_stays_red(tmp_path: Path) -> None:
    gate = json.loads(json.dumps(_FIXTURES["pr_time_four_eyes"]))
    gate["approved"] = False
    gate["recommendation"] = "hold"
    out = _run(gate, tmp_path, "dev@company.com")
    assert out.returncode == 1, out.stderr
    assert "hold" in out.stderr


@pytest.mark.parametrize("body", ["", "   ", "not json at all", "[]"])
def test_unreadable_gate_output_is_red(tmp_path: Path, body: str) -> None:
    """#541's lesson in a new place: producing nothing is not producing a pass."""
    path = tmp_path / "gate.json"
    path.write_text(body, encoding="utf-8")
    out = subprocess.run(  # noqa: S603
        [sys.executable, str(_SCRIPT), str(path)], capture_output=True, text=True, check=False
    )
    assert out.returncode == 1, out.stdout + out.stderr
