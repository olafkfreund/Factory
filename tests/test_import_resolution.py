"""The whole-repo import-resolution gate, and the hub's own verdict (Factory#834).

Two jobs. The first half asserts the gate reports what it must and stays quiet
about what it must not, on synthetic trees. The second half runs it against
THIS repository, so the gate is enforced by the hub's ordinary PR suite
(`pytest tests/ shared/factory-common/tests/`, contracts.yml) rather than
needing a workflow of its own.

The motivating incident (TFactory#1121 + #1125 -> a red `dev`, fixed in #1126)
is reconstructed verbatim in `test_the_tfactory_incident_is_reported`: a
package whose forked submodule was deleted, still imported by a module that no
test in the tree imports. That last clause is the point -- pytest collection
found the real one only because nine test modules reached it transitively.
"""

from __future__ import annotations

from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import check_import_resolution as gate

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _incident_tree(root: Path) -> Path:
    """TFactory's layout at the moment `dev` went red, minimised."""
    package = root / "apps" / "web-server" / "server"
    (package / "services").mkdir(parents=True)
    (package / "routes").mkdir()
    for init in (package, package / "services", package / "routes"):
        (init / "__init__.py").write_text("")
    context = package / "routes" / "context.py"
    context.write_text("from server.services.url_safety import assert_safe_outbound_url\n")
    return context


def test_builtin_self_test_passes() -> None:
    assert gate.main(["--self-test"]) == 0


def test_the_tfactory_incident_is_reported(tmp_path: Path) -> None:
    _incident_tree(tmp_path)
    assert gate.run_check(tmp_path) == 1


def test_the_same_tree_passes_once_the_module_exists(tmp_path: Path) -> None:
    """The mutation of the test above: one file appears, nothing else changes.

    Without this pair the gate could be reporting every tree red and the case
    above would still look like proof.
    """
    _incident_tree(tmp_path)
    services = tmp_path / "apps" / "web-server" / "server" / "services"
    (services / "url_safety.py").write_text("def assert_safe_outbound_url(url): ...\n")
    assert gate.run_check(tmp_path) == 0


def test_the_same_tree_passes_when_the_import_is_repointed(tmp_path: Path) -> None:
    """The fix TFactory#1126 actually landed, rather than restoring the fork."""
    context = _incident_tree(tmp_path)
    (tmp_path / "factory_common").mkdir()
    (tmp_path / "factory_common" / "__init__.py").write_text("")
    (tmp_path / "factory_common" / "url_safety.py").write_text(
        "def assert_safe_outbound_url(url): ...\n"
    )
    context.write_text("from factory_common.url_safety import assert_safe_outbound_url\n")
    assert gate.run_check(tmp_path) == 0


def test_a_third_party_import_is_out_of_scope(tmp_path: Path) -> None:
    """A missing dependency is a different failure with a different fix.

    If this ever fails, the gate has started deciding verdicts on which venv CI
    happened to build, and every repo's run becomes unreproducible locally.
    """
    context = _incident_tree(tmp_path)
    context.write_text("import httpx\nfrom fastapi import APIRouter\n")
    assert gate.run_check(tmp_path) == 0


def test_an_optional_import_is_not_reported(tmp_path: Path) -> None:
    context = _incident_tree(tmp_path)
    context.write_text(
        "try:\n"
        "    from server.services.url_safety import assert_safe_outbound_url\n"
        "except ImportError:\n"
        "    assert_safe_outbound_url = None\n"
    )
    assert gate.run_check(tmp_path) == 0


def test_a_typing_only_import_is_not_reported(tmp_path: Path) -> None:
    context = _incident_tree(tmp_path)
    context.write_text(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from server.services.url_safety import Checker\n"
    )
    assert gate.run_check(tmp_path) == 0


def test_the_hub_tree_resolves() -> None:
    """The gate's verdict on this repository, run by the ordinary PR suite.

    Whole-repo on purpose (Factory#786): a diff-scoped version cannot see a
    module that goes stale without being edited, which is the only shape the
    incident had.
    """
    assert gate.run_check(_REPO_ROOT) == 0


def test_a_tree_with_no_python_is_unknown_not_green(tmp_path: Path) -> None:
    """A gate that scanned nothing must not be indistinguishable from a clean one."""
    assert gate.run_check(tmp_path) == 2
