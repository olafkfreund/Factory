"""The uncollected-test gate, and the hub's own verdict (Factory#844).

Two jobs, same split as ``test_import_resolution.py``. The first half asserts
the gate reports what it must on synthetic trees; the second runs it against
THIS repository, so the gate is enforced by the hub's ordinary PR suite
(``pytest tests/ shared/factory-common/tests/``, contracts.yml) rather than
needing a workflow of its own.

The motivating incident is reconstructed verbatim in
``test_the_pfactory_607_alarm_is_reported``: ``pfactory build`` has been broken
since 2026-06-03 because ``run_autonomous_agent`` is defined nowhere, and the
test asserting that exact property has sat uncollected in the tree the whole
time. Ten weeks of green CI over a broken entry point.

Every case that asserts a FAILURE is paired with the one-change mutation that
makes it pass, and every case that asserts a PASS with the mutation that makes
it fail. A gate that reddens everything and a gate that reddens nothing both
look like proof from one side only.
"""

from __future__ import annotations

from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import check_test_collection as gate

_REPO_ROOT = Path(__file__).resolve().parents[1]

_STEPS = "jobs:\n  backend:\n    steps:\n      - run: |\n"


def _register(
    root: Path, path: str, *, reason: str | None = None, issue: str = "PFactory#607"
) -> None:
    gate._registry(root, path=path, reason=reason or gate._GOOD_REASON, issue=issue)


def test_builtin_self_test_passes() -> None:
    assert gate.main(["--self-test"]) == 0


def test_the_pfactory_607_alarm_is_reported(tmp_path: Path) -> None:
    """apps/backend/agents/test_refactoring.py, uncollected and unregistered."""
    gate._pfactory_tree(tmp_path)
    assert gate.run_check(tmp_path) == 1


def test_the_same_tree_passes_once_the_file_is_registered(tmp_path: Path) -> None:
    """The mutation of the case above: one registry file appears, nothing else."""
    gate._pfactory_tree(tmp_path)
    _register(tmp_path, "apps/backend/agents/test_refactoring.py")
    assert gate.run_check(tmp_path) == 0


def test_a_placeholder_reason_is_rejected(tmp_path: Path) -> None:
    """`reason = "TODO"` satisfies any check that only asks whether one is present."""
    gate._pfactory_tree(tmp_path)
    _register(tmp_path, "apps/backend/agents/test_refactoring.py", reason="TODO")
    assert gate.run_check(tmp_path) == 1


def test_a_wordy_placeholder_reason_is_still_rejected(tmp_path: Path) -> None:
    """The mutation the one-word `TODO` case cannot see.

    A six-word floor alone passes "TODO: work out whether this should be
    collected", which is a placeholder wearing a sentence. Both rules have to
    hold, so both need a case that fails when only the other is removed.
    """
    gate._pfactory_tree(tmp_path)
    _register(
        tmp_path,
        "apps/backend/agents/test_refactoring.py",
        reason="TODO: work out later whether this file should be collected or deleted",
    )
    assert gate.run_check(tmp_path) == 1


def test_a_commented_pytest_line_does_not_widen_the_boundary(tmp_path: Path) -> None:
    """Workflow prose quotes pytest command lines. A comment is not a command.

    Without this the gate reports NOTHING on any repo whose ci.yml happens to
    mention `pytest apps/backend` in a comment -- and the hub's contracts.yml
    and AIFactory's ci.yml both do exactly that.
    """
    gate._pfactory_tree(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.write_text(
        "# CI used to run `pytest apps/backend` here -- prose, not a command\n"
        + _STEPS
        + "          pytest tests/ apps/web-server/tests/\n"
    )
    assert gate.run_check(tmp_path) == 1


def test_a_registry_entry_that_matches_nothing_is_red(tmp_path: Path) -> None:
    """Factory#788. An allowlist that only ever grows is an ignore list."""
    gate._pfactory_tree(tmp_path)
    _register(tmp_path, "apps/backend/agents/test_deleted.py")
    assert gate.run_check(tmp_path) == 1


def test_widening_collection_makes_the_entry_dead(tmp_path: Path) -> None:
    """The other half of #788: a fixed file's entry must be deleted, not left."""
    gate._pfactory_tree(tmp_path)
    _register(tmp_path, "apps/backend/agents/test_refactoring.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.write_text(workflow.read_text().replace("tests/ apps", "tests/ apps/backend apps"))
    assert gate.run_check(tmp_path) == 1


def test_a_multiline_pytest_invocation_keeps_its_paths(tmp_path: Path) -> None:
    """Read line-by-line this has no path arguments, so the whole repo looks collected.

    That is the shape where the gate reports NOTHING while looking healthy, and
    AIFactory's ci.yml writes its pytest steps exactly this way.
    """
    gate._pfactory_tree(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.write_text(_STEPS + "          pytest \\\n            tests/ \\\n            -q\n")
    assert gate.run_check(tmp_path) == 1


def test_a_pytest_probe_does_not_collect_the_whole_repo(tmp_path: Path) -> None:
    """PFactory's runner-images.yml smoke-tests an image with `pytest --version`.

    Counted as an invocation it has no path arguments, which reads as "the
    whole repo is collected" -- a clean verdict over eight uncollected files.
    """
    gate._pfactory_tree(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.write_text(
        _STEPS + "          pytest tests/\n" + _STEPS + "          pytest --version\n"
    )
    assert gate.run_check(tmp_path) == 1


def test_a_pip_install_line_is_not_an_invocation(tmp_path: Path) -> None:
    """The hub's own contracts.yml has `pip install pytest ... jsonschema httpx`."""
    gate._pfactory_tree(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.write_text(
        _STEPS + "          pytest tests/\n" + _STEPS + "          pip install pytest httpx\n"
    )
    assert gate.run_check(tmp_path) == 1


def test_a_bare_pytest_collects_the_whole_repo(tmp_path: Path) -> None:
    """CFactory runs `PYTHONPATH=apps/backend pytest -v`, and that is genuinely everything.

    The mutation pair for the two cases above: without it they would pass just
    as well if the gate had stopped believing any bare invocation at all.
    """
    gate._pfactory_tree(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.write_text(_STEPS + "          PYTHONPATH=apps/backend pytest -v\n")
    assert gate.run_check(tmp_path) == 0


def test_testpaths_narrows_a_bare_pytest(tmp_path: Path) -> None:
    """...unless a root pytest config narrows it, which would otherwise read clean."""
    gate._pfactory_tree(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.write_text(_STEPS + "          pytest -v\n")
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    assert gate.run_check(tmp_path) == 1


def test_a_narrowing_flag_is_unknown_not_a_pass(tmp_path: Path) -> None:
    """--ignore shrinks collection; modelling it wrong fails in the clean direction."""
    gate._pfactory_tree(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.write_text(_STEPS + "          pytest . --ignore=apps/backend\n")
    assert gate.run_check(tmp_path) == 2


def test_a_collected_path_that_does_not_exist_is_unknown(tmp_path: Path) -> None:
    """A verdict measured against the wrong boundary is worse than no verdict."""
    gate._pfactory_tree(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.write_text(_STEPS + "          pytest tests/ apps/gone/tests\n")
    assert gate.run_check(tmp_path) == 2


def test_no_pytest_invocation_is_unknown_not_green(tmp_path: Path) -> None:
    gate._pfactory_tree(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.write_text("jobs:\n  lint:\n    steps:\n      - run: ruff check .\n")
    assert gate.run_check(tmp_path) == 2


def test_a_tree_with_no_test_files_is_unknown_not_green(tmp_path: Path) -> None:
    """A gate that examined ZERO items must not print the same verdict as a clean one."""
    assert gate.run_check(tmp_path) == 2


def _container_tree(root: Path, directive: str = "") -> None:
    """The TFactory#1134 shape: pytest run against a mounted container path.

    ``portal_testing/`` is this repo's directory, mounted into the runner image
    as ``/app/portal_testing``. Its tests run in CI; nothing in the workflow
    text says which repo directory that is.
    """
    gate._pfactory_tree(root)
    _register(root, "apps/backend/agents/test_refactoring.py")
    (root / "portal_testing").mkdir()
    (root / "portal_testing" / "test_container.py").write_text("def test_ok(): ...\n")
    (root / ".github" / "workflows" / "ci.yml").write_text(
        _STEPS
        + "          pytest tests/ apps/web-server/tests/\n"
        + _STEPS
        + "          docker run --rm img \\\n"
        + "            sh -c 'pip install -q pytest && python -m pytest /app/portal_testing -q'"
        + f"{directive}\n"
    )


def test_a_container_pytest_path_reads_as_uncollected(tmp_path: Path) -> None:
    """Unannotated, this is the reading that put two real suites in a registry.

    They are covered -- 33 tests -- and the entry has to say so, which turns a
    covered area into a documented gap and invites someone to delete them.
    """
    _container_tree(tmp_path)
    assert gate.run_check(tmp_path) == 1


def test_the_directive_maps_a_container_path_to_its_repo_directory(tmp_path: Path) -> None:
    """The mutation of the case above: one comment appears, nothing else moves."""
    _container_tree(tmp_path, directive="  # test-collection: portal_testing")
    assert gate.run_check(tmp_path) == 0
    assert "portal_testing" in gate._collected(tmp_path).paths


def test_a_directive_naming_the_whole_repo_is_rejected(tmp_path: Path) -> None:
    """`# test-collection: .` would hand out the false clean as a feature."""
    _container_tree(tmp_path, directive="  # test-collection: .")
    assert gate.run_check(tmp_path) == 2


def test_a_directive_escaping_the_tree_is_rejected(tmp_path: Path) -> None:
    _container_tree(tmp_path, directive="  # test-collection: ../elsewhere")
    assert gate.run_check(tmp_path) == 2


def test_a_directive_naming_an_absent_path_is_unknown(tmp_path: Path) -> None:
    """A typo must not read as a pass, by the same guard a stale workflow hits."""
    _container_tree(tmp_path, directive="  # test-collection: portal_typo")
    assert gate.run_check(tmp_path) == 2


def test_a_directive_does_nothing_on_a_line_that_runs_no_pytest(tmp_path: Path) -> None:
    """It annotates an invocation. Anywhere else it is a comment about one."""
    gate._pfactory_tree(tmp_path)
    _register(tmp_path, "apps/backend/agents/test_refactoring.py")
    (tmp_path / "portal_testing").mkdir()
    (tmp_path / "portal_testing" / "test_container.py").write_text("def test_ok(): ...\n")
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        _STEPS
        + "          pytest tests/ apps/web-server/tests/\n"
        + "      # test-collection: portal_testing\n"
    )
    assert gate.run_check(tmp_path) == 1


def test_an_annotated_line_with_a_narrowing_flag_is_still_unknown(tmp_path: Path) -> None:
    """A directive says what pytest was pointed at, not that --ignore is modelled."""
    _container_tree(tmp_path, directive=" --ignore=x  # test-collection: portal_testing")
    assert gate.run_check(tmp_path) == 2


def test_the_hub_tree_is_accounted_for() -> None:
    """The gate's verdict on this repository, run by the ordinary PR suite.

    The hub has three uncollected test files of its own, all registered in
    ``uncollected-tests-allowlist.toml`` with a written reason. If this fails,
    either a new one landed or a registered one became collected -- and in the
    second case the entry must be deleted, not left behind (Factory#788).
    """
    assert gate.run_check(_REPO_ROOT) == 0
