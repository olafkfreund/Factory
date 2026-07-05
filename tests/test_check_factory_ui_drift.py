#!/usr/bin/env python3
"""Self-test for the factory-ui drift gate.

Behaviour-locking tests for the canonical factory-ui drift gate (portal UX
program, P3). The gate's own ``--self-test`` covers the core logic; these pytest
cases additionally lock its public surface and verify it against the real
checked-in canonical components under ``shared/factory-ui/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The gate lives in <repo>/scripts/.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import check_factory_ui_drift as gate  # noqa: E402


def _make_canonical(root: Path) -> Path:
    canonical = root / "canonical"
    canonical.mkdir(parents=True)
    for module in gate.CANONICAL_MODULES:
        (canonical / module).write_text(f"// {module}\nexport const x = 1;\n")
    return canonical


def _make_service(canonical: Path, root: Path) -> Path:
    for module in gate.CANONICAL_MODULES:
        target = root / gate._VENDOR_DIR / module
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((canonical / module).read_bytes())
    return root


def test_builtin_self_test_passes() -> None:
    assert gate.main(["--self-test"]) == 0


def test_byte_identical_copies_pass(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "svc")
    assert gate.check_service("aifactory", service, canonical) == []


def test_one_byte_drift_is_detected(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "svc")
    drifted = service / gate._VENDOR_DIR / gate.CANONICAL_MODULES[0]
    drifted.write_text(drifted.read_text() + " ")
    problems = gate.check_service("aifactory", service, canonical)
    assert len(problems) == 1
    assert "drifted" in problems[0]


def test_missing_vendored_copy_is_reported(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = tmp_path / "empty"
    problems = gate.check_service("tfactory", service, canonical)
    assert any("missing" in p for p in problems)


def test_unknown_service_is_rejected(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    problems = gate.check_service("nope", tmp_path, canonical)
    assert problems and "unknown service" in problems[0]


def test_all_three_forks_are_listed() -> None:
    assert set(gate.SERVICE_LAYOUTS) == {"pfactory", "aifactory", "tfactory"}


def test_canonical_files_exist_in_repo() -> None:
    canonical = _REPO_ROOT / "shared" / "factory-ui"
    for module in gate.CANONICAL_MODULES:
        assert (canonical / module).is_file(), module
