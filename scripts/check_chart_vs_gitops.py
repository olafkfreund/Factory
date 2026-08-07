#!/usr/bin/env python3
"""Do the two deploy engines agree about the controls that matter? (Factory#504)

The fleet deploys twice. `charts/<svc>/` is what a self-hoster installs;
`factory-gitops/apps/<svc>/manifests/` is what reaches the reference cluster.
Nothing compared them, so a control could be declared in one and simply absent
from the other — which is the whole Factory#503 family: four charts claiming a
hardened `securityContext` while the running pods had none.

WHY NOT A FULL RESOURCE DIFF, settled in Factory#499. The two engines
legitimately differ and a gate that fails on "resource in one, absent in the
other" is red on day one and stays red: the charts carry ConfigMaps, PDBs,
ServiceAccounts and control-plane NetworkPolicies that gitops does not; gitops
carries PVCs, a seed-creds initContainer, a cred-sync sidecar and dozens of
inline env vars that the charts do not; the cluster autoscales with KEDA
ScaledObjects no chart models. None of that is drift. It is two engines with
different jobs.

So this compares a DECLARED CONTROL SUBSET and says which one, every run.

DIRECTION IS NOT SYMMETRIC. A control present in the chart and absent from
gitops FAILS: the chart is the published claim, and the cluster failing to honour
it is the defect. The reverse is a WARNING: gitops leading the chart is the
normal direction for cluster-specific work, and failing on it would punish the
cluster for being ahead.

WHAT THIS DOES NOT COVER YET, stated because a gate that implies a scope it does
not have is the defect it exists to catch. Factory#504 proposes four controls;
this implements three. NetworkPolicy COVERAGE — for every pod-label set either
engine produces, is it selected by some policy in that engine — is not here. It
needs label-set matching across two engines rather than a key lookup, and it is
the control that would have caught Factory#502, so its absence is a real gap and
not a rounding error. :data:`UNIMPLEMENTED_CONTROLS` names it in the report.

Usage:
    python3 scripts/check_chart_vs_gitops.py --gitops ../factory-gitops \\
        --service-root ..                  # dir holding AIFactory/, PFactory/, ...
    python3 scripts/check_chart_vs_gitops.py --self-test

Exit codes:
    0 - every declared control agrees, or diverges only in the waived/warned way
    1 - a control the chart declares is missing from gitops and is not waived
    2 - bad invocation, or an input could not be read (never a silent pass:
        a check that cannot see its subject must say so, Factory#500)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from selftest_report import SelfTest, gate_argparser

_EXIT_BAD_INVOCATION = 2

SERVICES: dict[str, str] = {
    "aifactory": "AIFactory",
    "pfactory": "PFactory",
    "tfactory": "TFactory",
    "cfactory": "CFactory",
}

# The securityContext keys compared, pod- and container-level. Enumerated rather
# than "compare the whole dict": the two engines legitimately spell some fields
# differently (the chart sets runAsGroup, gitops relies on fsGroup), and a
# whole-dict compare would fail on that and get muted. These are the fields the
# Factory#503 family was actually about.
POD_FIELDS: tuple[str, ...] = ("runAsNonRoot", "runAsUser", "seccompProfile")
CONTAINER_FIELDS: tuple[str, ...] = (
    "allowPrivilegeEscalation",
    "capabilities",
    "readOnlyRootFilesystem",
)

# Controls proposed by Factory#504 that this script does NOT implement.
UNIMPLEMENTED_CONTROLS: tuple[str, ...] = (
    "NetworkPolicy coverage (every pod-label set selected by some policy in its "
    "own engine) — needs label-set matching, not a key lookup; would have caught "
    "Factory#502",
)


@dataclass(frozen=True)
class Waiver:
    """A control allowed to differ, with the reason recorded in the source.

    A waiver is not a mute button. It carries the issue that tracks closing it,
    so the difference between "decided" and "not done yet" stays visible - the
    distinction CFactory's standards/exemptions.md draws for the same reason.
    """

    service: str
    control: str
    reason: str
    tracked_by: str


# Both of this gate's original waivers are CLOSED by Factory#550, and closed by
# changing the world rather than by widening the exemption:
#
#   podDisruptionBudget — the charts enabled one with minAvailable: 1 against
#   their own pinned replicaCount: 1, which permits zero disruptions and blocks
#   `kubectl drain` on the node hosting the pod indefinitely (measured; see the
#   PR). The charts now default it OFF and their templates refuse to render an
#   unevictable PDB, so "absent in both engines" is a real agreement.
#
#   automountServiceAccountToken — verified per workload against the live
#   cluster. pfactory and cfactory have no in-cluster API caller and now declare
#   false in both engines; aifactory and tfactory create Jobs via
#   load_incluster_config() and now declare true in both. The comparison below
#   changed from presence-of-false to a VALUE compare so the second pair is
#   actually checked instead of passing as "absent in both".
#
# An empty tuple is deliberate and is not the same as deleting the mechanism:
# the Waiver dataclass and _waived() stay, so the next control that legitimately
# differs is recorded with a reason and a tracking issue rather than muted.
WAIVERS: tuple[Waiver, ...] = ()


def synthetic_manifests(
    pod_sc: dict[str, Any], ctr_sc: dict[str, Any], extra: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """A minimal gitops manifest stream for service ``svc``, for tests.

    Public and living beside the comparator rather than in the test tree because
    THREE places need it — this module's ``--self-test``, tests/test_chart_vs_gitops.py
    and the honesty case in tests/test_gate_honesty.py — and the first draft had
    three copies of it, which the jscpd clone budget correctly rejected. The
    self-test must run standalone with no pytest, so the shared builder cannot
    live in a test-only helper.
    """
    return [
        {
            "kind": "Deployment",
            "metadata": {"name": "svc"},
            "spec": {
                "template": {
                    "spec": {
                        "securityContext": pod_sc,
                        "containers": [{"name": "svc", "securityContext": ctr_sc}],
                    }
                }
            },
        },
        *(extra or []),
    ]


@dataclass
class Findings:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report: list[str] = field(default_factory=list)


class InputUnavailableError(RuntimeError):
    """An engine's declaration could not be read. Never downgraded to a pass."""


def _load_yaml(path: Path) -> dict[str, Any]:
    """A chart's values.yaml as a mapping.

    The parsed TYPE is checked, not just the parse. An empty or non-mapping
    values.yaml would otherwise sail through here and fail much later on
    ``values.get(...)`` with an AttributeError — a crash rather than this
    module's "input unavailable" path, which is the one that exits 2 and says
    what it could not read (Factory#500).
    """
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InputUnavailableError(f"cannot read {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise InputUnavailableError(
            f"{path}: expected a YAML mapping, got {type(loaded).__name__} — "
            "an empty or malformed values.yaml cannot be compared"
        )
    return loaded


def _load_manifests(path: Path) -> list[dict[str, Any]]:
    """The gitops manifest stream, keeping only the mapping documents.

    Same reasoning as :func:`_load_yaml`: a stray scalar document in the stream
    would crash a later ``.get`` rather than being reported as unreadable input.
    """
    try:
        docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as exc:
        raise InputUnavailableError(f"cannot read {path}: {exc}") from exc
    kept = [d for d in docs if isinstance(d, dict)]
    if not kept:
        raise InputUnavailableError(f"{path}: no YAML mapping documents to compare")
    return kept


def _waived(service: str, control: str) -> Waiver | None:
    for w in WAIVERS:
        if w.control == control and w.service in (service, "*"):
            return w
    return None


def _deployment(docs: list[dict[str, Any]], service: str) -> dict[str, Any]:
    for d in docs:
        if d.get("kind") == "Deployment" and d.get("metadata", {}).get("name") == service:
            return d
    raise InputUnavailableError(f"{service}: no Deployment named {service!r} in the manifests")


def _app_container(dep: dict[str, Any], service: str) -> dict[str, Any]:
    containers: list[dict[str, Any]] = dep["spec"]["template"]["spec"]["containers"]
    for c in containers:
        if c.get("name") == service:
            return c
    raise InputUnavailableError(
        f"{service}: no container named {service!r}; found {[c.get('name') for c in containers]}"
    )


def compare_service(service: str, values: dict[str, Any], docs: list[dict[str, Any]]) -> Findings:
    """Compare one service's chart values against its gitops manifests."""
    out = Findings()
    dep = _deployment(docs, service)
    pod_spec = dep["spec"]["template"]["spec"]
    live_pod = pod_spec.get("securityContext") or {}
    live_ctr = _app_container(dep, service).get("securityContext") or {}
    chart_pod = values.get("podSecurityContext") or {}
    chart_ctr = values.get("containerSecurityContext") or {}

    out.report.append(f"{service}:")

    for label, fields, chart, live in (
        ("pod", POD_FIELDS, chart_pod, live_pod),
        ("container", CONTAINER_FIELDS, chart_ctr, live_ctr),
        # automountServiceAccountToken rides the same per-key comparison rather
        # than a presence check, which is Factory#550's finding. Presence-of-
        # ``false`` cannot tell "declared true" from "not declared at all", and
        # those are exactly the two states that mattered: aifactory and tfactory
        # NEED the token, so the honest declaration is ``true``, and a gate that
        # only looks for ``false`` would have called their agreement vacuous.
        # Both engines must now name a value, and the values must match.
        (
            "sa",
            ("automountServiceAccountToken",),
            _chart_automount(values),
            _live_automount(docs, pod_spec),
        ),
    ):
        for key in fields:
            if key not in chart:
                if key in live:
                    out.warnings.append(f"{service}: gitops sets {label}.{key}, the chart does not")
                continue
            if key not in live:
                out.failures.append(
                    f"{service}: chart declares {label}.{key}={chart[key]!r} and the "
                    f"gitops manifest sets it nowhere"
                )
                out.report.append(f"  {label}.{key}: chart={chart[key]!r}  gitops=ABSENT")
            elif live[key] != chart[key]:
                out.failures.append(
                    f"{service}: {label}.{key} differs — chart {chart[key]!r}, gitops {live[key]!r}"
                )
                out.report.append(f"  {label}.{key}: chart={chart[key]!r}  gitops={live[key]!r}")
            else:
                out.report.append(f"  {label}.{key}: agree ({chart[key]!r})")

    _compare_presence(service, values, docs, out)
    return out


_AUTOMOUNT = "automountServiceAccountToken"


def _chart_automount(values: dict[str, Any]) -> dict[str, Any]:
    """The chart's automount declaration, as a 0-or-1 key dict for the loop.

    ``automount`` is accepted as an alias because that is the key the upstream
    Helm ``common`` chart uses and one of ours could adopt it.
    """
    sa = values.get("serviceAccount") or {}
    for key in (_AUTOMOUNT, "automount"):
        if key in sa:
            return {_AUTOMOUNT: sa[key]}
    return {}


def _live_automount(docs: list[dict[str, Any]], pod_spec: dict[str, Any]) -> dict[str, Any]:
    """The gitops automount declaration, pod spec first, then the ServiceAccount.

    Pod-spec first because that is the precedence Kubernetes itself applies: a
    pod-level value overrides the ServiceAccount's. Reading them the other way
    round would let the gate pass on the value the cluster ignores — the exact
    contradiction Factory#550 found inside TFactory's own chart.
    """
    if _AUTOMOUNT in pod_spec:
        return {_AUTOMOUNT: pod_spec[_AUTOMOUNT]}
    for d in docs:
        if d.get("kind") == "ServiceAccount" and _AUTOMOUNT in d:
            return {_AUTOMOUNT: d[_AUTOMOUNT]}
    return {}


def _compare_presence(
    service: str,
    values: dict[str, Any],
    docs: list[dict[str, Any]],
    out: Findings,
) -> None:
    """The one control that is genuinely presence, not value.

    A PDB is a resource: it exists in an engine or it does not. Comparing its
    ``minAvailable`` across engines would be comparing a number whose correct
    value depends on the replica and node counts of the specific cluster, which
    is the reasoning Factory#550 settled — see the fleet decision recorded in
    factory-gitops apps/README.md.
    """
    chart_pdb = (values.get("podDisruptionBudget") or {}).get("enabled", False)
    live_pdb = any(d.get("kind") == "PodDisruptionBudget" for d in docs)
    _record(service, "podDisruptionBudget", chart_pdb, live_pdb, out)


def _record(service: str, control: str, chart_has: bool, live_has: bool, out: Findings) -> None:
    if chart_has and not live_has:
        waiver = _waived(service, control)
        if waiver is None:
            out.failures.append(f"{service}: chart declares {control}, gitops does not")
            out.report.append(f"  {control}: chart=declared  gitops=ABSENT")
        else:
            out.report.append(
                f"  {control}: chart=declared  gitops=ABSENT  WAIVED ({waiver.tracked_by})"
            )
    elif live_has and not chart_has:
        out.warnings.append(f"{service}: gitops declares {control}, the chart does not")
        out.report.append(f"  {control}: chart=absent  gitops=declared (warning only)")
    else:
        out.report.append(f"  {control}: agree ({'declared' if chart_has else 'absent in both'})")


def run(gitops: Path, service_root: Path) -> tuple[Findings, int]:
    """Compare every service; returns the findings and an exit code."""
    total = Findings()
    try:
        for service, repo in SERVICES.items():
            values = _load_yaml(service_root / repo / "charts" / service / "values.yaml")
            docs = _load_manifests(gitops / "apps" / service / "manifests" / "manifests.yaml")
            got = compare_service(service, values, docs)
            total.failures += got.failures
            total.warnings += got.warnings
            total.report += got.report
    except InputUnavailableError as exc:
        sys.stderr.write(f"chart-vs-gitops: {exc}\n")
        return total, _EXIT_BAD_INVOCATION
    return total, 1 if total.failures else 0


def _selftest() -> int:
    """Synthetic engines with known disagreements, so the gate is seen failing."""
    t = SelfTest("chart-vs-gitops")
    req = t.req

    manifests = synthetic_manifests

    hardened_pod = {
        "runAsNonRoot": True,
        "runAsUser": 65532,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    hardened_ctr = {
        "allowPrivilegeEscalation": False,
        "capabilities": {"drop": ["ALL"]},
        "readOnlyRootFilesystem": True,
    }
    values = {"podSecurityContext": hardened_pod, "containerSecurityContext": hardened_ctr}

    agree = compare_service("svc", values, manifests(hardened_pod, hardened_ctr))
    req(not agree.failures, "identical control sets agree")

    # THE CASE WITH TEETH, and the exact Factory#503 shape: chart claims a
    # hardened container context, the manifest sets none at all.
    missing = compare_service("svc", values, manifests(hardened_pod, {}))
    req(bool(missing.failures), "a control the chart declares and gitops omits FAILS")
    req(
        any("readOnlyRootFilesystem" in f for f in missing.failures),
        "the failure names the missing control, not a count",
    )

    # A differing VALUE is as much drift as an absent key.
    weakened = compare_service(
        "svc", values, manifests(hardened_pod, {**hardened_ctr, "readOnlyRootFilesystem": False})
    )
    req(bool(weakened.failures), "a control present but WEAKENED fails too")

    # Direction: gitops ahead of the chart is a warning, never a failure.
    ahead = compare_service(
        "svc",
        {"podSecurityContext": hardened_pod, "containerSecurityContext": {}},
        manifests(hardened_pod, hardened_ctr),
    )
    req(
        not ahead.failures and bool(ahead.warnings), "gitops leading the chart warns, does not fail"
    )

    # An UNWAIVED chart-only PDB still fails. This is the baseline the waiver
    # case below has to visibly suppress, and with WAIVERS now empty it is also
    # the live behaviour: the charts must not enable a PDB gitops does not have.
    pdb_only = compare_service(
        "svc",
        {**values, "podDisruptionBudget": {"enabled": True}},
        manifests(hardened_pod, hardened_ctr),
    )
    req(
        any("podDisruptionBudget" in f for f in pdb_only.failures),
        "a chart-only PDB fails when nothing waives it",
    )

    # The waiver MECHANISM, exercised against a synthetic waiver. Factory#550
    # closed both real waivers, so WAIVERS is empty -- and an empty tuple would
    # otherwise let the machinery rot untested until the next person needed it
    # and found it broken. Injected rather than kept as a live waiver, because a
    # waiver that exists only to be tested is exactly the mute button the Waiver
    # docstring says this is not.
    global WAIVERS  # noqa: PLW0603 - restored in the finally below
    real_waivers = WAIVERS
    try:
        WAIVERS = (
            Waiver(
                service="*",
                control="podDisruptionBudget",
                reason="self-test only",
                tracked_by="Factory#550",
            ),
        )
        waived = compare_service(
            "svc",
            {**values, "podDisruptionBudget": {"enabled": True}},
            manifests(hardened_pod, hardened_ctr),
        )
    finally:
        WAIVERS = real_waivers
    req(
        not any("podDisruptionBudget" in f for f in waived.failures),
        "a waived control does not fail the run",
    )
    req(
        any("WAIVED" in line for line in waived.report),
        "a waived control is still printed, with its tracking issue",
    )

    _selftest_automount(req, values, manifests, hardened_pod, hardened_ctr)

    # Scope: every waiver names something, and names where it is tracked.
    req(
        all(w.reason and w.tracked_by for w in WAIVERS),
        "every waiver carries a reason and an issue",
    )
    req(bool(UNIMPLEMENTED_CONTROLS), "the unimplemented controls are declared, not implied")

    return t.finish()


def _selftest_automount(req, values, manifests, hardened_pod, hardened_ctr) -> None:  # type: ignore[no-untyped-def]
    """Factory#550: automount is compared by VALUE, and precedence is honoured.

    Split out because the checks above already fill ``_selftest``; the cases
    here are the ones that would have passed vacuously under the old
    presence-of-``false`` comparison.
    """

    def sa_doc(**kw: Any) -> dict[str, Any]:
        return {"kind": "ServiceAccount", "metadata": {"name": "svc"}, **kw}

    def chart(v: Any) -> dict[str, Any]:
        return {**values, "serviceAccount": {_AUTOMOUNT: v}}

    # THE CASE THE OLD COMPARISON MISSED. Both engines say `true` -- a real,
    # deliberate agreement for a pod that creates Jobs. Presence-of-false read
    # this as "absent in both" and reported agreement it had not checked.
    agree_true = compare_service(
        "svc",
        chart(True),
        manifests(hardened_pod, hardened_ctr, [sa_doc(**{_AUTOMOUNT: True})]),
    )
    req(not agree_true.failures, "chart true / gitops true agrees")

    # And the same pair disagreeing must FAIL, which presence-of-false could not
    # see either: neither side declares `false`, so it called them equal.
    disagree = compare_service(
        "svc",
        chart(True),
        manifests(hardened_pod, hardened_ctr, [sa_doc(**{_AUTOMOUNT: False})]),
    )
    req(
        any(_AUTOMOUNT in f for f in disagree.failures),
        "chart true / gitops false FAILS",
    )

    # The original Factory#550 shape: chart declares, gitops declares nothing.
    undeclared = compare_service(
        "svc", chart(False), manifests(hardened_pod, hardened_ctr)
    )
    req(
        any(_AUTOMOUNT in f for f in undeclared.failures),
        "a chart automount value gitops never states FAILS",
    )

    # Precedence: Kubernetes lets the pod spec override the ServiceAccount, so
    # the gate must read the pod spec first. Reading the SA first would pass on
    # a value the cluster ignores -- the contradiction inside TFactory's chart.
    pod_wins = manifests(hardened_pod, hardened_ctr, [sa_doc(**{_AUTOMOUNT: False})])
    pod_wins[0]["spec"]["template"]["spec"][_AUTOMOUNT] = True
    req(
        not compare_service("svc", chart(True), pod_wins).failures,
        "the pod spec's automount wins over the ServiceAccount's",
    )


def main(argv: list[str] | None = None) -> int:
    ap = gate_argparser(__doc__)
    ap.add_argument("--gitops", type=Path, help="path to a factory-gitops checkout")
    ap.add_argument(
        "--service-root", type=Path, help="directory containing AIFactory/, PFactory/, ..."
    )
    args = ap.parse_args(argv)

    if args.self_test:
        return _selftest()
    if not args.gitops or not args.service_root:
        ap.error("--gitops and --service-root are both required")

    findings, code = run(args.gitops, args.service_root)
    if code == _EXIT_BAD_INVOCATION:
        return code

    print("\n".join(findings.report))  # noqa: T201
    print(  # noqa: T201
        "\nControls compared: pod/container securityContext fields, "
        "podDisruptionBudget, automountServiceAccountToken."
    )
    for gap in UNIMPLEMENTED_CONTROLS:
        print(f"NOT COMPARED: {gap}")  # noqa: T201
    for w in WAIVERS:
        print(f"WAIVED ({w.service}/{w.control}, {w.tracked_by}): {w.reason}")  # noqa: T201
    if findings.warnings:
        print("\nWarnings (gitops ahead of the chart — not a failure):")  # noqa: T201
        for line in findings.warnings:
            print(f"  {line}")  # noqa: T201
    if findings.failures:
        print("\nchart-vs-gitops FAILED:")  # noqa: T201
        for line in findings.failures:
            print(f"  {line}")  # noqa: T201
        return 1
    print("\nchart-vs-gitops PASSED: every compared control agrees, or is waived with a reason.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
