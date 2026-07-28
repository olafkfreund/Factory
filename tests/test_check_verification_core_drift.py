#!/usr/bin/env python3
"""Self-test for the verification-core drift gate.

Behaviour-locking tests for the canonical verification-core drift gate (epic
Factory#154, issue Factory#158). The gate's own ``--self-test`` covers the core
logic; these pytest cases additionally lock its public surface and verify it
against the real checked-in canonical modules under ``scripts/``.
"""

from __future__ import annotations

from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import check_verification_core_drift as gate
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

_LAYOUT = {
    "verification_gate.py": "apps/backend/agents/verification_gate.py",
    "nix_provisioner.py": "apps/backend/tools/runners/nix_provisioner.py",
}


def _make_canonical(root: Path) -> Path:
    canonical = root / "canonical"
    canonical.mkdir(parents=True)
    for module in gate.CANONICAL_MODULES:
        (canonical / module).write_text(f"# {module}\nVALUE = 1\n")
    return canonical


def _make_service(canonical: Path, root: Path, layout: dict[str, str]) -> Path:
    for module, rel_path in layout.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((canonical / module).read_bytes())
    return root


def test_builtin_self_test_passes() -> None:
    # The gate ships its own dependency-free self-test; it must pass.
    assert gate._self_test() == 0


def test_identical_copy_has_no_drift(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "service", _LAYOUT)
    assert gate.check_drift(canonical, service, _LAYOUT) == []


def test_extra_service_file_is_ignored(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "service", _LAYOUT)
    (service / "apps/backend/agents/local_helper.py").write_text("# service-only\n")
    assert gate.check_drift(canonical, service, _LAYOUT) == []


def test_byte_change_is_flagged(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "service", _LAYOUT)
    (service / "apps/backend/agents/verification_gate.py").write_text("# changed\nVALUE = 2\n")
    problems = gate.check_drift(canonical, service, _LAYOUT)
    assert len(problems) == 1
    assert problems[0].startswith("verification_gate.py")


def test_missing_file_is_flagged(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = tmp_path / "service"
    target = service / "apps/backend/tools/runners/nix_provisioner.py"
    target.parent.mkdir(parents=True)
    target.write_bytes((canonical / "nix_provisioner.py").read_bytes())
    problems = gate.check_drift(canonical, service, _LAYOUT)
    assert any("verification_gate.py" in p and "missing" in p for p in problems)


def test_unvendored_module_is_not_checked(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    layout = {"nix_provisioner.py": "apps/backend/tools/runners/nix_provisioner.py"}
    service = _make_service(canonical, tmp_path / "service", layout)
    assert gate.check_drift(canonical, service, layout) == []


def test_empty_layout_has_no_drift(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = tmp_path / "service"
    service.mkdir()
    assert gate.check_drift(canonical, service, {}) == []


def test_run_check_exit_codes(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "service", _LAYOUT)
    gate.SERVICE_LAYOUTS["__pytest__"] = _LAYOUT
    try:
        assert gate.run_check(canonical, service, "__pytest__") == 0
        (service / "apps/backend/tools/runners/nix_provisioner.py").write_text("drift\n")
        assert gate.run_check(canonical, service, "__pytest__") == 1
        assert gate.run_check(tmp_path / "nope", service, "__pytest__") == 2
        assert gate.run_check(canonical, service, "__unknown__") == 2
    finally:
        del gate.SERVICE_LAYOUTS["__pytest__"]


def test_unregistered_service_is_loud_not_a_clean_pass(tmp_path: Path) -> None:
    """A service the gate does not know must exit 2, never 0.

    Originally this asserted the opposite: pfactory mapped to {} and run_check
    returned 0 with "vendors no verification-core modules", so a service that was
    NEVER CHECKED was indistinguishable from one that passed — the same
    false-green defect as Factory#397. Factory#401 removed the empty entry and
    made an unknown service an error.

    It then asserted `"pfactory" not in SERVICE_LAYOUTS`, which pinned a
    CONTINGENT fact rather than the invariant: pfactory was re-registered in
    Factory#400 because it really does vendor two shared libraries. The rule
    being locked here is about UNKNOWN services, so the test now uses a name that
    can never be registered instead of whichever service happens to be absent.
    """
    canonical = _make_canonical(tmp_path)
    unknown = "definitely-not-a-registered-service"
    assert unknown not in gate.SERVICE_LAYOUTS
    assert gate.run_check(canonical, tmp_path, unknown) == 2


def test_every_canonical_module_is_vendored_by_someone() -> None:
    """A module declared canonical but mapped by nobody is unenforced.

    verification_profiles.py and verification_runner.py were listed for weeks
    while no service vendored them, so nothing ever compared them and they
    inflated the module count the gate reported as OK.
    """
    assert gate._unmapped_modules() == []


def test_main_self_test_flag() -> None:
    assert gate.main(["--self-test"]) == 0


def test_main_list_flag() -> None:
    assert gate.main(["--list"]) == 0


def test_main_requires_service() -> None:
    # argparse error() exits with code 2.
    with pytest.raises(SystemExit) as excinfo:
        gate.main([])
    assert excinfo.value.code == 2


def test_main_requires_root_with_service() -> None:
    with pytest.raises(SystemExit) as excinfo:
        gate.main(["--service", "tfactory"])
    assert excinfo.value.code == 2


def test_real_canonical_modules_exist() -> None:
    # Regression lock: the checked-in canonical modules must all exist (a drift
    # gate with a missing canonical file would be silently useless).
    scripts = _REPO_ROOT / "scripts"
    for module in gate.CANONICAL_MODULES:
        assert (scripts / module).is_file(), f"canonical missing {module}"


def test_service_layouts_reference_known_modules() -> None:
    # Every module a service layout references must be a real canonical module.
    for service, layout in gate.SERVICE_LAYOUTS.items():
        for module in layout:
            assert module in gate.CANONICAL_MODULES, f"{service} references unknown {module}"
