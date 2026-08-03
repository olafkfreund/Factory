#!/usr/bin/env python3
"""Cross-gate control for the two honesty properties every hub gate must hold.

Factory#504. Three separate defects on 2026-07-30 were the same shape wearing
different clothes, and the taxonomy they produced is written up in
``docs/dev/gate-honesty.md``. Two of its three criteria are mechanisable, and
this file mechanises them for every gate under ``scripts/``:

**A count is not a check.** A gate that reports ``matches the canonical
(6 vendored module(s))`` has told a reader nothing they can falsify. Factory#523
is the proof: deleting one line from ``SERVICE_LAYOUTS`` un-gated a vendored file
entirely, and the whole trace was that ``6`` becoming ``5``. The same shape ran a
pin count from 12 to 14 to 16 with two people watching. So: every gate must
ENUMERATE what it compared.

**Every verdict carries its fragment.** Printing the source only for the things a
gate reports absent covers the direction that costs an investigation and leaves
the direction that costs a missing control — a parse (or a comparison) that
reports PRESENT when the control is absent prints nothing at all, and nobody goes
looking. So: the pass path must cite its bytes too.

**Mutate the gate's own configuration, not just its subject.** Every mutation
table written for these gates moved the SUBJECT — drift a file, delete a file,
break a signature. None moved the gate's own scope, which is why Factory#523 sat
open under a gate with sixteen green cases. Each case below therefore holds the
subject constant and deletes one entry from the gate's configuration.

The registry at the top is itself subject to the first rule: it enumerates the
gates it covers and asserts that enumeration against the directory, so adding a
``scripts/check_*.py`` without a case here fails rather than silently widening the
blind spot. An exempt gate is named with its reason — a waiver that suppresses
detection is indistinguishable from a check nobody wrote.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import check_branch_divergence as divergence_gate
import check_chart_vs_gitops as chart_gate
import check_factory_github_drift as github_gate
import check_factory_ui_drift as ui_gate
import check_pin_freshness as pin_gate
import check_verification_core_drift as vcore_gate
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO_ROOT / "scripts"

# Gates asserted below, by the name of the case that asserts them.
_COVERED: dict[str, str] = {
    "check_verification_core_drift.py": "test_verification_core_gate_is_honest",
    "check_factory_github_drift.py": "test_factory_github_gate_is_honest",
    "check_factory_ui_drift.py": "test_factory_ui_gate_is_honest",
    "check_branch_divergence.py": "test_branch_divergence_gate_is_honest",
    "check_pin_freshness.py": "test_pin_freshness_gate_is_honest",
    "check_chart_vs_gitops.py": "test_chart_vs_gitops_gate_is_honest",
}

# Gates deliberately out of scope, each with the reason stated. Named, not
# omitted: an exemption nobody can see is the same green as a missing check.
_EXEMPT: dict[str, str] = {
    "check_deploy_drift.py": (
        "compares one expected sha against one deployed tag. It has no per-item "
        "configuration that can silently shrink, so neither property has a "
        "surface here — there is nothing to enumerate and one verdict, which "
        "already prints both values it compared."
    ),
    "check_jscpd_budget.py": (
        "reads a single duplication percentage out of a jscpd report and compares "
        "it against a committed budget. Same shape: one number in, one verdict "
        "out, no scope that can shrink unobserved."
    ),
}


def _copy_into(canonical: Path, rel_paths: dict[str, str], root: Path) -> Path:
    """Materialise a service tree that matches *canonical* byte-for-byte."""
    for source_name, rel in rel_paths.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(canonical / source_name, target)
    return root


def _assert_enumerates(out: str, items: dict[str, str], compares: int) -> None:
    """The report must name every item it compared and cite the bytes for each."""
    for source_name, rel in items.items():
        assert source_name in out, f"report never named {source_name}"
        assert rel in out, f"report never named the path it read for {source_name}"
    assert out.count("sha256:") == compares, (
        "every verdict must carry the fragment it was derived from, on BOTH sides "
        f"and on the PASS path — expected {compares} digests, got {out.count('sha256:')}"
    )


def test_every_gate_is_covered_here_or_named_as_exempt() -> None:
    """The registry above is enumerated against the directory, not counted.

    This file is a gate over gates and is subject to its own first rule: a new
    ``scripts/check_*.py`` that nobody adds a case for would otherwise widen the
    blind spot by exactly the amount nobody notices.
    """
    found = {path.name for path in sorted(_SCRIPTS.glob("check_*.py"))}
    assert found == set(_COVERED) | set(_EXEMPT), (
        "a gate under scripts/ is neither asserted here nor named as exempt: "
        f"{sorted(found - set(_COVERED) - set(_EXEMPT))}"
    )
    for gate_name, case in _COVERED.items():
        assert case in Path(__file__).read_text(), f"{gate_name} names a case that does not exist"


def test_verification_core_gate_is_honest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    layout = dict(vcore_gate.SERVICE_LAYOUTS["aifactory"])
    service = _copy_into(_SCRIPTS, layout, tmp_path / "service")

    vcore_gate.SERVICE_LAYOUTS["__honesty__"] = layout
    try:
        assert vcore_gate.run_check(_SCRIPTS, service, "__honesty__") == 0
        _assert_enumerates(capsys.readouterr().out, layout, compares=2 * len(layout))

        # Configuration mutation: the tree is untouched, one mapping goes.
        del vcore_gate.SERVICE_LAYOUTS["__honesty__"]["ratchet_helpers.py"]
        assert vcore_gate.run_check(_SCRIPTS, service, "__honesty__") == 1, (
            "deleting a layout entry left the gate green on a file it no longer compares"
        )
    finally:
        vcore_gate.SERVICE_LAYOUTS.pop("__honesty__", None)


def test_factory_github_gate_is_honest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical = _REPO_ROOT / "shared" / "factory-github"
    files = {rel: rel for rel in github_gate.CANONICAL_FILES}
    service = _copy_into(canonical, files, tmp_path / "service")

    assert github_gate.run_check(canonical, service) == 0
    _assert_enumerates(capsys.readouterr().out, files, compares=2 * len(files))

    # Configuration mutation: the tree is untouched, one entry leaves the contract.
    monkeypatch.setattr(github_gate, "CANONICAL_FILES", github_gate.CANONICAL_FILES[1:])
    assert github_gate.run_check(canonical, service) == 1, (
        "dropping a file from CANONICAL_FILES left the gate green on a file it no "
        "longer compares (this is what shipped in Factory#370 — two new canonical "
        "files, unlisted, and the gate reported OK against a tree it could not import)"
    )


def test_factory_ui_gate_is_honest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical = _REPO_ROOT / "shared" / "factory-ui"
    layout = dict(ui_gate.SERVICE_LAYOUTS["aifactory"])
    portal = _copy_into(canonical, layout, tmp_path / "portal")

    assert ui_gate.main(["--service", "aifactory", "--root", str(portal)]) == 0
    _assert_enumerates(capsys.readouterr().out, layout, compares=2 * len(layout))

    # Configuration mutation: the tree is untouched, one component leaves the
    # portal's layout. This was GREEN until Factory#523 — the sibling gate had the
    # same hole, found by turning this file's criterion on it.
    shrunk = {k: v for k, v in layout.items() if k != "CommandPalette.tsx"}
    monkeypatch.setitem(ui_gate.SERVICE_LAYOUTS, "aifactory", shrunk)
    assert ui_gate.main(["--service", "aifactory", "--root", str(portal)]) == 1, (
        "dropping a component from a portal's layout left the gate green on a "
        "component it no longer compares"
    )


def test_branch_divergence_gate_is_honest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Factory#498's watchdog, held to this file's three criteria.

    Its scope is DERIVED from the ``BRANCHES=`` column of
    ``scripts/apply_branch_protection.sh`` rather than re-declared, so there is no
    second registry to delete an entry from. That is not enough on its own: the
    table itself can be narrowed. So the gate also checks the claim in the other
    direction, and the mutation below is exactly that narrowing — PFactory leaves
    the scope while still having a dev branch, and the gate must go red instead of
    quietly checking one repo fewer.
    """
    now = int(time.time())
    fleet = tmp_path / "fleet"
    fleet.mkdir()
    intent = (_SCRIPTS / "apply_branch_protection.sh").read_text()

    for name in ("CFactory", "PFactory", "TFactory", "AIFactory"):
        divergence_gate._build_benign(fleet, now, name)
    for name in ("Factory", "factory-gitops"):
        repo = divergence_gate._new_repo(fleet, name, now)
        divergence_gate._run(["git", "-C", str(repo), "branch", "-D", "dev"])

    # workdir == clone-base: the repos are already there, so nothing is cloned and
    # no network is touched.
    assert divergence_gate.run_check(fleet, str(fleet), intent, 24.0, now) == 0
    out = capsys.readouterr().out
    for name in ("CFactory", "PFactory", "TFactory", "AIFactory", "Factory", "factory-gitops"):
        assert name in out, f"the report never named {name}"
    # Every verdict carries the bytes it was derived from, on BOTH sides and on
    # the PASS path — four repos compared, two branch shas each.
    assert out.count("compared dev=") == 4
    assert out.count(" against main=") == 4

    # Configuration mutation: the repos are untouched, PFactory leaves the scope.
    narrowed = re.sub(
        r'(^\s{4}PFactory\).*)BRANCHES="main dev"', r'\1BRANCHES="main"', intent, flags=re.MULTILINE
    )
    assert narrowed != intent, "the mutation did not change the intent table"
    assert divergence_gate.run_check(fleet, str(fleet), narrowed, 24.0, now) == 2, (
        "narrowing a repo out of the BRANCHES= table left the gate green on a repo "
        "that still has a dev branch — scope shrank, nobody noticed"
    )


def test_pin_freshness_gate_is_honest(capsys: pytest.CaptureFixture[str]) -> None:
    """Factory#519's watchdog, held to this file's three criteria.

    Its scope has TWO registries that can shrink independently — SERVICE_LAYOUTS
    (imported, shared with the byte gate) and the repo mapping that turns a
    service into a pin URL. Losing either stops a service being checked while the
    remaining ones still pass, so both are mutated below.

    The pass path matters as much as the fail path here. This watchdog is green
    almost always, so a green run that stopped enumerating is the realistic way
    it rots.
    """
    now = int(time.time())
    head = pin_gate._git("rev-parse", "HEAD").strip()

    # PASS path: every service named, every module it vendors enumerated.
    failures, report = pin_gate.check(dict.fromkeys(pin_gate._REPOS, head), now=now)
    assert not failures
    out = "\n".join(report)
    for service, modules in vcore_gate.SERVICE_LAYOUTS.items():
        assert service in out, f"the report never named {service}"
        for module in modules:
            assert module in out, f"{service}'s vendored {module} was never enumerated"

    # Observed FAILING, on a real pin that really did go stale (Factory#536 moved
    # scripts/ratchet_helpers.py after CFactory pinned a9f44033). Needs real
    # history, so it names its own precondition rather than dying on "Invalid
    # revision range" under a shallow clone.
    stale = "a9f44033dbb041d8a1468226c6325ea1f175a264"
    if subprocess.run(  # noqa: S603
        ["git", "cat-file", "-e", f"{stale}^{{commit}}"],  # noqa: S607
        cwd=_SCRIPTS.parent,
        capture_output=True,
        check=False,
    ).returncode:
        pytest.fail(
            f"needs the full hub history; {stale[:8]} is not in this clone. "
            "CI must check out with fetch-depth: 0 (see contracts.yml)."
        )
    failures, report = pin_gate.check({"cfactory": stale}, now=now)
    assert failures, "a pin behind a module the service vendors must fail"
    assert any("a9f44033" in line for line in failures), "the failure never cited the pin"

    # Configuration mutation 1: the service leaves SERVICE_LAYOUTS. Nothing about
    # the pins changes; the gate must refuse rather than check one fewer.
    dropped = vcore_gate.SERVICE_LAYOUTS.pop("cfactory")
    try:
        assert pin_gate.scope_problems(), (
            "a service dropped from SERVICE_LAYOUTS left the gate with nothing to "
            "say — scope shrank, nobody noticed"
        )
        assert pin_gate.main(["--no-fetch", "--pin", "pfactory=" + head]) == 2
    finally:
        vcore_gate.SERVICE_LAYOUTS["cfactory"] = dropped

    # Configuration mutation 2: the repo mapping loses an entry, so that service
    # has no pin to fetch and silently stops being covered.
    removed = pin_gate._REPOS.pop("tfactory")
    try:
        assert pin_gate.scope_problems(), (
            "a service with no repo mapping is never fetched and never checked, "
            "and the run stayed green"
        )
    finally:
        pin_gate._REPOS["tfactory"] = removed

    capsys.readouterr()


def test_chart_vs_gitops_gate_is_honest(capsys: pytest.CaptureFixture[str]) -> None:
    """Factory#504's comparator, held to this file's three criteria.

    Its scope is three registries that can shrink independently: the service
    list, the compared securityContext fields, and the waivers. Narrowing any of
    them leaves every remaining case passing, which is the variant-3 shape.
    """
    hard_pod = {
        "runAsNonRoot": True,
        "runAsUser": 65532,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    hard_ctr = {
        "allowPrivilegeEscalation": False,
        "capabilities": {"drop": ["ALL"]},
        "readOnlyRootFilesystem": True,
    }
    values = {"podSecurityContext": hard_pod, "containerSecurityContext": hard_ctr}

    def manifests(ctr: dict[str, object]) -> list[dict[str, object]]:
        return chart_gate.synthetic_manifests(hard_pod, ctr)

    # PASS path enumerates every field it compared, rather than counting them.
    agree = chart_gate.compare_service("svc", values, manifests(hard_ctr))
    assert not agree.failures
    out = "\n".join(agree.report)
    for field_name in (*chart_gate.POD_FIELDS, *chart_gate.CONTAINER_FIELDS):
        assert field_name in out, f"the report never named {field_name}"

    # Observed FAILING, on the Factory#503 shape it was built for.
    missing = chart_gate.compare_service("svc", values, manifests({}))
    assert missing.failures
    assert any("readOnlyRootFilesystem" in f for f in missing.failures)

    # Configuration mutation 1: a compared FIELD leaves the set. The engines are
    # untouched; the gate must stop claiming it checked that field.
    kept = chart_gate.CONTAINER_FIELDS
    chart_gate.CONTAINER_FIELDS = tuple(f for f in kept if f != "readOnlyRootFilesystem")
    try:
        narrowed = chart_gate.compare_service("svc", values, manifests({}))
        assert not any("readOnlyRootFilesystem" in f for f in narrowed.failures), (
            "sanity: the narrowed set should no longer report it"
        )
        assert "readOnlyRootFilesystem" not in "\n".join(narrowed.report), (
            "a dropped field must vanish from the REPORT too — a report still "
            "naming a field nobody compares is worse than one that omits it"
        )
    finally:
        chart_gate.CONTAINER_FIELDS = kept

    # Configuration mutation 2: a waiver loses its reason. The waiver list is the
    # escape hatch, so an unexplained entry is the silent exemption this gate ends.
    assert all(w.reason and w.tracked_by for w in chart_gate.WAIVERS)

    capsys.readouterr()
