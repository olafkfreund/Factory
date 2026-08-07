"""The merge-attribution audit, checked offline (Factory#611).

The command talks to `gh`, so its classifier would be untested unless it is
tested here -- the arrangement tests/test_cli_freshness.py and
tests/test_pin_freshness.py already use.

Everything is synthetic. These assert the VERDICT, so they keep meaning as real
pull requests merge, and they keep meaning after the operator provisions a
separate agent identity -- at which point the live command goes green and only
these tests still exercise the failing direction.
"""

from __future__ import annotations

import json

# scripts/ is put on sys.path by tests/conftest.py.
import check_merge_attribution as cma
import pytest

_AGENT = cma.Merge("Factory", 1, "factory-agent[bot]")
_SHARED = cma.Merge("Factory", 1, "olafkfreund")


def test_builtin_self_test_passes() -> None:
    assert cma.main(["--self-test"]) == 0


def test_a_merge_by_an_identity_agents_do_not_hold_is_attributable() -> None:
    code, counts = cma.assess([_AGENT])
    assert code == 0
    assert counts[cma.ATTRIBUTABLE] == 1


def test_the_same_merge_under_the_shared_login_fails() -> None:
    """The mutation. Only the login differs between this and the test above.

    If this ever passes, the command has stopped measuring the one thing
    Factory#611 is about and would report the fleet as auditable while every
    merge still runs through the operator's credentials.
    """
    code, counts = cma.assess([_SHARED])
    assert code == 1
    assert counts[cma.INDISTINGUISHABLE] == 1


def test_one_shared_merge_among_attributable_ones_still_fails() -> None:
    """A batch is only clean if every merge in it is. An average would hide the
    single unattributable merge, which is the only kind worth finding."""
    assert cma.assess([_AGENT, _AGENT, _SHARED])[0] == 1


def test_a_merge_with_no_recorded_actor_is_undetermined_not_a_pass() -> None:
    assert cma.assess([cma.Merge("Factory", 1, None)])[0] == 2


def test_reading_zero_merges_is_undetermined_not_a_pass() -> None:
    """Rule 4.7: a check that saw nothing has verified nothing. An empty repo
    list must not be the cheapest route to exit 0."""
    assert cma.assess([])[0] == 2


def test_undetermined_outranks_indistinguishable() -> None:
    """Cannot-read wins over can-read-but-cannot-tell, so a batch that partly
    failed to load is never downgraded to the ordinary red."""
    assert cma.assess([_SHARED, cma.Merge("Factory", 2, None)])[0] == 2


def test_gh_payload_parses_to_merges() -> None:
    payload = json.loads('[{"number": 7, "mergedBy": {"login": "olafkfreund"}}]')
    assert cma.parse("Factory", payload) == [cma.Merge("Factory", 7, "olafkfreund")]


def test_a_null_merged_by_parses_to_no_actor() -> None:
    """`gh` returns `"mergedBy": null` for a pull request merged by a deleted
    account or closed-then-merged out of band. Coercing that to a login string
    would silently classify it, which is the failure this whole issue names."""
    assert cma.parse("Factory", [{"number": 8, "mergedBy": None}])[0].merged_by is None


def test_a_payload_shaped_differently_raises_rather_than_being_coerced() -> None:
    """The trust boundary. Everything downstream of `parse` is an audit verdict,
    so a response that is not shaped the way this assumes must stop the run --
    `int("626")` and a login that is not a string would both have produced a
    plausible-looking merge out of something never checked."""
    with pytest.raises(TypeError, match="not an integer"):
        cma.parse("Factory", [{"number": "626", "mergedBy": {"login": "olafkfreund"}}])
    with pytest.raises(TypeError, match="not an integer"):
        cma.parse("Factory", [{"mergedBy": {"login": "olafkfreund"}}])
    with pytest.raises(TypeError, match="not a string"):
        cma.parse("Factory", [{"number": 1, "mergedBy": {"login": 42}}])


def test_the_operator_account_is_declared_shared() -> None:
    """The declaration is the load-bearing part: the classifier is trivial, and
    it is only correct while this set names every login agents can authenticate
    as. Measured 2026-08-07 -- one collaborator, `olafkfreund`, on all six repos."""
    assert "olafkfreund" in cma._SHARED_IDENTITIES
