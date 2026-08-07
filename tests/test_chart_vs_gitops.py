"""The chart-vs-gitops control comparison, checked offline (Factory#504).

The gate itself needs five checkouts and runs on a schedule, so the comparator
would be untested unless it is tested here — the same arrangement
tests/test_branch_divergence.py and tests/test_pin_freshness.py use.

Everything here is synthetic. Two engines are built in-memory with known
disagreements, so these assert the VERDICT rather than the plumbing, and they do
not depend on what the real repos happen to contain today.
"""

from __future__ import annotations

import sys

# scripts/ is put on sys.path by tests/conftest.py.
import check_chart_vs_gitops as cvg
import pytest

_HARD_POD = {
    "runAsNonRoot": True,
    "runAsUser": 65532,
    "seccompProfile": {"type": "RuntimeDefault"},
}
_HARD_CTR = {
    "allowPrivilegeEscalation": False,
    "capabilities": {"drop": ["ALL"]},
    "readOnlyRootFilesystem": True,
}
_VALUES = {"podSecurityContext": _HARD_POD, "containerSecurityContext": _HARD_CTR}


# One builder, shared with the script's --self-test and the honesty case: the
# first draft had three copies and the clone budget rejected it.
_manifests = cvg.synthetic_manifests


def test_builtin_self_test_passes() -> None:
    assert cvg.main(["--self-test"]) == 0


def test_matching_engines_agree() -> None:
    assert not cvg.compare_service("svc", _VALUES, _manifests(_HARD_POD, _HARD_CTR)).failures


def test_a_control_the_chart_declares_and_gitops_omits_fails() -> None:
    """THE ASSERTION WITH TEETH — the exact Factory#503 shape.

    Four charts declared a hardened container securityContext while the running
    manifests set none at all, for weeks, with nothing comparing them.
    """
    found = cvg.compare_service("svc", _VALUES, _manifests(_HARD_POD, {}))
    assert found.failures
    assert any("readOnlyRootFilesystem" in f for f in found.failures), (
        "the failure must name the control; a count is not a check"
    )


def test_a_weakened_control_fails_as_hard_as_an_absent_one() -> None:
    """Present-but-false is the more dangerous case: it LOOKS configured."""
    weakened = {**_HARD_CTR, "readOnlyRootFilesystem": False}
    found = cvg.compare_service("svc", _VALUES, _manifests(_HARD_POD, weakened))
    assert found.failures


def test_gitops_ahead_of_the_chart_warns_rather_than_fails() -> None:
    """The asymmetry is deliberate, and the gate is useless without it.

    Cluster-specific work legitimately lands in gitops first. A symmetric gate
    would fail on that and be muted within a week.
    """
    values = {"podSecurityContext": _HARD_POD, "containerSecurityContext": {}}
    found = cvg.compare_service("svc", values, _manifests(_HARD_POD, _HARD_CTR))
    assert not found.failures
    assert found.warnings


def test_a_chart_only_pdb_fails_when_nothing_waives_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The baseline the waiver case has to visibly suppress.

    Also the LIVE behaviour since Factory#550 emptied ``WAIVERS``: the charts
    must not enable a PDB that the gitops manifests do not have. Pinned with an
    explicitly empty waiver list rather than relying on the module's current
    contents, so this keeps testing the same thing after the next waiver lands.
    """
    monkeypatch.setattr(cvg, "WAIVERS", ())
    values = {**_VALUES, "podDisruptionBudget": {"enabled": True}}
    found = cvg.compare_service("svc", values, _manifests(_HARD_POD, _HARD_CTR))
    assert any("podDisruptionBudget" in f for f in found.failures)


def test_a_waiver_suppresses_the_failure_but_not_the_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A waiver is not a mute button; the reader must still see the difference.

    Factory#550 closed both of the gate's real waivers, so this injects one. The
    mechanism has to stay tested while nothing uses it -- an untested escape
    hatch is discovered broken by whoever next needs it, under time pressure.
    """
    monkeypatch.setattr(
        cvg,
        "WAIVERS",
        (
            cvg.Waiver(
                service="*",
                control="podDisruptionBudget",
                reason="test fixture",
                tracked_by="Factory#550",
            ),
        ),
    )
    values = {**_VALUES, "podDisruptionBudget": {"enabled": True}}
    found = cvg.compare_service("svc", values, _manifests(_HARD_POD, _HARD_CTR))
    assert not any("podDisruptionBudget" in f for f in found.failures)
    assert any("WAIVED" in line for line in found.report)


def test_every_waiver_names_a_reason_and_a_tracking_issue() -> None:
    """An unexplained waiver is the silent exemption this gate exists to end.

    ``WAIVERS`` is empty as of Factory#550, so the loop below runs zero times.
    That is a rule passing without evaluating anything, so the ATTRIBUTE is what
    is asserted -- an empty escape hatch is fine, a deleted one is not, and the
    old ``assert cvg.WAIVERS`` contradicted its own failure message by demanding
    a non-empty list. The teeth for this rule live in
    ``test_a_reasonless_waiver_is_rejected`` below, which supplies its own.
    """
    assert isinstance(cvg.WAIVERS, tuple), (
        "the waiver list is the escape hatch; an empty one is fine, an absent one is not"
    )
    for w in cvg.WAIVERS:
        assert w.reason.strip(), f"{w.control} waived with no reason"
        assert w.tracked_by.startswith("Factory#"), f"{w.control} waived with no tracking issue"


def test_a_reasonless_waiver_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rule above, given something to evaluate.

    Without this the "every waiver is explained" claim is green because there
    are no waivers -- the same shape as a test suite that evaluated no rules.
    """
    monkeypatch.setattr(
        cvg,
        "WAIVERS",
        (cvg.Waiver(service="*", control="podDisruptionBudget", reason="", tracked_by=""),),
    )
    assert not all(w.reason and w.tracked_by for w in cvg.WAIVERS)


def test_the_uncompared_controls_are_declared() -> None:
    """Factory#504 proposes four controls and this implements three.

    NetworkPolicy coverage is the one that would have caught Factory#502. A gate
    that implied it covered that is the defect it exists to catch, so its absence
    is printed on every run.
    """
    assert cvg.UNIMPLEMENTED_CONTROLS
    assert any("NetworkPolicy" in c for c in cvg.UNIMPLEMENTED_CONTROLS)


def test_scope_cannot_shrink_unnoticed() -> None:
    """Silent scope loss (gate-honesty §3): the compared sets are enumerated.

    Dropping a service or a field narrows the gate while every remaining case
    still passes, which reads exactly like nothing wrong.
    """
    assert set(cvg.SERVICES) == {"aifactory", "pfactory", "tfactory", "cfactory"}
    assert set(cvg.POD_FIELDS) >= {"runAsNonRoot", "runAsUser", "seccompProfile"}
    assert set(cvg.CONTAINER_FIELDS) >= {
        "allowPrivilegeEscalation",
        "capabilities",
        "readOnlyRootFilesystem",
    }


def test_an_unreadable_input_is_never_a_pass() -> None:
    """Factory#500: a check that cannot see its subject must say so."""
    with pytest.raises(cvg.InputUnavailableError):
        cvg._deployment([{"kind": "Service", "metadata": {"name": "svc"}}], "svc")
    with pytest.raises(cvg.InputUnavailableError):
        cvg._app_container(
            {"spec": {"template": {"spec": {"containers": [{"name": "other"}]}}}}, "svc"
        )


def _sa(value: object) -> dict[str, object]:
    return {
        "kind": "ServiceAccount",
        "metadata": {"name": "svc"},
        "automountServiceAccountToken": value,
    }


def _chart(value: object) -> dict[str, object]:
    return {**_VALUES, "serviceAccount": {"automountServiceAccountToken": value}}


def test_automount_true_on_both_sides_is_a_checked_agreement() -> None:
    """Factory#550. The case the old presence-of-``false`` compare could not see.

    aifactory and tfactory NEED the token -- they create Jobs via
    ``load_incluster_config()`` -- so ``true`` is their honest declaration. The
    previous comparison asked only "does each side declare ``false``?", so a
    ``true``/``true`` pair reported "absent in both": agreement it never checked.
    """
    found = cvg.compare_service("svc", _chart(True), _manifests(_HARD_POD, _HARD_CTR, [_sa(True)]))
    assert not found.failures
    assert any("automountServiceAccountToken: agree (True)" in line for line in found.report)


def test_automount_disagreement_fails_even_when_neither_side_says_false() -> None:
    """The same pair diverging. Under presence-of-``false`` both sides scored
    False, so the gate called them equal and passed on a real divergence."""
    found = cvg.compare_service("svc", _chart(True), _manifests(_HARD_POD, _HARD_CTR, [_sa(False)]))
    assert any("automountServiceAccountToken" in f for f in found.failures)


def test_automount_declared_in_the_chart_and_nowhere_in_gitops_fails() -> None:
    """The original Factory#550 shape: four charts declaring the control while
    every gitops Deployment left it unset, so the token was mounted anyway."""
    found = cvg.compare_service("svc", _chart(False), _manifests(_HARD_POD, _HARD_CTR))
    assert any("automountServiceAccountToken" in f for f in found.failures)


def test_the_pod_spec_automount_wins_over_the_service_accounts() -> None:
    """Kubernetes lets the pod spec override the ServiceAccount, so the gate
    must read it first.

    Reading the ServiceAccount first would pass on the value the cluster
    ignores. That is not hypothetical: TFactory's chart declared ``false`` on
    its ServiceAccount while its Deployment rendered ``true`` from
    ``rbac.jobSandbox.enabled``, and the cluster honoured the ``true``.
    """
    docs = _manifests(_HARD_POD, _HARD_CTR, [_sa(False)])
    docs[0]["spec"]["template"]["spec"]["automountServiceAccountToken"] = True
    assert not cvg.compare_service("svc", _chart(True), docs).failures


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
