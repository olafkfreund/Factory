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


def _require_full_history() -> None:
    """Fail with the reason, not with "Invalid revision range".

    These cases assert the comparator's verdict on real hub commits, so a
    shallow clone breaks them with a git error that says nothing about clone
    depth — which is exactly what the first CI run of this file did. A guard that
    cannot run should name its own precondition instead of leaving the next
    person to decode the symptom.

    Deliberately a FAILURE, not a skip: skipping would make these cases vanish
    silently on any runner that clones shallow, which is the gate-that-did-not-run
    shape this whole file is about.

    A plain function rather than an autouse fixture because the ratchet runs mypy
    with --ignore-missing-imports, so `pytest.fixture` resolves to Any and
    `@pytest.fixture(autouse=True)` is an untyped decorator under --strict. No
    other test in this repo uses a fixture; this is why.
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
    _require_full_history()
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
    _require_full_history()
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
    _require_full_history()
    failures, report = pf.check({"cfactory": _PIN_AT_519}, now=_far_future())
    assert failures, "a pin behind a module it vendors must fail"
    assert any("ratchet_helpers" in line or "510" in line for line in report)


def test_a_fresh_move_is_propagating_not_stale() -> None:
    """The budget exists so the watchdog is not red by construction.

    A canonical lands before any consumer can pin it. Without a grace window this
    alerts every single time a shared module changes, which trains people to
    ignore it — the Factory#538 failure shape.
    """
    _require_full_history()
    moved_at = min(e for _, e in pf.commits_since(_PIN_AT_519, pf.canonical_paths("cfactory")))
    failures, report = pf.check({"cfactory": _PIN_AT_519}, now=moved_at + 3600)
    assert not failures
    assert any("PROPAGATING" in line for line in report), "the grace state must be visible"


def test_the_budget_is_the_only_thing_excusing_it() -> None:
    """Mutation guard on the budget itself: at zero, the same input fails.

    Without this, a budget accidentally set to infinity would pass every other
    case in this file.
    """
    _require_full_history()
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


# --- the drift gate's trigger, which Factory#543 turned into a wedge risk -----

_FILTERED = """name: x
on:
  pull_request:
    branches: [dev, main]
    paths:
      - "scripts/ratchet_helpers.py"
  push:
    branches: [dev, main]
jobs:
  drift:
"""

_UNFILTERED = """name: x
on:
  pull_request:
    branches: [dev, main]
    # no paths filter, deliberately (Factory#525)
  push:
    branches: [dev, main]
    paths:
      - "scripts/ratchet_helpers.py"
jobs:
  drift:
"""


def test_a_re_added_paths_filter_is_flagged() -> None:
    """THE ASSERTION WITH TEETH, and it guards an outage rather than a gap.

    Since Factory#543 this job is a REQUIRED status check in all four consumers.
    A path-filtered workflow does not report a "skipped" context, it reports
    NOTHING, so re-adding the filter Factory#525 removed would block every
    non-matching PR in that repo forever - the Factory#529 wedge, fleet-wide.
    """
    problem = pf.trigger_filter_problem("Repo", _FILTERED)
    assert problem is not None
    assert "REQUIRED" in problem, "the message must say why a filter is now fatal"


def test_paths_ignore_is_the_same_defect() -> None:
    """`paths-ignore:` filters just as effectively; spelling it differently
    would otherwise walk straight past this guard."""
    assert pf.trigger_filter_problem("Repo", _FILTERED.replace("paths:", "paths-ignore:"))


def test_a_filter_on_push_only_is_not_flagged() -> None:
    """Scope guard in the other direction.

    Only the pull_request trigger can wedge a PR. A guard that also fired on a
    push filter would be noise, and noise is how a real alert gets muted.
    """
    assert pf.trigger_filter_problem("Repo", _UNFILTERED) is None


def test_no_pull_request_trigger_at_all_is_flagged() -> None:
    """Deleting the trigger is the same outcome as filtering it to nothing."""
    body = "name: x\non:\n  push:\n    branches: [dev, main]\njobs:\n  drift:\n"
    assert pf.trigger_filter_problem("Repo", body)


def test_the_live_consumers_are_unfiltered_right_now() -> None:
    """The claim that made requiring the check safe, asserted against reality.

    Network, unlike the rest of this file - so it is skipped when offline rather
    than failing a local run for a reason that has nothing to do with the change
    under test. The scheduled watchdog checks the same thing every day with no
    escape hatch, which is where it must not be skippable.
    """
    gate = next(g for g in pf.GATES if g.required_check)
    for service in gate.services():
        repo = pf._REPOS[service]
        try:
            body = pf.fetch_workflow(repo, gate.workflow, timeout=10)
        except pf.PinUnavailableError as exc:  # offline
            pytest.skip(f"no network: {exc}")
        assert pf.trigger_filter_problem(repo, body) is None


# --- Factory#514: the rule's exemption is conditional on THIS being true ------


def test_every_file_granular_gate_is_read_fleet_wide() -> None:
    """The condition the narrowed pin rule rests on.

    Rule 5.2 lets a file-granular set pin inside its workflow instead of a
    `.hub-sha` file, but only because the hub reads those pins fleet-wide — that
    is what answers the original objection, "nothing outside that workflow can
    find it". A gate missing from GATES is a pin nobody can find, and the
    exemption stops being true the moment that happens.
    """
    declared = {g.workflow for g in pf.GATES}
    assert ".github/workflows/verification-core-drift.yml" in declared
    assert ".github/workflows/factory-ui-drift.yml" in declared


def test_a_gate_reads_its_own_canonical_root() -> None:
    """Each gate must look for movement where its canonical actually lives.

    Pointing factory-ui at `scripts/` would make it permanently green: nothing
    under scripts/ is a portal component, so no commit would ever count as
    moving its canonical. That is the silent-scope-loss shape, one level down.
    """
    roots = {g.name: g.canonical_root for g in pf.GATES}
    assert roots["verification-core"] == "scripts"
    assert roots["factory-ui"] == "shared/factory-ui"
    for gate in pf.GATES:
        for service in gate.services():
            for path in gate.canonical_paths(service):
                assert path.startswith(gate.canonical_root + "/")


def test_only_a_required_gate_is_held_to_an_unfiltered_trigger() -> None:
    """factory-ui is path-filtered and that is correct while it is not required.

    Flagging it would be noise, and noise is how the verification-core alert
    beside it gets muted.
    """
    by_name = {g.name: g for g in pf.GATES}
    assert by_name["verification-core"].required_check is True
    assert by_name["factory-ui"].required_check is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
