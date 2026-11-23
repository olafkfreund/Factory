#!/usr/bin/env python3
"""Self-test for the factory-ui drift gate.

Behaviour-locking tests for the canonical factory-ui drift gate (portal UX
program, P3). The gate's own ``--self-test`` covers the core logic; these pytest
cases additionally lock its public surface and verify it against the real
checked-in canonical components under ``shared/factory-ui/``.
"""

from __future__ import annotations

from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import check_factory_ui_drift as gate
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_canonical(root: Path) -> Path:
    canonical = root / "canonical"
    canonical.mkdir(parents=True)
    for module in gate.CANONICAL_MODULES:
        (canonical / module).write_text(f"// {module}\nexport const x = 1;\n")
    return canonical


def _make_service(canonical: Path, root: Path, service: str = "aifactory") -> Path:
    for module, rel in gate.SERVICE_LAYOUTS[service].items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((canonical / module).read_bytes())
    return root


def test_builtin_self_test_passes() -> None:
    assert gate.main(["--self-test"]) == 0


def test_byte_identical_copies_pass(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "svc")
    assert gate.check_service("aifactory", service, canonical) == []


@pytest.mark.parametrize("module", ["CommandPalette.tsx", "tokens.css", "tailwind-theme.css"])
def test_one_byte_drift_is_detected(tmp_path: Path, module: str) -> None:
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "svc")
    drifted = service / gate.SERVICE_LAYOUTS["aifactory"][module]
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


def test_all_five_portals_are_listed() -> None:
    assert set(gate.SERVICE_LAYOUTS) == {
        "pfactory",
        "aifactory",
        "tfactory",
        "cfactory",
        "rfactory",
    }


@pytest.mark.parametrize("service", ["pfactory", "aifactory", "tfactory"])
def test_react_portal_styles_live_alongside_components(service: str) -> None:
    layout = gate.SERVICE_LAYOUTS[service]
    assert layout["tokens.css"] == "apps/frontend-web/src/styles/tokens.css"
    assert layout["tailwind-theme.css"] == "apps/frontend-web/src/styles/tailwind-theme.css"
    assert layout["PortalSwitcher.tsx"] == "apps/frontend-web/src/components/PortalSwitcher.tsx"


@pytest.mark.parametrize(
    ("service", "token_path"),
    [
        ("cfactory", "apps/frontend-web/src/styles/tokens.css"),
        ("rfactory", "web/public/tokens.css"),
    ],
)
def test_token_only_layouts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, service: str, token_path: str
) -> None:
    assert gate.SERVICE_LAYOUTS[service] == {"tokens.css": token_path}
    canonical = _make_canonical(tmp_path)
    portal = _make_service(canonical, tmp_path / "svc", service)
    assert gate.check_service(service, portal, canonical) == []
    (portal / token_path).unlink()
    assert gate.check_service(service, portal, canonical) == [
        f"{service}: vendored copy missing: {token_path}"
    ]
    monkeypatch.setitem(gate.SERVICE_LAYOUTS, service, {})
    assert "layout maps it nowhere" in gate.check_service(service, portal, canonical)[0]


def test_canonical_files_exist_in_repo() -> None:
    canonical = _REPO_ROOT / "shared" / "factory-ui"
    for module in gate.CANONICAL_MODULES:
        assert (canonical / module).is_file(), module


def test_the_contract_lists_every_canonical_component() -> None:
    """A .tsx in shared/factory-ui/ that CANONICAL_MODULES omits is unchecked.

    The inverse of test_canonical_files_exist_in_repo above: that one proves
    every LISTED file exists, which says nothing about a file that exists but is
    not listed. Factory#397 is exactly that failure in the sibling gate.
    """
    canonical = _REPO_ROOT / "shared" / "factory-ui"
    assert gate._missing_from_contract(canonical) == []


@pytest.mark.parametrize("name", ["BrandNew.tsx", "extra.css"])
def test_completeness_guard_is_wired_into_check_service(tmp_path: Path, name: str) -> None:
    """The guard must be CALLED by check_service(), not merely defined.

    Factory#397 shipped its guard as dead code - defined, tested directly, never
    invoked - so the gate stayed green on a canonical it had not looked at. A
    test that calls the helper itself cannot catch that; this one goes through
    check_service().
    """
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "svc")
    assert gate.check_service("pfactory", service, canonical) == []

    (canonical / name).write_text("/* unlisted */\n")
    problems = gate.check_service("pfactory", service, canonical)
    assert any(name in p for p in problems), (
        "check_service() ignored a canonical file that CANONICAL_MODULES "
        "does not list - the completeness guard is not wired in."
    )


@pytest.mark.parametrize("new", ["ProjectBreadcrumb.tsx", "tokens.css", "tailwind-theme.css"])
def test_module_absent_from_pinned_canonical_is_tolerated_only_when_listed(
    tmp_path: Path, new: str
) -> None:
    """A portal pinned before a new file existed keeps passing; once the
    pinned canonical has it, the vendored copy is required (and byte-checked)."""
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "svc")
    layout = gate.SERVICE_LAYOUTS["aifactory"]
    assert new in gate.NOT_YET_PINNED
    # old pin: canonical lacks it, the portal has not vendored it -> pass
    (canonical / new).unlink()
    (service / layout[new]).unlink()
    assert gate.check_service("aifactory", service, canonical) == []
    # an unlisted module missing from canonical is still a hard failure
    (canonical / "PortalSwitcher.tsx").unlink()
    assert any(
        "canonical missing" in p for p in gate.check_service("aifactory", service, canonical)
    )
    # new pin: canonical has it -> vendored copy is now required
    (canonical / "PortalSwitcher.tsx").write_text("// PortalSwitcher.tsx\nexport const x = 1;\n")
    (service / layout["PortalSwitcher.tsx"]).write_bytes(
        (canonical / "PortalSwitcher.tsx").read_bytes()
    )
    (canonical / new).write_text("// new\n")
    assert any(
        "vendored copy missing" in p for p in gate.check_service("aifactory", service, canonical)
    )
