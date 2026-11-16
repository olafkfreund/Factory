"""Quarterly access-review issue opener (Factory#312)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "access_review_reminder.sh"


def _run(tmp_path: Path, existing: str, **env: str) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run the script with a stub ``gh`` that lists ``existing`` and logs ``create``."""
    log = tmp_path / "created"
    stub = tmp_path / "gh"
    stub.write_text(
        "#!/bin/sh\n"
        'case "$2" in\n'
        f'  list) printf "%s\\n" "{existing}" ;;\n'
        f'  create) shift 2; echo "$*" >"{log}"; cat "${{4:-/dev/null}}" >/dev/null ;;\n'
        "esac\n"
    )
    stub.chmod(0o755)
    base = {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "TEMPLATE": str(ROOT / "docs/compliance/access-review-record-template.md"),
    }
    proc = subprocess.run(  # noqa: S603
        ["/bin/sh", str(SCRIPT)],
        env={**base, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    return proc, log.read_text() if log.exists() else ""


@pytest.mark.parametrize(
    ("year", "month", "quarter"),
    [
        ("2027", "01", "2026-Q4"),
        ("2027", "04", "2027-Q1"),
        ("2027", "07", "2027-Q2"),
        ("2027", "10", "2027-Q3"),
    ],
)
def test_opens_the_quarter_that_just_ended(
    tmp_path: Path, year: str, month: str, quarter: str
) -> None:
    proc, created = _run(tmp_path, "", YEAR=year, MONTH=month)
    assert proc.returncode == 0, proc.stderr
    assert f"--title Access review {quarter}" in created


def test_existing_issue_is_left_alone(tmp_path: Path) -> None:
    proc, created = _run(tmp_path, "Access review 2026-Q4", YEAR="2027", MONTH="01")
    assert proc.returncode == 0
    assert "exists" in proc.stdout
    assert created == ""


def test_other_title_does_not_count(tmp_path: Path) -> None:
    proc, created = _run(tmp_path, "Access review 2026-Q3", YEAR="2027", MONTH="01")
    assert proc.returncode == 0
    assert "Access review 2026-Q4" in created


def test_non_quarter_month_needs_explicit_quarter(tmp_path: Path) -> None:
    proc, created = _run(tmp_path, "", YEAR="2027", MONTH="02")
    assert proc.returncode != 0 and created == ""
    proc, created = _run(tmp_path, "", YEAR="2027", MONTH="02", QUARTER="2026-Q4")
    assert proc.returncode == 0 and "Access review 2026-Q4" in created


def test_bad_quarter_is_rejected(tmp_path: Path) -> None:
    proc, created = _run(tmp_path, "", QUARTER="2026-Q5")
    assert proc.returncode != 0 and created == ""
