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

import dataclasses
import subprocess
import sys
import urllib.error
import urllib.request
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
    assert ".github/workflows/planning-card-conformance.yml" in declared


def test_the_planning_card_gate_watches_the_contract_it_pins() -> None:
    """The one gate with no vendored copy on the service side (Factory#554).

    Every other gate here leaves something compared when its pin goes stale: the
    vendored file is still byte-checked, just against an old canonical. CFactory
    vendors no copy of the planning-card schema at all — its workflow checks the
    hub out at the pin and compares its pydantic models against the file in
    place. So a pin left behind means the service is measured against a contract
    the hub has moved on from, with a green build the whole time, and this
    watchdog is the only thing that can notice.

    Which makes the pathspec load-bearing rather than incidental. Pointed at
    anything but the schema this gate is permanently green by construction — the
    silent-scope-loss shape one level down, and the same failure
    `test_a_gate_reads_its_own_canonical_root` guards for factory-ui.
    """
    gate = next(g for g in pf.GATES if g.name == "planning-card")
    assert gate.services() == ["cfactory"], "CFactory is the only consumer of this contract"
    assert gate.canonical_paths("cfactory") == ["apis/planning-card.schema.json"]
    assert gate.pin_var == "HUB_PIN_SHA"

    # And the pathspec must actually select the contract's own history: a
    # commit that touched the schema has to be visible to `commits_since`, or
    # the gate reports a pin as current no matter how far it has fallen behind.
    touched = pf._git("log", "-1", "--pretty=format:%h", "--", *gate.canonical_paths("cfactory"))
    assert touched.strip(), "no hub commit has ever touched the path this gate watches"


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


def test_a_required_gate_must_cover_every_service() -> None:
    """Fleet-wide coverage stopped being enough at the third gate (Factory#547).

    With one gate, "in no gate's layout" caught a dropped service. With three, a
    service dropped from ONE layout is still covered by another and that check
    stays quiet — silent scope loss with extra steps. A required gate has the
    stronger invariant: its job blocks merges in every consumer, so every
    consumer must be in its layout.
    """
    for gate in pf.GATES:
        if gate.required_check:
            assert set(gate.layouts) == set(pf._REPOS), f"{gate.name} does not cover the fleet"


def test_the_contracts_gate_reads_a_differently_named_pin() -> None:
    """Its pin cannot be HUB_PIN_SHA: it shares code-quality.yml with another.

    CFactory's drift job gates two sets from one workflow — the standards
    directory (pinned by standards/.hub-sha) and this single file. Two variables
    of the same name in one file is not addressable, so the gate carries the
    name it reads.
    """
    contracts = next(g for g in pf.GATES if g.name == "factory-contracts")
    assert contracts.pin_var == "CONTRACTS_PIN_SHA"
    assert contracts.services() == ["cfactory"], "CFactory is the only consumer"
    assert (
        pf.pin_from("X", 'env:\n  CONTRACTS_PIN_SHA: "abc1234"\n', "w", "CONTRACTS_PIN_SHA")
        == "abc1234"
    )
    with pytest.raises(pf.PinUnavailableError):
        # The default name must NOT match it, or one gate would silently read
        # another's pin out of the same file.
        pf.pin_from("X", 'env:\n  CONTRACTS_PIN_SHA: "abc1234"\n', "w")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


def test_a_404_is_an_answer_but_a_network_error_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    """`unlisted_consumers` must be quietest when it CAN look, not when it cannot.

    It answers "does this repo ship the gate's workflow", and the only way to
    answer is over the network. Flattening every failure to False would make
    absence undetectable exactly when GitHub is unreachable — the gate would go
    green on a fleet it never read, which is the Factory#500 shape and the same
    defect this whole watchdog exists to catch one level up.

    So: 404 is a real answer (the repo does not have it); anything else raises.
    """

    def _raise(code: int):
        def _open(url: str, **_kw: object) -> object:
            raise urllib.error.HTTPError(url, code, "boom", {}, None)  # type: ignore[arg-type]

        return _open

    monkeypatch.setattr(urllib.request, "urlopen", _raise(404))
    assert pf.workflow_exists("PFactory", ".github/workflows/nope.yml") is False

    monkeypatch.setattr(urllib.request, "urlopen", _raise(503))
    with pytest.raises(pf.PinUnavailableError):
        pf.workflow_exists("PFactory", ".github/workflows/nope.yml")


def test_a_repo_running_a_gate_must_be_in_its_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one scope check that does not compare two hand-written lists.

    Every other check in `scope_problems` compares one declaration against
    another, so they all agree by construction when both are wrong together.
    This one compares a layout against the repos, which cannot be edited to
    make the gate quiet.

    It exists because the list it guards HAD gone stale: Factory#848 declared
    `test-collection` for aifactory and cfactory, correct that day, and within a
    day PFactory and TFactory shipped the same workflow (Factory#844) while the
    hub kept reporting `pin-freshness PASSED ... across 6 gate(s)` without ever
    reading their pins.
    """
    gate = next(g for g in pf.GATES if g.name == "test-collection")
    assert "tfactory" in gate.layouts, "fixture assumes tfactory is declared today"

    # Pretend every repo missing from a layout DOES ship that gate's workflow.
    monkeypatch.setattr(pf, "workflow_exists", lambda *_a, **_kw: True)
    shrunk = dataclasses.replace(
        gate, layouts={svc: lay for svc, lay in gate.layouts.items() if svc != "tfactory"}
    )
    monkeypatch.setattr(pf, "GATES", (shrunk,))

    problems = pf.unlisted_consumers()
    assert any("TFactory" in p and "test-collection" in p for p in problems), (
        f"dropping tfactory from the layout while it still ships the workflow "
        f"was not reported; got {problems}"
    )


def test_no_repo_is_reported_when_none_ships_the_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other direction, so the test above cannot pass by always finding one."""
    monkeypatch.setattr(pf, "workflow_exists", lambda *_a, **_kw: False)
    assert pf.unlisted_consumers() == []
