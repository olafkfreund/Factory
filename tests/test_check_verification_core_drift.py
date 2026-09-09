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
        # A canonical entry may be a path under scripts/ (languages/*.yaml).
        (canonical / module).parent.mkdir(parents=True, exist_ok=True)
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


def test_empty_layout_over_an_empty_tree_has_no_drift(tmp_path: Path) -> None:
    canonical = _make_canonical(tmp_path)
    service = tmp_path / "service"
    service.mkdir()
    assert gate.check_drift(canonical, service, {}) == []


def test_empty_layout_over_a_carrying_tree_is_red(tmp_path: Path) -> None:
    """Mapping nothing is not the same as there being nothing to map.

    This asserted the opposite until Factory#523 — "empty layout must not drift"
    — which is the defect stated as a requirement: a service tree carrying two
    canonical modules, with a layout mapping none of them, was a pass. Deleting
    every entry is only deleting one entry repeatedly, so the extreme case and
    the reported case are the same bug.
    """
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "service", _LAYOUT)
    problems = gate.check_drift(canonical, service, {})
    assert [p.split(":")[0] for p in problems] == sorted(_LAYOUT), problems

    # Asserted through run_check() as well, because it used to short-circuit on
    # an empty layout with "vendors no verification-core modules (nothing to
    # check)" and exit 0 without calling check_drift at all.
    gate.SERVICE_LAYOUTS["__pytest_empty__"] = {}
    try:
        assert gate.run_check(canonical, service, "__pytest_empty__") == 1
    finally:
        del gate.SERVICE_LAYOUTS["__pytest_empty__"]


def test_deleting_a_layout_entry_turns_the_gate_red(tmp_path: Path) -> None:
    """THE Factory#523 mutation: mutate the gate's CONFIGURATION, not its subject.

    Reported reproduction, verbatim: with ``job_dispatch.py`` mapped, a drifted
    copy is flagged; with the one-line mapping removed, the gate printed
    ``NO PROBLEMS`` and the run reported success. The only signal was the module
    count in the success line dropping from 6 to 5 — a headline number nobody
    re-derives.

    The subject is held constant across the two calls (the same drifted file, on
    disk, unchanged); the only thing that moves is the gate's own layout. A guard
    exercised only by mutating its subject cannot see this, which is why every
    mutation table for this gate passed while the hole was open.
    """
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "service", _LAYOUT)
    (service / _LAYOUT["verification_gate.py"]).write_text("# deliberately drifted\n")

    mapped = gate.check_drift(canonical, service, _LAYOUT)
    assert any(p.startswith("verification_gate.py") for p in mapped), mapped

    unmapped_layout = {k: v for k, v in _LAYOUT.items() if k != "verification_gate.py"}
    unmapped = gate.check_drift(canonical, service, unmapped_layout)
    assert any("verification_gate.py" in p and "maps it nowhere" in p for p in unmapped), unmapped


def test_deleting_a_real_service_mapping_turns_the_gate_red(tmp_path: Path) -> None:
    """The same mutation against the REAL SERVICE_LAYOUTS, end-to-end.

    The test above proves the logic on a synthetic layout; this one proves the
    shipped configuration is actually wired to it. It builds a service tree that
    matches aifactory's real layout byte-for-byte, confirms run_check() exits 0,
    then deletes one real mapping and requires exit 1 — which is the reproduction
    on the issue, run against the config the fleet uses.
    """
    canonical = _make_canonical(tmp_path)
    real_layout = dict(gate.SERVICE_LAYOUTS["aifactory"])
    assert "job_dispatch.py" in real_layout, "fixture assumes aifactory maps job_dispatch.py"
    service = _make_service(canonical, tmp_path / "service", real_layout)

    gate.SERVICE_LAYOUTS["__pytest_real__"] = real_layout
    try:
        assert gate.run_check(canonical, service, "__pytest_real__") == 0
        del gate.SERVICE_LAYOUTS["__pytest_real__"]["job_dispatch.py"]
        assert gate.run_check(canonical, service, "__pytest_real__") == 1
    finally:
        gate.SERVICE_LAYOUTS.pop("__pytest_real__", None)


def test_stray_guard_is_wired_into_check_drift(tmp_path: Path) -> None:
    """The stray-copy guard must be CALLED by check_drift(), not merely defined.

    Same wiring requirement as the unmapped-module guard below, for the same
    reason: Factory#397 shipped the sibling gate's completeness guard as dead
    code — defined, tested directly, never invoked.
    """
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "service", _LAYOUT)
    stray = service / "apps/backend/copy/nix_provisioner.py"
    stray.parent.mkdir(parents=True)
    stray.write_bytes((canonical / "nix_provisioner.py").read_bytes())

    problems = gate.check_drift(canonical, service, _LAYOUT)
    assert any("apps/backend/copy/nix_provisioner.py" in p for p in problems), (
        "check_drift() ignored a canonical module carried by the service that the "
        "layout maps nowhere. The stray-copy guard is defined but not wired in."
    )


def test_stray_scan_prunes_dot_directories_and_dependency_trees(tmp_path: Path) -> None:
    """The scan's scope is the documented one, in both directions.

    A local checkout keeps whole second copies of the tree under
    ``.claude/worktrees/`` and ``node_modules/``; flagging those would redden
    every developer run and the guard would be turned off. Pruning them is a
    deliberate blind spot, so it is asserted rather than assumed — and the second
    half asserts the prune list has not quietly swallowed the real case.
    """
    canonical = _make_canonical(tmp_path)
    service = tmp_path / "service"
    for parent in (".claude/worktrees/x", "node_modules/pkg"):
        (service / parent).mkdir(parents=True)
        (service / parent / "nix_provisioner.py").write_text("# not a vendored copy\n")
    assert gate.check_drift(canonical, service, {}) == []

    (service / "vendor").mkdir()
    (service / "vendor/nix_provisioner.py").write_text("# a real unmapped copy\n")
    assert gate.check_drift(canonical, service, {}) != []


def test_success_report_enumerates_what_it_compared(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A count is not a check: the pass must name every module and its bytes.

    ``OK: aifactory matches the canonical (6 vendored module(s))`` read 6 the day
    a seventh was dropped and 5 the day a sixth was, and neither is legible as a
    defect. Locked here so the enumeration cannot regress to a headline number,
    and so the per-module evidence (a digest anyone can re-derive with
    ``sha256sum``) is present on the PASS path — not only on failures.
    """
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "service", _LAYOUT)
    gate.SERVICE_LAYOUTS["__pytest_ok__"] = _LAYOUT
    try:
        assert gate.run_check(canonical, service, "__pytest_ok__") == 0
    finally:
        del gate.SERVICE_LAYOUTS["__pytest_ok__"]

    out = capsys.readouterr().out
    for module, rel_path in _LAYOUT.items():
        assert f"{module} -> {rel_path}" in out, f"success report never named {module}"
    assert out.count("sha256:") == 2 * len(_LAYOUT), "each side of each compare must cite its bytes"


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


def test_unmapped_guard_is_wired_into_check_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unmapped-module guard must be CALLED by check_drift(), not just defined.

    The test above passes if ``_unmapped_modules()`` merely EXISTS and works. That
    is not the same property, and the difference is not hypothetical: Factory#397
    shipped the sibling gate's completeness guard as dead code — defined, tested
    directly, never invoked — so the gate stayed green on a canonical it had not
    looked at. Both sibling gates grew a wiring test after that; this one did not,
    and unwiring the guard here left all sixteen of these cases green.

    Asserted through check_drift() by declaring a module canonical that no service
    maps, which is the Factory#401 scenario (verification_profiles.py /
    verification_runner.py listed for weeks, vendored by nobody, compared nowhere).
    """
    canonical = _make_canonical(tmp_path)
    service = _make_service(canonical, tmp_path / "service", _LAYOUT)
    assert gate.check_drift(canonical, service, _LAYOUT) == [], "identical copies must be clean"

    monkeypatch.setattr(gate, "CANONICAL_MODULES", (*gate.CANONICAL_MODULES, "orphan_module.py"))
    problems = gate.check_drift(canonical, service, _LAYOUT)
    assert any("orphan_module.py" in p for p in problems), (
        "check_drift() ignored a canonical module that no service vendors. The "
        "unmapped-module guard is defined but not wired in, so the gate reports "
        "OK for a module it never compares anywhere."
    )


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


# --------------------------------------------------------------------------- #
# acknowledged forks (Factory#590)                                             #
# --------------------------------------------------------------------------- #


def test_hub_own_ratchet_uses_the_shared_rules() -> None:
    # The hub's scripts/ratchet_lint.py is the FIFTH fork and had the same
    # defect (Factory#589). PORTED_RATCHETS runs against SERVICE checkouts and
    # cannot reach it, so this is where it is asserted. Four of five checked is
    # the scope loss this gate exists to catch.
    assert gate.ported_ratchet_problems(_REPO_ROOT, gate.HUB_PORTED_RATCHET) == []


def test_ported_ratchet_registry_covers_every_service_with_a_layout() -> None:
    # Every service the gate knows about runs a ratchet. A service present in
    # SERVICE_LAYOUTS but absent from PORTED_RATCHETS is a fork nothing asks
    # about, which is the state all five were in before Factory#590.
    assert set(gate.PORTED_RATCHETS) == set(gate.SERVICE_LAYOUTS)


def test_restated_rule_names_a_real_canonical_helper() -> None:
    # The remedy the failure message names must exist in the canonical, or the
    # gate tells people to import something that is not there.
    helpers = (_REPO_ROOT / "scripts/ratchet_helpers.py").read_text()
    for rule in gate._REQUIRED_RATCHET_RULES:
        assert f"def {rule}(" in helpers, f"{rule} is required but absent from ratchet_helpers"


def test_inline_restatement_is_flagged(tmp_path: Path) -> None:
    # THE mutation: the shared rule copied back inline. No byte comparison can
    # see this, because these forks are not byte-comparable to anything.
    fork = tmp_path / "scripts/ratchet_lint.py"
    fork.parent.mkdir(parents=True)
    fork.write_text(
        "from ratchet_helpers import is_test_file\n\n\n"
        "def ruff_counts(res):\n"
        "    if res.returncode not in (0, 1):\n"
        "        raise SystemExit(2)\n"
        "    return 0\n"
    )
    problems = gate.ported_ratchet_problems(tmp_path, "scripts/ratchet_lint.py")
    assert any("does not import" in p for p in problems)
    assert any("restates the shared rule" in p for p in problems)


def test_import_in_a_comment_does_not_satisfy_the_gate(tmp_path: Path) -> None:
    # Parsed with ast, not grepped: a mention is not an import.
    fork = tmp_path / "scripts/ratchet_lint.py"
    fork.parent.mkdir(parents=True)
    fork.write_text(
        '"""Uses require_tool_ran."""\n# from ratchet_helpers import require_tool_ran\n'
    )
    assert any(
        "does not import" in p
        for p in gate.ported_ratchet_problems(tmp_path, "scripts/ratchet_lint.py")
    )


def test_missing_fork_is_flagged_not_skipped(tmp_path: Path) -> None:
    assert any(
        "absent" in p for p in gate.ported_ratchet_problems(tmp_path, "scripts/ratchet_lint.py")
    )
