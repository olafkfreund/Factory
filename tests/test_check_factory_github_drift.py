#!/usr/bin/env python3
"""Self-test for the factory-github drift gate (scripts/check_factory_github_drift.py).

Behaviour-locking tests for the canonical VCS-client drift gate (epic Factory#154,
issue Factory#157). The gate's own ``--self-test`` covers the core logic; these
pytest cases additionally lock its public surface and verify it against the real
checked-in canonical tree at ``shared/factory-github/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The gate lives in <repo>/scripts/.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import check_factory_github_drift as gate  # noqa: E402


def _make_canonical(root: Path) -> Path:
    canonical = root / "canonical"
    (canonical / "providers").mkdir(parents=True)
    for rel in gate.CANONICAL_FILES:
        (canonical / rel).write_text(f"# {rel}\nVALUE = 1\n")
    return canonical


def _copy_tree(canonical: Path, dest: Path) -> Path:
    (dest / "providers").mkdir(parents=True)
    for rel in gate.CANONICAL_FILES:
        (dest / rel).write_bytes((canonical / rel).read_bytes())
    return dest


def test_builtin_self_test_passes() -> None:
    # The gate ships its own dependency-free self-test; it must pass.
    assert gate._self_test() == 0


def test_identical_copy_has_no_drift(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = _copy_tree(canonical, tmp_path / "service")
    assert gate.check_drift(canonical, service) == []


def test_extra_service_file_is_ignored(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = _copy_tree(canonical, tmp_path / "service")
    (service / "bot_detection.py").write_text("# service-only\n")
    assert gate.check_drift(canonical, service) == []


def test_byte_change_is_flagged(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = _copy_tree(canonical, tmp_path / "service")
    (service / "gh_client.py").write_text("# gh_client.py\nVALUE = 2\n")
    problems = gate.check_drift(canonical, service)
    assert len(problems) == 1
    assert problems[0].startswith("gh_client.py")


def test_missing_file_is_flagged(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = tmp_path / "service"
    (service / "providers").mkdir(parents=True)
    for rel in gate.CANONICAL_FILES:
        if rel != "providers/protocol.py":
            (service / rel).write_bytes((canonical / rel).read_bytes())
    problems = gate.check_drift(canonical, service)
    assert any("providers/protocol.py" in p and "missing" in p for p in problems)


def test_run_check_exit_codes(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = _copy_tree(canonical, tmp_path / "service")
    assert gate.run_check(canonical, service) == 0
    (service / "rate_limiter.py").write_text("drift\n")
    assert gate.run_check(canonical, service) == 1
    assert gate.run_check(tmp_path / "nope", service) == 2


def test_main_self_test_flag() -> None:
    assert gate.main(["--self-test"]) == 0


def test_main_requires_service() -> None:
    # argparse error() exits with code 2.
    with pytest.raises(SystemExit) as excinfo:
        gate.main([])
    assert excinfo.value.code == 2


def test_real_canonical_tree_is_complete() -> None:
    # Regression lock: the checked-in canonical tree must contain every file the
    # gate considers part of the layer (a drift gate with a missing canonical
    # file would be silently useless).
    canonical = _REPO_ROOT / "shared/factory-github"
    assert canonical.is_dir(), "shared/factory-github/ must exist"
    for rel in gate.CANONICAL_FILES:
        assert (canonical / rel).is_file(), f"canonical missing {rel}"


def test_real_canonical_matches_itself() -> None:
    # The canonical tree trivially has no drift against itself; this also proves
    # check_drift reads the real files without error.
    canonical = _REPO_ROOT / "shared/factory-github"
    assert gate.check_drift(canonical, canonical) == []
