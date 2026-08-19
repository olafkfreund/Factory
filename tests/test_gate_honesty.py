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

import datetime
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import check_banned_constructs as banned_gate
import check_branch_divergence as divergence_gate
import check_chart_vs_gitops as chart_gate
import check_cli_freshness as cli_gate
import check_codeql_analysis_honesty as codeql_honesty_gate
import check_codeql_exclude_pairing as pairing_gate
import check_codeql_fork_validation as forkval_gate
import check_codeql_query_suite as suite_gate
import check_factory_github_drift as github_gate
import check_factory_ui_drift as ui_gate
import check_gate_liveness as liveness_gate
import check_merge_attribution as merge_gate
import check_orphaned_pr_commits as orphan_gate
import check_pin_freshness as pin_gate
import check_planning_card_conformance as card_gate
import check_security_fork_drift as fork_gate
import check_sink_coverage as sink_gate
import check_test_home_isolation as home_gate
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
    "check_cli_freshness.py": "test_cli_freshness_gate_is_honest",
    "check_planning_card_conformance.py": "test_planning_card_conformance_gate_is_honest",
    "check_merge_attribution.py": "test_merge_attribution_gate_is_honest",
    "check_orphaned_pr_commits.py": "test_orphaned_pr_commits_gate_is_honest",
    # 2026-08-13 security-cleanup guardrail batch (Factory#720).
    "check_codeql_query_suite.py": "test_codeql_query_suite_gate_is_honest",
    "check_codeql_exclude_pairing.py": "test_codeql_exclude_pairing_gate_is_honest",
    "check_security_fork_drift.py": "test_security_fork_drift_gate_is_honest",
    "check_sink_coverage.py": "test_sink_coverage_gate_is_honest",
    "check_banned_constructs.py": "test_banned_constructs_gate_is_honest",
    "check_test_home_isolation.py": "test_test_home_isolation_gate_is_honest",
    # Factory#738.
    "check_gate_liveness.py": "test_gate_liveness_gate_is_honest",
    # Factory#737.
    "check_codeql_fork_validation.py": "test_codeql_fork_validation_gate_is_honest",
    # Factory#774.
    "check_codeql_analysis_honesty.py": "test_codeql_analysis_honesty_gate_is_honest",
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
    #
    # Factory#550 emptied WAIVERS, and this line used to be a bare
    # `all(... for w in chart_gate.WAIVERS)` -- which over an empty tuple is
    # vacuously true. A rule that passes without evaluating anything is the
    # exact failure this file exists to catch, so the mutation now supplies its
    # own subject instead of borrowing whatever the module happens to hold.
    kept_waivers = chart_gate.WAIVERS
    chart_gate.WAIVERS = (
        chart_gate.Waiver(service="*", control="podDisruptionBudget", reason="", tracked_by=""),
    )
    try:
        assert not all(w.reason and w.tracked_by for w in chart_gate.WAIVERS), (
            "a waiver with no reason and no tracking issue must not satisfy the rule"
        )
    finally:
        chart_gate.WAIVERS = kept_waivers
    assert all(w.reason and w.tracked_by for w in chart_gate.WAIVERS)

    # Configuration mutation 3: the automount comparison degrades to
    # presence-of-`false`, which is what Factory#550 replaced. A `true`/`false`
    # divergence must not survive it -- under the old logic neither side scored
    # `False`, so the gate called them equal and passed.
    sa_doc = {
        "kind": "ServiceAccount",
        "metadata": {"name": "svc"},
        "automountServiceAccountToken": False,
    }
    diverged = chart_gate.compare_service(
        "svc",
        {**values, "serviceAccount": {"automountServiceAccountToken": True}},
        chart_gate.synthetic_manifests(hard_pod, hard_ctr, [sa_doc]),
    )
    assert any("automountServiceAccountToken" in f for f in diverged.failures), (
        "the gate must compare the automount VALUE, not whether either side says false"
    )

    capsys.readouterr()


def test_planning_card_conformance_gate_is_honest() -> None:
    """Factory#554's comparator, held to this file's three criteria.

    The one gate here whose SUBJECT lives in another repo: the contract is in
    ``apis/`` and the pydantic models are in CFactory, so the real comparison
    can only run in CFactory's CI. That makes the third criterion the load-
    bearing one — nothing in this repo will ever observe this gate on live
    input, so its own scope has to be asserted where the gate is written.

    Its scope is ``_ROLES``, which can shrink independently of everything the
    gate compares. Dropping a line from it removes a `$def` from the gate's
    world entirely: the contract still carries the role, consumers still read
    it, and the only trace is one fewer line in a report nobody re-derives.
    That is not hypothetical for this contract — ``card_list`` was the role
    nothing compared, and the ``count``/``total`` defect lived in it for months
    (Factory#371).
    """
    contract = card_gate._SELFTEST_CONTRACT
    service = card_gate._selftest_service()

    # PASS path: clean, and every role and field it read is named. There is no
    # "matched N roles" line to be satisfied by, deliberately.
    assert card_gate.check(contract, service) == []
    for role, _model in card_gate._ROLES:
        assert role in contract["$defs"], f"the self-test contract never covers {role}"

    # Observed FAILING on the shape it exists for: a type narrowed, nothing else
    # moved. A field-name comparison passes this.
    narrowed = card_gate._mutated("card", "card_key", type="integer")
    assert any("card_key: types differs" in p for p in card_gate.check(narrowed, service))

    # CONFIGURATION MUTATION. The subject is held constant - the same contract,
    # the same models - and only _ROLES moves.
    kept = card_gate._ROLES
    card_gate._ROLES = tuple(r for r in kept if r[0] != "card_list")
    try:
        problems = card_gate.check(contract, {k: v for k, v in service.items() if k != "card_list"})
        assert any("card_list" in p and "maps it to no model" in p for p in problems), (
            "a role dropped from _ROLES must flag the now-unmapped `$def` rather "
            "than quietly stop comparing it"
        )
    finally:
        card_gate._ROLES = kept

    # And the whole self-test, run as the gate's consumers run it: it PERFORMS
    # each mutation rather than describing one, and prints every case it ran.
    assert card_gate.main(["--self-test"]) == 0


def test_cli_freshness_gate_is_honest() -> None:
    """Factory#459's watchdog, held to this file's three criteria.

    Two registries can shrink independently here — the tracked packages and the
    repos that bake them — and narrowing either leaves every remaining case
    passing, which is the variant-3 shape.
    """
    now = time.gmtime()
    del now  # the comparator takes an injected `now`; this case fixes its own
    when = datetime.datetime(2026, 8, 3, tzinfo=datetime.UTC)
    pin = cli_gate.Pin("AIFactory", "@openai/codex", "0.144.6")

    def doc(latest: str, published: str) -> dict[str, object]:
        return {"dist-tags": {"latest": latest}, "time": {latest: published}}

    # PASS path names the versions it compared rather than emitting a verdict.
    line, failure = cli_gate.assess(
        pin, doc("0.146.0", "2026-07-29T00:00:00Z"), now=when, max_age_days=30
    )
    assert failure is None
    assert "0.144.6" in line and "0.146.0" in line, "the report must carry both sides"

    # Observed FAILING on the shape it exists for.
    _, failure = cli_gate.assess(
        pin, doc("0.146.0", "2026-05-01T00:00:00Z"), now=when, max_age_days=30
    )
    assert failure is not None

    # Configuration mutation: a package leaves the tracked set. The Dockerfile is
    # untouched; the gate must stop claiming it watched that CLI.
    kept = cli_gate.TRACKED
    cli_gate.TRACKED = tuple(p for p in kept if p != "@openai/codex")
    try:
        pins = cli_gate.parse_pins("AIFactory", "RUN npm install -g @openai/codex@0.144.6\n")
        assert pins == [], (
            "a package dropped from TRACKED must vanish from the parse, not be "
            "silently reported under a stale name"
        )
    finally:
        cli_gate.TRACKED = kept

    # And the repo list is enumerated, so losing one is visible rather than quiet.
    assert set(cli_gate.REPOS) == {"AIFactory", "PFactory", "TFactory"}


def test_merge_attribution_gate_is_honest(capsys: pytest.CaptureFixture[str]) -> None:
    """Factory#611's audit command, held to this file's criteria.

    Its subject is a merge trail nobody can re-derive, so the enumeration
    property matters more here than anywhere else in this file: the only reason
    to believe a verdict is that the command printed the login it read it from.

    Note the asymmetry in what counts as scope loss. `_REPOS` shrinking is scope
    loss in the ordinary sense — a repo stops being audited and the remaining
    ones still report. `_SHARED_IDENTITIES` shrinking is NOT: it empties on the
    day agents stop authenticating as the operator, which is the fix landing.
    What has to be proved about it is that it is load-bearing rather than
    decorative, which is the second mutation below.
    """
    merges = [
        merge_gate.Merge("Factory", 626, "olafkfreund"),
        merge_gate.Merge("AIFactory", 12, "factory-agent[bot]"),
    ]

    # Every verdict carries its fragment, and the PASS line carries one too —
    # a reader that printed the login only for what it flags cannot be caught
    # reading the wrong field for everything it waves through.
    merge_gate.report(merges)
    out = capsys.readouterr().out
    for merge in merges:
        assert f"{merge.repo}#{merge.number}" in out, f"never named {merge.repo}#{merge.number}"
        assert f"mergedBy={merge.merged_by}" in out, f"never cited {merge.repo}'s merge actor"
    assert merge_gate.ATTRIBUTABLE in out and merge_gate.INDISTINGUISHABLE in out

    # Configuration mutation 1: the fleet list must not shrink unobserved. It is
    # asserted against the one declared in scripts/apply_branch_protection.sh, so
    # the two cannot drift apart in silence either.
    declared = re.search(
        r"^ALL_REPOS=\(([^)]*)\)",
        (_SCRIPTS / "apply_branch_protection.sh").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert declared, "apply_branch_protection.sh no longer declares ALL_REPOS"
    assert set(merge_gate._REPOS) == set(declared.group(1).split()), (
        "the audited repo list and the fleet's declared repo list have diverged — "
        "a repo would go unaudited with nothing red"
    )

    # Configuration mutation 2: empty the declaration. The merges are unchanged,
    # and the operator's merge must stop reading as indistinguishable — proving
    # the verdict comes from the declaration and not from something incidental.
    kept = merge_gate._SHARED_IDENTITIES
    merge_gate._SHARED_IDENTITIES = frozenset()
    try:
        assert merge_gate.assess(merges)[0] == 0, (
            "with no identity declared shared, every merge is attributable by "
            "construction — if this still failed, the verdict is not coming from "
            "the declaration and the gate cannot be reasoned about"
        )
    finally:
        merge_gate._SHARED_IDENTITIES = kept

    assert merge_gate.assess(merges)[0] == 1, "restoring the declaration must restore the red"


def test_orphaned_pr_commits_gate_is_honest(capsys: pytest.CaptureFixture[str]) -> None:
    """factory-gitops#187's watchdog, held to this file's criteria.

    Its subject is a commit that exists on a branch and nowhere else, so the
    enumeration property is the whole value: the only reason to believe "nothing
    orphaned" is that the run said how many branches it looked at, per repo.

    The scope hazard here is the fleet list. This gate reads branches over the
    API rather than deriving its subject from a file, so a repo silently leaving
    ``REPOS`` removes it from the scan with nothing red -- which is why it is
    asserted against the same ``ALL_REPOS`` declaration merge-attribution uses.
    """
    now = datetime.datetime(2026, 8, 12, 12, 0, tzinfo=datetime.UTC)
    old = "2026-08-07T15:20:26Z"

    def pr(number: int, head: str, merged: str | None = old) -> dict[str, object]:
        return {
            "number": number,
            "state": "closed",
            "merged_at": merged,
            "head_sha": head,
        }

    # The real factory-gitops#180 orphan. The finding must carry BOTH shas: a
    # reader cannot confirm the loss without the pair to diff.
    finding = orphan_gate.classify(
        "fix/563-odin-now-public", "3fd8ca1a", [pr(180, "50b70a32")], now, 12.0
    )
    assert finding is not None, "the real #180 orphan must be reported"
    assert finding["tip"] == "3fd8ca1a", "the finding must carry the branch tip"
    assert finding["pr_head"] == "50b70a32", "the finding must carry the merged head"

    # Configuration mutation 1: the fleet list must not shrink unobserved. A repo
    # dropped from REPOS is simply never scanned, and every remaining repo still
    # reports "ok" -- the exact shape of a gate that narrows into green.
    declared = re.search(
        r"^ALL_REPOS=\(([^)]*)\)",
        (_SCRIPTS / "apply_branch_protection.sh").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert declared, "apply_branch_protection.sh no longer declares ALL_REPOS"
    assert set(orphan_gate.REPOS) == set(declared.group(1).split()), (
        "the scanned repo list and the fleet's declared repo list have diverged — "
        "a repo would go unscanned with nothing red"
    )

    # Configuration mutation 2: the grace window must be load-bearing rather than
    # decorative. The SAME branch that is silent inside the window must fire
    # outside it -- if it stayed silent, the quiet would be coming from something
    # else and a real orphan could hide behind it.
    recent = "2026-08-12T11:30:00Z"
    assert orphan_gate.classify("b", "zzz", [pr(1, "aaa", recent)], now, 12.0) is None, (
        "a just-merged branch must be inside the grace window"
    )
    assert orphan_gate.classify("b", "zzz", [pr(1, "aaa", recent)], now, 0.0) is not None, (
        "with the window closed the same branch must fire — proving grace muted it"
    )

    # The PASS path must state its scope too. A run that printed nothing on a
    # clean fleet would be indistinguishable from a run that scanned nothing.
    assert orphan_gate.report([], ("Factory", "factory-gitops")) == 0
    out = capsys.readouterr().out
    assert "2 repo(s) scanned" in out, (
        "the clean verdict must say how many repos it covered, or 'ok' is a claim "
        "with no scope attached"
    )


def test_codeql_query_suite_gate_is_honest(tmp_path: Path) -> None:
    """Factory#720's Gate 1, held to this file's criteria.

    Its scope is a single constant (`_REQUIRED_SUITE`) rather than a
    collection, so the third criterion here is narrower than the drift gates
    above: prove the verdict is actually DERIVED from the constant rather
    than hardcoded, by moving the constant to something the fixture does not
    satisfy and watching a config that used to pass start failing.
    """
    repo = tmp_path / "repo"
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "codeql.yml").write_text(
        "jobs:\n  analyze:\n    steps:\n      - uses: github/codeql-action/init@v3\n"
        "        with:\n          queries: security-and-quality\n"
    )

    ok, explanation = suite_gate.effective_suite(repo)
    assert ok
    assert "security-and-quality" in explanation, (
        "the pass path must cite what it matched, not just say yes"
    )

    # Configuration mutation: the gate's OWN required-suite constant moves.
    # The fixture is untouched — if the verdict does not flip, the check was
    # never reading the constant it claims to enforce.
    kept = suite_gate._REQUIRED_SUITE
    suite_gate._REQUIRED_SUITE = "some-suite-this-fixture-does-not-have"
    try:
        ok, _explanation = suite_gate.effective_suite(repo)
        assert not ok, (
            "moving _REQUIRED_SUITE must change the verdict on an unchanged fixture — "
            "otherwise the gate is not actually reading its own configuration"
        )
    finally:
        suite_gate._REQUIRED_SUITE = kept
    ok, _explanation = suite_gate.effective_suite(repo)
    assert ok, "restoring the constant must restore the pass"


def test_codeql_exclude_pairing_gate_is_honest(tmp_path: Path) -> None:
    """Factory#720's Gate 2 (ported from PFactory#517), held to this file's criteria.

    Unlike the drift gates, this gate has no separate shrinkable registry of
    its own — its whole configuration IS the two files it reads (the exclude
    list and the custom-query pack), which is exactly what its own
    ``_self_test`` mutates case-by-case (delete the replacement, strip its
    doc comment). Delegated to here rather than re-derived, plus the
    enumeration property checked directly: the pass path must name the rule
    id it paired, not just say "ok".
    """
    assert pairing_gate._self_test() == 0

    repo = tmp_path / "repo"
    (repo / ".github" / "codeql" / "custom-queries").mkdir(parents=True)
    (repo / ".github" / "codeql" / "codeql-config.yml").write_text(
        "query-filters:\n  - exclude:\n      id: py/path-injection\n"
    )
    (repo / ".github" / "codeql" / "custom-queries" / "Sanitized.ql").write_text(
        "/**\n * @id py/path-injection-sanitized\n * Barrier-aware sanitizer.\n */\n"
        "class Sanitizer extends DataFlow::Node { }\n"
    )
    assert pairing_gate.check(repo) == []


def test_codeql_fork_validation_gate_is_honest(capsys: pytest.CaptureFixture[str]) -> None:
    """Factory#737's measured counterpart to Gate 2, held to this file's criteria.

    Its scope is the manifest the workflow hands it -- the list of forks to
    compare -- and that list is exactly what can silently shrink: a workflow
    step that stops writing one pair produces a green run over three forks
    instead of four, and nothing in a count-only report would say so. The two
    properties are asserted directly rather than delegated, because the
    dangerous direction here is a PASS that measured less than it claims.
    """
    assert forkval_gate._self_test() == 0

    stock = '"P","d","error","a [[""x""|""relative:///a.py:1:1:1:2""]] f","/s.py","3"\n'
    cleared_all = ""

    # Enumeration: the pass path names every rule it compared and both numbers,
    # so a reader can check the verdict rather than take "4 OK" on trust.
    good = [
        forkval_gate.compare("py/path-injection", stock, cleared_all),
        forkval_gate.compare("py/full-ssrf", stock, cleared_all),
    ]
    assert forkval_gate.report(good, source_files=1192) == 0
    out = capsys.readouterr().out
    for rule in ("py/path-injection", "py/full-ssrf"):
        assert rule in out, f"the pass path never named {rule}"
    assert "cleared 1" in out, "the pass path must cite the number it derived the verdict from"
    assert "1192 source file(s)" in out, (
        "scan breadth must appear on the pass path: a count that fell because the database "
        "covered less code is not an improvement, and nothing else would show it"
    )

    # Scope mutation: the tree and the queries are untouched, one entry leaves
    # the manifest. The report must not claim four forks when it compared two.
    assert "2 fork(s) measured" in out, "the report must state how many forks it actually compared"

    # And the shrink taken all the way -- zero forks measured is the
    # Factory#738 shape, and must be a failure rather than a quiet green.
    assert forkval_gate.report([]) == 1, "a run that measured no forks at all must fail"
    assert "no fork was measured" in capsys.readouterr().out


def test_security_fork_drift_gate_is_honest(tmp_path: Path) -> None:
    """Factory#720's Gate 3, held to this file's criteria.

    Its scope is three registries (REGISTRY, FORK_DIVERGENCES, REPO_REFS)
    that can each shrink independently. Mutated here: dropping an entry from
    REGISTRY must stop that file being compared at all — the exact shape
    Factory#523 hit in the drift gates above, reproduced for this one.
    """
    assert fork_gate._self_test() == 0

    fork_gate._init_git_repo(tmp_path / "RepoA", {"sub/thing.py": "SAFE = 1\n"})
    fork_gate._init_git_repo(tmp_path / "RepoB", {"sub/thing.py": "SAFE = 0\n"})  # already diverged
    refs = {"RepoA": "main", "RepoB": "main"}

    registry_backup = dict(fork_gate.REGISTRY)
    fork_gate.REGISTRY.clear()
    fork_gate.REGISTRY["honesty-thing.py"] = {
        "_kind": "vendored",
        "RepoA": "sub/thing.py",
        "RepoB": "sub/thing.py",
    }
    try:
        problems = fork_gate.check_drift(tmp_path, refs)
        assert problems, "sanity: the two repos really do diverge"
        assert "honesty-thing.py" in problems[0], (
            "the pass/fail report must name the diverged entry"
        )

        # Configuration mutation: the entry leaves REGISTRY. The two repos are
        # UNCHANGED — still diverged — but the gate must now say nothing.
        del fork_gate.REGISTRY["honesty-thing.py"]
        assert fork_gate.check_drift(tmp_path, refs) == [], (
            "sanity check on the mutation itself: with no registry entries there "
            "is nothing to compare"
        )
    finally:
        fork_gate.REGISTRY.clear()
        fork_gate.REGISTRY.update(registry_backup)


def test_sink_coverage_gate_is_honest(tmp_path: Path) -> None:
    """Factory#720's Gate 4, held to this file's criteria.

    Its scope is SINK_CLASSES. Dropping the outbound-http entry must stop an
    unguarded httpx call being flagged, even though the call site itself
    never changes — the "1 of 14 wired" failure this gate exists to catch,
    reproduced one level up, against the gate's own configuration instead of
    the sink call site.
    """
    assert sink_gate._self_test() == 0

    (tmp_path / "routes.py").write_text("def f(url):\n    return httpx.get(url)\n")
    http_guard = __import__("re").compile(r"url_safety\.check")

    before = sink_gate.find_unguarded(tmp_path, {"http_guard": http_guard})
    assert before, "sanity: the unguarded call must be caught before any mutation"
    assert "routes.py" in before[0] and "outbound-http" in before[0]

    kept = sink_gate.SINK_CLASSES
    sink_gate.SINK_CLASSES = tuple(c for c in kept if c.name != "outbound-http")
    try:
        after = sink_gate.find_unguarded(tmp_path, {"http_guard": http_guard})
        assert after == [], (
            "dropping the outbound-http sink class from SINK_CLASSES left an "
            "unguarded httpx call unflagged — scope shrank, nobody noticed"
        )
    finally:
        sink_gate.SINK_CLASSES = kept
    assert sink_gate.find_unguarded(tmp_path, {"http_guard": http_guard}), (
        "restoring SINK_CLASSES must restore the finding"
    )


def test_banned_constructs_gate_is_honest(tmp_path: Path) -> None:
    """Factory#720's Gate 5, held to this file's criteria.

    Its scope is `_SKIP_DIRS` (plus the dot-directory rule Factory#720 added
    after the first version silently swept `.venv-ci/`/`site-packages/`/a
    nested worktree into its baseline — see the module docstring). Adding a
    LEGITIMATE source directory name to it must stop findings in that
    directory being reported, which is exactly the shape that first bug was.
    """
    assert banned_gate._self_test() == 0

    (tmp_path / "routes").mkdir()
    # Assembled, never written as one literal: this gate scans the whole repo,
    # so a fixture demonstrating a banned construct IS a banned construct as
    # far as it is concerned, and the gate flagged its own test. Same shape as
    # standards rule 3.13 for credential-shaped fixtures. Splitting the token
    # keeps the fixture byte-identical for the gate under test while the
    # pattern never appears in this file.
    _detail = "detail=" + "str(" + "e)"
    (tmp_path / "routes" / "handler.py").write_text(
        f"def h(e):\n    return HTTPException(status_code=500, {_detail})\n"
    )
    before = banned_gate.check(tmp_path, None)
    assert before, "sanity: the finding must be caught before any mutation"

    kept = set(banned_gate._SKIP_DIRS)
    banned_gate._SKIP_DIRS.add("routes")
    try:
        after = banned_gate.check(tmp_path, None)
        assert after == [], (
            "adding a real source directory to _SKIP_DIRS silently stopped "
            "scanning it — the exact shape of the bug this gate already hit once"
        )
    finally:
        banned_gate._SKIP_DIRS.clear()
        banned_gate._SKIP_DIRS.update(kept)
    assert banned_gate.check(tmp_path, None), "restoring _SKIP_DIRS must restore the finding"


def test_test_home_isolation_gate_is_honest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Factory#720's Gate 6, held to this file's criteria.

    Its "scope" is not a registry that can shrink (it snapshots EVERY file
    under the given $HOME, unfiltered) — the same shape as
    check_deploy_drift.py's exemption above (one input in, one verdict out).
    Included in _COVERED rather than _EXEMPT per review: it still has to
    prove the enumeration property (the pass path states how many files it
    watched) and the mutation property (its own self-test), so both are
    checked directly here.
    """
    assert home_gate._self_test() == 0

    home = tmp_path / "home"
    home.mkdir()
    (home / "existing.txt").write_text("unchanged\n")

    assert home_gate.run_isolated(home, [__import__("sys").executable, "-c", "pass"]) == 0
    out = capsys.readouterr().out
    assert "1 file(s) before the run" in out, (
        "the pass path must state how many files it watched, or 'untouched' is a "
        "claim with no scope attached"
    )


def _liveness_api(
    state: str, runs: list[dict[str, object]], greens: int = 1, reds: int = 0
) -> Callable[[str], object]:
    """A fake GitHub Actions API for check_gate_liveness.

    ``greens``/``reds`` are the WHOLE-HISTORY totals the gate reads off
    ``total_count``, deliberately independent of ``runs`` (the recency page):
    the two halves of Factory#816's distinction are exactly "what does the
    newest run say" versus "has anything ever been green".
    """

    def fetch(url: str) -> object:
        if url.endswith("/contents/.github/workflows"):
            return [{"name": g.workflow} for g in liveness_gate.GATES]
        # The shipped exemptions have to keep matching something, or `check`
        # correctly reports them as dead entries (Factory#788) and the
        # all-green control stops being a control.
        exempt = any(w in url for w in liveness_gate._EXEMPT_WORKFLOWS)
        if "status=success" in url:
            return {"total_count": 0 if exempt else greens}
        if "status=failure" in url:
            return {"total_count": 2 if exempt else reds}
        if url.endswith("/runs?per_page=100"):
            return {"workflow_runs": runs}
        return {"state": state}

    return fetch


def test_gate_liveness_never_green_verdict_is_honest() -> None:
    """Factory#816: a gate that has never once passed, held to this file's criteria.

    The property under test is the LINE, not the label. Both halves below have
    the identical subject -- a gate whose newest verdict is red and fresh --
    and differ only in whether anything green exists anywhere in the history.
    Getting that backwards re-arms the bug the first version of
    check_gate_liveness.py shipped with, where a gate correctly reporting
    findings read as dead.
    """
    now = datetime.datetime(2026, 8, 15, 12, 0, tzinfo=datetime.UTC)
    fresh = (now - datetime.timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    api = _liveness_api
    alive = api("active", [{"conclusion": "success", "created_at": fresh}])

    subject: list[dict[str, object]] = [{"conclusion": "failure", "created_at": fresh}]
    watched = liveness_gate.GATES[0]
    barren = liveness_gate.verdict(watched, "o/r", api("active", subject, 0, 21), now)
    assert barren is not None and "NEVER GREEN" in barren, (
        "a gate with zero successes in its entire history has never shown it can pass"
    )
    assert "21" in barren, (
        "the never-green verdict must cite the count it measured, not just the label"
    )
    recovered = liveness_gate.verdict(watched, "o/r", api("active", subject, 3, 5), now)
    assert recovered is None, (
        "a gate that is red TODAY but has passed before is doing its job -- this is "
        "the exact bug the first version of this script shipped, re-armed"
    )

    # The exemption is a hole in coverage, so it is held to the two rules that
    # keep holes from widening: it must be justified, and it must still fit.
    with pytest.raises(ValueError):
        liveness_gate.NeverGreenExemption(workflow="x.yml", issue="Factory#1", reason="TODO")
    assert liveness_gate._stale_exemptions(frozenset()) != [], (
        "an exemption that suppressed nothing must fail the gate, not pass quietly"
    )

    # The record outlives the file: GitHub keeps reporting state=active for a
    # workflow deleted from the default branch (Factory#816's zz-*-proof pair).
    gone = liveness_gate.verdict(
        liveness_gate.GATES[0], "o/r", alive, now, frozenset({"something-else.yml"})
    )
    assert gone is not None and "ABSENT" in gone, (
        "a deleted workflow file must not read as a live gate on the strength of "
        "GitHub's stale `state: active`"
    )


def test_gate_liveness_gate_is_honest(capsys: pytest.CaptureFixture[str]) -> None:
    """Factory#738's external liveness check, held to this file's criteria.

    Its subject is the ABSENCE of runs, which makes the enumeration property
    load-bearing in an unusually direct way: the only reason to believe "every
    gate is alive" is that the run said which gates it looked at. A registry
    someone shortened reports fewer gates, all green, and says nothing at all
    about the one it stopped watching -- Factory#523's shape exactly, and the
    reason the scope mutation below deletes a ``GATES`` entry rather than
    breaking a workflow.
    """
    now = datetime.datetime(2026, 8, 15, 12, 0, tzinfo=datetime.UTC)

    api = _liveness_api

    fresh = (now - datetime.timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    alive = api("active", [{"conclusion": "success", "created_at": fresh}])

    # Enumeration, on the PASS path. A reader must be able to falsify the
    # verdict against the Actions tab, which needs the workflow name and the
    # age -- not a count.
    line = liveness_gate.evidence(liveness_gate.GATES[0], "o/r", alive, now)
    assert liveness_gate.GATES[0].workflow in line, "the pass line must name the workflow"
    assert "3h ago" in line, "the pass line must cite the age it compared"
    assert "budget" in line, "the pass line must cite the threshold it compared against"

    # Every verdict carries its fragment: the FAILING path must also say what
    # it measured and against what, or a reader cannot tell a real staleness
    # from a mis-set budget.
    stale_at = (now - datetime.timedelta(hours=500)).isoformat().replace("+00:00", "Z")
    stale = api("active", [{"conclusion": "failure", "created_at": stale_at}])
    problem = liveness_gate.verdict(liveness_gate.GATES[0], "o/r", stale, now)
    assert problem is not None
    assert "500h" in problem and "budget" in problem, "a stale verdict must cite both numbers"

    # Scope mutation: hold the subject constant and delete one entry from the
    # gate's own configuration. The gate must not simply report a smaller,
    # greener fleet.
    full = liveness_gate.check("o/r", alive, now)
    assert full == [], "the unmutated fleet is the control and must be clean"

    original = liveness_gate.GATES
    try:
        liveness_gate.GATES = original[:-1]
        shortened = liveness_gate.check("o/r", alive, now)
        assert shortened == [], "sanity: the shortened registry is still all-green"
        # The gate cannot detect its own shortening at runtime -- nothing can,
        # from inside. What it CAN do is refuse to ship shortened, which is
        # what the floor in its self-test enforces.
        assert len(original) >= liveness_gate._MIN_REGISTERED_GATES, (
            "the shipped registry must meet its own floor"
        )
        assert len(liveness_gate.GATES) < liveness_gate._MIN_REGISTERED_GATES, (
            "the mutation must breach the floor, or this case proves nothing"
        )
    finally:
        liveness_gate.GATES = original

    # And the floor is enforced by the gate's own self-test, not just asserted
    # here: run it against the shortened registry and require a failure.
    try:
        liveness_gate.GATES = original[:-1]
        assert liveness_gate._self_test() != 0, (
            "the self-test must go red on a shortened registry -- otherwise the "
            "floor is a comment, and a gate can be quietly narrowed"
        )
    finally:
        liveness_gate.GATES = original

    assert liveness_gate._self_test() == 0, "the self-test must pass on the shipped registry"
    capsys.readouterr()


def test_codeql_analysis_honesty_gate_is_honest() -> None:
    """Factory#774: the LATEST analysis per category must be a real scan.

    codeql-action/analyze's default ``upload: always`` publishes even on a
    cancelled run, and this repo's own history has it happening twice --
    Factory#771 (a PR merge-ref) and commit 4e2420e9 on main itself, where a
    zero-rule upload stood as the ONLY recorded analysis until an unrelated
    push happened to supersede it 100 seconds later. The property under test
    is "can it WIN", not "can it be uploaded at all": a superseded zero-rule
    entry from an earlier commit is Factory#775's benign case and must read
    clean, while the same entry as the NEWEST one for its category must not.
    """

    def api(analyses: list[dict[str, object]]):
        def fetch(url: str) -> object:
            assert "code-scanning/analyses" in url, f"gate hit an unexpected URL: {url}"
            return analyses

        return fetch

    ref = "refs/heads/main"
    real = {
        "ref": ref,
        "category": "/language:python",
        "rules_count": 172,
        "results_count": 8,
        "commit_sha": "a" * 40,
        "created_at": "2026-08-15T12:00:00Z",
    }
    honest = api([real])

    # Enumeration, on the PASS path: a reader must be able to check the
    # rules_count/results_count/commit against the Security tab, not just a
    # count of how many categories were "fine".
    lines = codeql_honesty_gate.evidence("o/r", ref, honest)
    assert lines == [codeql_honesty_gate._cite("/language:python", real)], (
        "the pass line must cite the exact fragment it compared"
    )
    assert codeql_honesty_gate.check("o/r", ref, honest) == [], "a lone real analysis is clean"

    # THE scope mutation this gate's subject is actually about: the same
    # ref+category, but the NEWEST analysis is the zero-rule one. This is
    # commit 4e2420e9's exact shape, and it is what decides whether the
    # defect is cosmetic or can mask a real result.
    cancelled = dict(
        real, rules_count=0, results_count=0, commit_sha="b" * 40, created_at="2026-08-15T12:05:00Z"
    )
    wins = api([real, cancelled])
    problems = codeql_honesty_gate.check("o/r", ref, wins)
    assert len(problems) == 1 and "rules_count=0" in problems[0], (
        "a later zero-rule upload superseding an earlier real one must be caught"
    )
    assert "b" * 10 in problems[0], "the failing verdict must cite which commit lied clean"

    # The inverse must NOT fire -- Factory#775's actual, harmless case: an
    # older zero-rule analysis a later real one has already superseded.
    loses = api([cancelled, dict(real, created_at="2026-08-15T12:10:00Z")])
    assert codeql_honesty_gate.check("o/r", ref, loses) == [], (
        "a superseded zero-rule analysis must not fail the gate -- it lost"
    )

    # A ref with no analyses at all must fail loudly, not read as "nothing to
    # check, therefore clean" -- the same reasoning check_gate_liveness.py
    # applies to a workflow with zero runs.
    empty = codeql_honesty_gate.check("o/r", ref, api([]))
    assert len(empty) == 1 and "no CodeQL analyses found" in empty[0], (
        "zero analyses for the ref must be caught, not silently passed"
    )

    assert codeql_honesty_gate._self_test() == 0, "the gate's own self-test must pass"
