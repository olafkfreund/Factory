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

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from selftest_report import SelfTest

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


WAIVERS: tuple[Waiver, ...] = (
    Waiver(
        service="*",
        control="podDisruptionBudget",
        reason=(
            "The charts enable a PDB with minAvailable: 1; the gitops manifests "
            "declare none. Not yet ported rather than decided against, and "
            "porting it wants a live check first: minAvailable: 1 against a "
            "single replica blocks node drains outright, which on a one-node "
            "k3d cluster is an outage, not a protection."
        ),
        tracked_by="Factory#550",
    ),
    Waiver(
        service="*",
        control="automountServiceAccountToken",
        reason=(
            "The charts set it false on the ServiceAccount; the gitops "
            "Deployments leave it unset, so the token IS mounted into every "
            "control-plane pod. Real exposure, small blast radius, and a "
            "one-line fix per manifest - but one that needs a running cluster to "
            "confirm nothing in the pod was quietly using that token."
        ),
        tracked_by="Factory#550",
    ),
)


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

    _compare_presence(service, values, docs, pod_spec, out)
    return out


def _compare_presence(
    service: str,
    values: dict[str, Any],
    docs: list[dict[str, Any]],
    pod_spec: dict[str, Any],
    out: Findings,
) -> None:
    """The two non-securityContext controls, both presence rather than value."""
    chart_pdb = (values.get("podDisruptionBudget") or {}).get("enabled", False)
    live_pdb = any(d.get("kind") == "PodDisruptionBudget" for d in docs)
    _record(service, "podDisruptionBudget", chart_pdb, live_pdb, out)

    sa = values.get("serviceAccount") or {}
    chart_automount = sa.get("automountServiceAccountToken", sa.get("automount"))
    # gitops can set it on the pod spec or the ServiceAccount; either counts.
    live_automount = pod_spec.get("automountServiceAccountToken")
    if live_automount is None:
        for d in docs:
            if d.get("kind") == "ServiceAccount":
                live_automount = d.get("automountServiceAccountToken")
                break
    _record(
        service,
        "automountServiceAccountToken",
        chart_automount is False,
        live_automount is False,
        out,
    )


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

    # A waiver suppresses the failure but must still be reported.
    waived = compare_service(
        "svc",
        {**values, "podDisruptionBudget": {"enabled": True}},
        manifests(hardened_pod, hardened_ctr),
    )
    req(
        not any("podDisruptionBudget" in f for f in waived.failures),
        "a waived control does not fail the run",
    )
    req(
        any("WAIVED" in line for line in waived.report),
        "a waived control is still printed, with its tracking issue",
    )

    # Scope: every waiver names something, and names where it is tracked.
    req(
        all(w.reason and w.tracked_by for w in WAIVERS),
        "every waiver carries a reason and an issue",
    )
    req(bool(UNIMPLEMENTED_CONTROLS), "the unimplemented controls are declared, not implied")

    return t.finish()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--gitops", type=Path, help="path to a factory-gitops checkout")
    ap.add_argument(
        "--service-root", type=Path, help="directory containing AIFactory/, PFactory/, ..."
    )
    ap.add_argument("--self-test", action="store_true", help="run the built-in self-test and exit")
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
