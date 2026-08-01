#!/usr/bin/env python3
"""PR-time cover for the branch-divergence watchdog (Factory#498).

The comparator ships a dependency-free ``--self-test`` that builds real git
repositories, and the scheduled workflow runs it before it believes its own
verdict. That only runs on a schedule, so a hub PR could break the detector and
nothing on the PR would say so -- the "the gate did not run" shape of
Factory#471. This file hooks it into hub PR CI and pins the two things that are
easy to break without noticing: the derived scope, and the direction of the
grading.
"""

from __future__ import annotations

from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import check_branch_divergence as gate
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_builtin_self_test_passes() -> None:
    assert gate._self_test() == 0


def test_scope_is_derived_from_the_branch_protection_intent_table() -> None:
    """The fleet list is read, not re-declared, and it reads the fleet we have.

    If someone adds a repo to apply_branch_protection.sh with a dev branch, this
    watchdog picks it up with no second edit. This case exists so that the
    derivation itself cannot silently start returning nothing.
    """
    table = gate.parse_intent((_REPO_ROOT / "scripts" / "apply_branch_protection.sh").read_text())
    with_dev = sorted(name for name, branches in table.items() if "dev" in branches)
    assert with_dev == ["AIFactory", "CFactory", "PFactory", "TFactory"]
    # Factory and factory-gitops are main-only and stay in the report as SKIPPED,
    # not omitted: a repo that quietly leaves the scope is the whole defect class.
    assert set(table) - set(with_dev) == {"Factory", "factory-gitops"}


def test_an_unparseable_intent_table_cannot_produce_an_empty_scope() -> None:
    # The dangerous failure is not a crash, it is "checked 0 repo(s): OK".
    with pytest.raises(gate.CannotDetermineError):
        gate.parse_intent("ALL_REPOS=()")
    with pytest.raises(gate.CannotDetermineError):
        gate.parse_intent("no table here at all")
    with pytest.raises(gate.CannotDetermineError):
        gate.parse_intent('ALL_REPOS=(CFactory Newbie)\n    CFactory)  BRANCHES="main dev" ;;\n')


def test_backflow_fires_with_no_grace_period() -> None:
    """Unpromoted work is graded on age; work stranded on main never is."""
    now = 1_000_000_000
    fresh = [gate.Commit("a" * 40, "fix: hotfix straight to main", now - 60)]
    code, message = gate.verdict([], fresh, now, 24.0)
    assert code == 1
    assert "DIVERGED" in message

    # Same commit, same age, on the dev side: inside the budget, so quiet.
    code, message = gate.verdict(fresh, [], now, 24.0)
    assert code == 0

    # And past the budget it is not quiet -- the grading has a live direction,
    # not just a permissive one.
    old = [gate.Commit("b" * 40, "fix(approve): stop reporting Done", now - 40 * 3600)]
    code, message = gate.verdict(old, [], now, 24.0)
    assert code == 1
    assert "40.0h" in message
