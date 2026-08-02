"""The pin-freshness watchdog, checked offline on every hub PR (Factory#519).

The watchdog itself is scheduled, because the window it watches opens after a
merge rather than during one — a consumer cannot re-vendor a canonical until the
hub commit exists to pin. That makes the workflow unrunnable as a PR gate and the
COMPARATOR untested unless it is tested here, which is the arrangement
tests/test_branch_divergence.py already uses for the same reason.

Nothing here reaches the network. Pins are supplied explicitly, which is also
how the offline mode of the script is meant to be used.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import check_pin_freshness as pf
import pytest
from check_verification_core_drift import SERVICE_LAYOUTS

_REPO = Path(__file__).resolve().parents[1]

# Real hub commits with known relationships, so these assert the VERDICT rather
# than the plumbing.
_PIN_AT_519 = "a9f44033dbb041d8a1468226c6325ea1f175a264"  # CFactory's pin when #519 was filed
_HUB_AT_519 = "d9bd01de01c357886234dd5f23a546d5799e4e97"  # the other three's pin at that time


def _have(ref: str) -> bool:
    return (
        subprocess.run(  # noqa: S603
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"],  # noqa: S607
            cwd=_REPO,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


@pytest.fixture(autouse=True)
def _needs_full_history() -> None:
    """Fail with the reason, not with 'Invalid revision range'.

    These cases assert the comparator's verdict on real hub commits, so a
    shallow clone breaks every one of them with a git error that says nothing
    about clone depth — which is exactly what happened on the first CI run of
    this file. A guard that cannot run should name its own precondition instead
    of leaving the next person to decode the symptom.

    Deliberately NOT a skip: the cases would then vanish silently on any runner
    that clones shallow, which is the gate-that-did-not-run shape this whole
    file is about.
    """
    missing = [ref for ref in (_PIN_AT_519, _HUB_AT_519) if not _have(ref)]
    if missing:
        pytest.fail(
            "this suite needs the full hub history; "
            f"{', '.join(r[:8] for r in missing)} not present in this clone. "
            "CI must check out with fetch-depth: 0 (see contracts.yml); "
            "locally, run `git fetch --unshallow`."
        )


def _epoch(ref: str) -> int:
    out = subprocess.run(  # noqa: S603
        ["git", "log", "-1", "--pretty=format:%ct", ref],  # noqa: S607
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return int(out.stdout.strip())


def _far_future() -> int:
    return _epoch("HEAD") + 30 * 86400


def test_builtin_self_test_passes() -> None:
    assert pf.main(["--self-test"]) == 0


def test_the_gate_knows_which_services_it_covers() -> None:
    """Silent scope loss is the failure this cannot afford (gate-honesty §3)."""
    assert pf.scope_problems() == []


def test_behind_but_untouched_is_not_staleness() -> None:
    """The whole reason this is not a pin-EQUALITY check.

    32 hub commits separate these two, and none touches the single module
    CFactory vendors. Reporting that as drift would make the watchdog wrong about
    a service that is correctly configured — and #519 could not settle the
    question precisely because nothing computed it.
    """
    moved = pf.commits_since(_PIN_AT_519, pf.canonical_paths("cfactory"), until=_HUB_AT_519)
    assert moved == [], "nothing in a9f44033..d9bd01de touches scripts/ratchet_helpers.py"

    # And it really was a long way behind — otherwise this proves nothing.
    everything = pf.commits_since(_PIN_AT_519, ["."], until=_HUB_AT_519)
    assert len(everything) > 30, f"fixture assumes a long gap, got {len(everything)}"


def test_the_same_pin_is_stale_once_the_canonical_moves() -> None:
    """THE ASSERTION WITH TEETH.

    Same pin, later HEAD: Factory#536 moved ratchet_helpers.py, so the pin that
    was honestly green above is now gating against a canonical that has changed.
    A watchdog that cannot reach this verdict is decorative.
    """
    failures, report = pf.check({"cfactory": _PIN_AT_519}, now=_far_future())
    assert failures, "a pin behind a module it vendors must fail"
    assert any("ratchet_helpers" in line or "510" in line for line in report)


def test_a_fresh_move_is_propagating_not_stale() -> None:
    """The budget exists so the watchdog is not red by construction.

    A canonical lands before any consumer can pin it. Without a grace window this
    alerts every single time a shared module changes, which trains people to
    ignore it — the Factory#538 failure shape.
    """
    moved_at = min(e for _, e in pf.commits_since(_PIN_AT_519, pf.canonical_paths("cfactory")))
    failures, report = pf.check({"cfactory": _PIN_AT_519}, now=moved_at + 3600)
    assert not failures
    assert any("PROPAGATING" in line for line in report), "the grace state must be visible"


def test_the_budget_is_the_only_thing_excusing_it() -> None:
    """Mutation guard on the budget itself: at zero, the same input fails.

    Without this, a budget accidentally set to infinity would pass every other
    case in this file.
    """
    moved_at = min(e for _, e in pf.commits_since(_PIN_AT_519, pf.canonical_paths("cfactory")))
    failures, _ = pf.check({"cfactory": _PIN_AT_519}, now=moved_at + 3600, budget_hours=0)
    assert failures


def test_a_pin_at_head_is_clean() -> None:
    failures, _ = pf.check({"cfactory": "HEAD"}, now=_far_future())
    assert not failures


def test_the_report_enumerates_modules_rather_than_counting_them() -> None:
    """docs/dev/gate-honesty.md: a reader cannot falsify a number."""
    _, report = pf.check({"tfactory": "HEAD"}, now=_far_future())
    joined = "\n".join(report)
    for module in ("ratchet_helpers.py", "verification_gate.py", "artifact_store.py"):
        assert module in joined, f"{module} is vendored by tfactory but absent from the report"


def test_an_unreadable_pin_is_never_a_pass() -> None:
    """Factory#500: a check that cannot see its subject must say so."""
    with pytest.raises(pf.PinUnavailableError):
        pf.commits_since("not-a-real-ref", ["scripts/ratchet_helpers.py"])


def test_offline_mode_refuses_to_run_with_pins_missing() -> None:
    """Half a fleet checked is not a pass; it is the scope loss in miniature."""
    with pytest.raises(SystemExit) as excinfo:
        pf.main(["--no-fetch", "--pin", "cfactory=HEAD"])
    assert excinfo.value.code == 2, "argparse error exit, not a green run over one service"


def test_every_layout_service_is_reachable_by_the_fetcher() -> None:
    """A service in the map with no repo entry would be silently unchecked."""
    assert set(pf._REPOS) == set(SERVICE_LAYOUTS)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
