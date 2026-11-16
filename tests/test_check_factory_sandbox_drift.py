"""Tests for scripts/check_factory_sandbox_drift.py (Factory#3709)."""

from __future__ import annotations

from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import check_factory_sandbox_drift as gate

_REPO = Path(__file__).resolve().parents[1]


def test_builtin_self_test_passes() -> None:
    assert gate._self_test() == 0


def test_real_canonical_is_fully_listed() -> None:
    assert gate.check_drift(gate._DEFAULT_CANONICAL, gate._DEFAULT_CANONICAL) == []


def test_main_checks_a_copy(tmp_path: Path) -> None:
    for rel in gate.CANONICAL_FILES:
        (tmp_path / rel).write_bytes((gate._DEFAULT_CANONICAL / rel).read_bytes())
    assert gate.main(["--service", str(tmp_path)]) == 0
    (tmp_path / "env.py").write_text("# drifted\n")
    assert gate.main(["--service", str(tmp_path)]) == 1
