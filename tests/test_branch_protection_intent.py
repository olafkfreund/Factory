#!/usr/bin/env python3
"""Offline tests for the branch-protection drift gate (Factory#468).

``scripts/apply_branch_protection.sh`` compares the protection GitHub reports
live against the intent declared in its own table. The load-bearing part is the
normaliser: the live API wraps booleans as ``{"enabled": bool}``, returns the
required-check list as either ``.contexts`` or ``.checks[].context``, and omits
``.restrictions`` when unset, while the intent payload uses bare booleans. If the
normaliser disagreed between the two shapes the gate would be either
always-red (annoying, self-correcting) or always-green -- and an always-green
drift gate is the defect one level up from the drift it was added to catch.

These tests need no token and no network: they drive the script's ``--emit`` and
``--normalise-stdin`` hooks. Both directions are proved, per
standards/coding-standards.md rule 4.9 -- a live response matching intent
compares equal, and a live response differing in ONE field compares unequal.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "apply_branch_protection.sh"

# Every repo/branch pair the intent table declares. Keep in step with
# repo_config()'s BRANCHES field.
_DECLARED = [
    ("CFactory", "main"),
    ("CFactory", "dev"),
    ("Factory", "main"),
    ("PFactory", "main"),
    ("PFactory", "dev"),
    ("TFactory", "main"),
    ("TFactory", "dev"),
    ("AIFactory", "main"),
    ("AIFactory", "dev"),
    ("factory-gitops", "main"),
]


def _all_repos() -> set[str]:
    """The fleet, read from the script's own ``ALL_REPOS`` array."""
    src = _SCRIPT.read_text(encoding="utf-8")
    m = re.search(r"^ALL_REPOS=\(([^)]*)\)", src, re.MULTILINE)
    assert m, "ALL_REPOS not found in apply_branch_protection.sh"
    repos = set(m.group(1).split())
    assert repos, "ALL_REPOS parsed as empty -- the regex stopped matching"
    return repos


def _emit(repo: str, branch: str) -> dict:
    # S603/S607: fixed argv, no shell, and the only interpolated values are the
    # literal repo/branch names from _DECLARED in this file. The gate under test
    # is a shell script, so running it is the point.
    out = subprocess.run(  # noqa: S603
        ["bash", str(_SCRIPT), "--emit", repo, branch],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def _stdin_hook(mode: str, payload: dict[str, object]) -> str:
    """Drive one of the script's offline stdin hooks; returns its stdout.

    Shared by the two hooks rather than copy-pasted per hook: a second body
    identical to the first but for the flag is exactly the paste the clone budget
    exists to stop (Factory#415).
    """
    out = subprocess.run(  # noqa: S603
        ["bash", str(_SCRIPT), mode],  # noqa: S607
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


def _declared_contexts(repo: str, branch: str) -> list[str]:
    """The contexts the script declares for a branch, for fixtures to start from.

    Hard-coded copies of these lists went stale twice -- once when the P0
    acceptance gate was promoted (Factory#814) and again for CodeQL and the
    security sinks (Factory#943). Both times the failure was
    ``fixture must start clean``, in a test whose subject is the COMPARATOR, not
    the list. Deriving removes a maintenance trap without weakening anything:
    the exact per-repo lists are pinned by
    ``test_check_contexts_are_per_repo``, and a mutation test that starts from
    the real declaration still has to detect the mutation.
    """
    return list(_emit(repo, branch)["required_status_checks"]["contexts"])


def _normalise(payload: dict) -> dict:
    return json.loads(_stdin_hook("--normalise-stdin", payload))


# The verification-core drift gate's job display name, identical in all four
# consumers. Required there since Factory#543 — its own header called it a
# "Blocking drift gate" while it was required nowhere.
_VCORE = "vendored copies match the hub canonical (byte-exact)"

# The PR-diff secret scan, required fleet-wide as of Factory#814. Three
# spellings because the job display names genuinely differ: PFactory
# capitalises it, the other three services do not, and the hub's single job is
# just "gitleaks". NOT the full-history job in the same workflow -- that one is
# gated to schedule/workflow_dispatch and never posts on a PR, so requiring it
# would block every PR in the fleet.
_GITLEAKS_PF = "Gitleaks (PR diff)"
_GITLEAKS = "gitleaks (PR diff)"
_GITLEAKS_HUB = "gitleaks"
# gitops names neither secret-scan job, so the context IS the job id. Verified
# against a real PR head rather than read off the YAML: `pr-diff-scan` reports
# success there and `full-history-scan` reports skipped.
_GITLEAKS_GITOPS = "pr-diff-scan"

# The P0 container acceptance suite, required on dev as of Factory#814.
# PFactory#586 is why: it went red on the causing PR twice, the PR merged anyway
# because the gate was advisory, and dev shipped a container that could not
# start. Required on dev only -- main takes sync merges whose checks already ran
# on dev, so requiring it there adds a wedge risk and buys nothing.
_ACCEPT = "docker (P0 acceptance)"
# Factory#943 part 1. CodeQL reports one context per matrix language, not a
# single roll-up, and AIFactory's job is spelled lowercase where the other four
# capitalise it -- required contexts match case-sensitively, so the two spellings
# are not interchangeable.
_CODEQL = ["Analyze (actions)", "Analyze (javascript-typescript)", "Analyze (python)"]
_CODEQL_AI = ["analyze (actions)", "analyze (javascript-typescript)", "analyze (python)"]
_SINKS = "security sinks (whole repo)"


def _live_shaped(
    *,
    contexts: list[str],
    strict: bool,
    reviews: int | None,
    code_owner: bool = False,
    conversation_resolution: bool,
) -> dict:
    """A protection object shaped the way the GitHub GET endpoint returns it."""
    doc: dict = {
        "url": "https://api.github.com/...",
        "required_signatures": {"enabled": False},
        "enforce_admins": {"enabled": False},
        "required_linear_history": {"enabled": False},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "block_creations": {"enabled": False},
        "required_conversation_resolution": {"enabled": conversation_resolution},
        "lock_branch": {"enabled": False},
        "allow_fork_syncing": {"enabled": False},
    }
    if contexts:
        doc["required_status_checks"] = {
            "strict": strict,
            "contexts": contexts,
            "checks": [{"context": c, "app_id": None} for c in contexts],
        }
    if reviews is not None:
        doc["required_pull_request_reviews"] = {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": code_owner,
            "required_approving_review_count": reviews,
            "require_last_push_approval": False,
        }
    return doc


@pytest.mark.parametrize(("repo", "branch"), _DECLARED)
def test_every_declared_branch_emits_intent(repo: str, branch: str) -> None:
    # A declared repo/branch must produce a payload; a typo in BRANCHES would
    # otherwise only surface as a runtime error during a nightly drift run.
    intent = _emit(repo, branch)
    assert set(intent) == {
        "required_status_checks",
        "enforce_admins",
        "required_pull_request_reviews",
        "restrictions",
        "allow_force_pushes",
        "allow_deletions",
        "required_linear_history",
        "required_conversation_resolution",
    }


@pytest.mark.parametrize(("repo", "branch"), _DECLARED)
def test_force_push_and_deletion_always_blocked(repo: str, branch: str) -> None:
    intent = _emit(repo, branch)
    assert intent["allow_force_pushes"] is False
    assert intent["allow_deletions"] is False


@pytest.mark.parametrize("repo", ["CFactory", "PFactory", "TFactory", "AIFactory"])
def test_dev_is_deliberately_looser_than_main(repo: str) -> None:
    """dev carries the same CI checks as main, but is looser about process.

    The argument this file already made for `dev` -- a solo maintainer (and the
    factory's own agents) have nobody to approve their PRs -- holds identically
    on `main`, and Factory#484 is what happens when it is applied to only one of
    them. GitHub forbids approving your own pull request, so a review
    requirement on `main` made EVERY promotion an `--admin` bypass, which also
    skips the required status checks on the way past. The rule was unsatisfiable
    and the effect was less enforcement, not more.

    So no branch requires a review. Since Factory#834 `strict` is on BOTH
    branches, so what now separates them is conversation resolution alone.

    `strict` moved to `dev` because two PRs whose diffs do not overlap can each
    be correctly green and still break the branch together -- TFactory#1121 and
    #1125 did exactly that, and dev was broken for about an hour. The earlier
    intent (dev looser, #455/#468) was a considered decision, reversed with the
    incident data it predated. The review exemption is untouched and the #484
    reasoning above still holds: a merge can satisfy `strict` unaided, but
    cannot approve its own PR.
    """
    main, dev = _emit(repo, "main"), _emit(repo, "dev")

    # Factory#484: unsatisfiable on a single-maintainer account, so every merge
    # became an admin override. Enforcement now comes from the checks.
    assert main["required_pull_request_reviews"] is None
    assert main["required_status_checks"]["strict"] is True
    assert main["required_conversation_resolution"] is True

    assert dev["required_pull_request_reviews"] is None
    assert dev["required_status_checks"]["strict"] is True  # Factory#834
    assert dev["required_conversation_resolution"] is False

    # dev is looser about PROCESS, never about CI. It may be gated MORE:
    # AIFactory's dev is its default branch and carries three checks main
    # does not (#691). The invariant is therefore a superset, not equality --
    # equality would have to be relaxed the first time any repo gates its
    # default branch properly, and relaxing it to "no constraint" is how the
    # stripping in #691 would have gone unnoticed.
    assert set(main["required_status_checks"]["contexts"]) <= set(
        dev["required_status_checks"]["contexts"]
    ), "dev must gate at least everything main gates"


def test_check_contexts_are_per_repo() -> None:
    """CFactory's CI jobs are named differently from the Python services'.

    The bug in Factory#468 was one repo's check names hardcoded into a script
    vendored to repos whose jobs are named differently. Lock the distinction.
    """
    assert _emit("CFactory", "main")["required_status_checks"]["contexts"] == sorted(
        [
            "Backend pytest",
            "Frontend typecheck + build",
            _GITLEAKS,
            _VCORE,
            *_CODEQL,
            _SINKS,
        ]
    )
    assert _emit("TFactory", "main")["required_status_checks"]["contexts"] == sorted(
        [
            "backend (ruff + pytest)",
            "critical (fast PR gate)",
            _GITLEAKS,
            _VCORE,
            *_CODEQL,
            _SINKS,
        ]
    )
    # AIFactory has no required frontend check, despite having a frontend suite.
    assert _emit("AIFactory", "main")["required_status_checks"]["contexts"] == sorted(
        [
            "backend (ruff + pytest)",
            _GITLEAKS,
            _VCORE,
            *_CODEQL_AI,
            _SINKS,
        ]
    )
    # ...but the hub and gitops do NOT carry it: Factory IS the canonical, and
    # factory-gitops vendors none of it. A context required where no such
    # workflow exists can never report, which is the Factory#529 wedge.
    for repo in ("Factory", "factory-gitops"):
        assert _VCORE not in _emit(repo, "main")["required_status_checks"]["contexts"]


def test_every_repo_requires_its_own_secret_scan() -> None:
    """Factory#814, and the three spellings that make it easy to get wrong.

    The display names genuinely differ -- PFactory capitalises the job,
    CFactory/TFactory/AIFactory do not, the hub's is bare ``gitleaks``, and
    gitops names neither job so its context is the job id. Three of the five
    spellings were asserted nowhere when this test was written, including both
    of the ones that are unique to a single repo. A context that is unique and
    unasserted is a typo away from being required-but-never-reported, which
    wedges the branch rather than protecting it (Factory#529).

    Asserting membership rather than the whole list on purpose: the exact
    context lists are locked by test_check_contexts_are_per_repo above, and
    duplicating them here would mean every future gate has to be added twice.
    """
    expected = {
        "CFactory": _GITLEAKS,
        "TFactory": _GITLEAKS,
        "AIFactory": _GITLEAKS,
        "PFactory": _GITLEAKS_PF,
        "Factory": _GITLEAKS_HUB,
        "factory-gitops": _GITLEAKS_GITOPS,
    }
    for repo, ctx in expected.items():
        contexts = _emit(repo, "main")["required_status_checks"]["contexts"]
        assert ctx in contexts, f"{repo} main does not require its secret scan"

    # Every repo in the fleet, not a subset that happens to be listed here. The
    # list is READ from the script's own ALL_REPOS rather than restated, so a
    # repo added there fails this test until it is given a scan -- restating it
    # would just mean the two lists drift and the test keeps passing.
    assert set(expected) == _all_repos(), "a repo exists that this test never checks"


def test_gitops_gates_the_branch_that_reaches_the_cluster() -> None:
    """factory-gitops `main` is what ArgoCD syncs to the live cluster.

    Until factory-gitops#95 this repo had exactly one workflow (`cli-canary`,
    weekly, on its own files) and NO required checks -- the least gated repo in
    the fleet holding the highest blast radius. A malformed manifest reached the
    cluster with nothing in the way. `kustomize build + schema` now runs on
    every PR and is required here.

    The secret scan joined it as required in factory-gitops#209. It had been
    running -- and failing -- on every PR for two months while two live API keys
    sat readable in a PUBLIC repo, because it was optional and a permanently-red
    optional check is one everybody scrolls past. Both are jobs of
    manifest-validate.yml, which deliberately carries no `paths:` filter, so
    requiring the second one cannot strand a manifest-free PR.

    Still no review requirement: bot-driven CD, and one would rest entirely on
    the admin bypass -- the same reason it was removed everywhere else (#484).
    """
    intent = _emit("factory-gitops", "main")
    assert intent["required_pull_request_reviews"] is None
    assert intent["required_status_checks"]["contexts"] == [
        "kustomize build + schema",
        "no literal secrets in manifests",
        _GITLEAKS_GITOPS,
    ]
    assert intent["allow_force_pushes"] is False
    assert intent["allow_deletions"] is False


# --- the comparator, both directions (rule 4.9) ------------------------------


def test_matching_live_response_compares_equal() -> None:
    """A live response that matches intent must normalise to the same JSON.

    If this fails the gate is always-red. Uses the API's own wire shape, so a
    normaliser that only understands the intent shape is caught here.
    """
    # reviews is None on every row now (#484): no branch requires an approving
    # review, because a single-maintainer account cannot supply one and the rule
    # only ever produced admin bypasses. Since Factory#834 dev is strict too, so
    # conversation resolution is the only remaining difference from main.
    for repo, branch, strict, reviews, convres in [
        (
            "TFactory",
            "main",
            True,
            None,
            True,
        ),
        (
            "TFactory",
            "dev",
            True,
            None,
            False,
        ),
        (
            "CFactory",
            "main",
            True,
            None,
            True,
        ),
        # AIFactory@dev is gated MORE than main: it is the default branch and
        # carries the ratchet, the format check and the shared-baseline gate
        # (#691). A single per-repo CHECKS could not express that.
        (
            "AIFactory",
            "dev",
            True,
            None,
            False,
        ),
        # The branch ArgoCD syncs to the cluster, gated at last (gitops#95),
        # with the secret scan able to block since gitops#209.
        (
            "factory-gitops",
            "main",
            True,
            None,
            True,
        ),
    ]:
        code_owner = repo in {"PFactory", "TFactory", "AIFactory"} and reviews is not None
        live = _live_shaped(
            contexts=_declared_contexts(repo, branch),
            strict=strict,
            reviews=reviews,
            code_owner=code_owner,
            conversation_resolution=convres,
        )
        assert _normalise(live) == _emit(repo, branch), f"{repo}@{branch}"


def test_contexts_read_from_checks_when_contexts_absent() -> None:
    # Newer responses may carry only .checks[].context; both spellings must work,
    # or the gate reports a phantom "all checks removed" drift.
    live = _live_shaped(
        contexts=_declared_contexts("AIFactory", "dev"),
        strict=True,  # dev is strict since Factory#834
        reviews=None,
        conversation_resolution=False,
    )
    del live["required_status_checks"]["contexts"]
    assert _normalise(live) == _emit("AIFactory", "dev")


def test_unordered_contexts_compare_equal() -> None:
    # GitHub does not promise an order; a spurious diff would train people to
    # ignore the gate.
    live = _live_shaped(
        # Reversed on purpose: the subject is order-independence, so the fixture
        # must not arrive in the declared order.
        contexts=list(reversed(_declared_contexts("TFactory", "dev"))),
        strict=True,  # dev is strict since Factory#834
        reviews=None,
        conversation_resolution=False,
    )
    assert _normalise(live) == _emit("TFactory", "dev")


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            # Since Factory#834 dev IS strict, so flipping it ON is a no-op and
            # would make this case pass while testing nothing. The divergence
            # worth detecting is protection having drifted back OFF.
            lambda d: d["required_status_checks"].update(strict=False),
            id="strict-flipped-off-on-dev",
        ),
        pytest.param(
            lambda d: d["required_status_checks"]["contexts"].pop(),
            id="required-check-dropped",
        ),
        pytest.param(
            lambda d: d["required_status_checks"]["contexts"].append("frontend (typecheck)"),
            id="extra-required-check-added",
        ),
        pytest.param(
            lambda d: d["required_status_checks"]["contexts"].__setitem__(
                0, "backend (ruff+pytest)"
            ),
            id="check-context-renamed",
        ),
        pytest.param(
            lambda d: d.update(required_conversation_resolution={"enabled": True}),
            id="conversation-resolution-imposed-on-dev",
        ),
        pytest.param(
            lambda d: d.update(enforce_admins={"enabled": True}),
            id="enforce-admins-imposed",
        ),
        pytest.param(
            lambda d: d.update(allow_force_pushes={"enabled": True}),
            id="force-push-unblocked",
        ),
        pytest.param(
            lambda d: d.update(allow_deletions={"enabled": True}),
            id="branch-deletion-unblocked",
        ),
        pytest.param(
            lambda d: d.update(
                required_pull_request_reviews={
                    "dismiss_stale_reviews": True,
                    "require_code_owner_reviews": True,
                    "required_approving_review_count": 1,
                }
            ),
            id="review-requirement-reimposed-on-dev",
        ),
        pytest.param(
            lambda d: d.update(restrictions={"users": [], "teams": [], "apps": []}),
            id="push-restrictions-added",
        ),
        pytest.param(
            lambda d: d.update(required_linear_history={"enabled": True}),
            id="linear-history-imposed",
        ),
    ],
)
def test_one_field_of_divergence_is_detected(mutate) -> None:
    """Mutation-check: change ONE field and the comparator must disagree.

    ``review-requirement-reimposed-on-dev`` is the exact regression Factory#468
    reports -- the old per-repo script applied main's payload to dev.
    """
    live = _live_shaped(
        contexts=_declared_contexts("TFactory", "dev"),
        strict=True,  # dev is strict since Factory#834
        reviews=None,
        conversation_resolution=False,
    )
    assert _normalise(live) == _emit("TFactory", "dev"), "fixture must start clean"
    mutate(live)
    assert _normalise(live) != _emit("TFactory", "dev")


def test_unprotected_branch_is_not_silently_equal() -> None:
    # An empty protection object must never normalise to a real intent, or
    # "protection was deleted" would read as "no drift".
    assert _normalise({}) != _emit("TFactory", "dev")
    assert _normalise({}) != _emit("TFactory", "main")


def test_check_is_the_default_mode() -> None:
    """The default must never be the mode that writes.

    CONTRIBUTING.md points a fresh maintainer at this script; a default that
    overwrites live protection is how Factory#468 happened.
    """
    body = _SCRIPT.read_text()
    assert 'MODE="check"' in body
    # --apply must be an explicit opt-in, and the only path that PUTs.
    put_lines = [ln for ln in body.splitlines() if "gh api -X PUT" in ln]
    assert put_lines, "expected exactly one PUT call site"
    assert body.count("gh api -X PUT") == 1
    assert '--apply) MODE="apply"' in body


def test_missing_token_fails_rather_than_reports_clean() -> None:
    # Rule 4.7: a gate that cannot read its input exits non-zero. Guard the
    # message and the exit-2 path against being softened into a skip.
    body = _SCRIPT.read_text()
    assert "UNDETERMINED" in body
    assert "exit 2" in body
    assert "Branch not found" in body
    assert "Branch not protected" in body


# ── the required contexts must be producible (Factory#529) ──────────────────


def _expand_matrix_names(name: str, wf_text: str) -> set[str]:
    """Expand one `${{ matrix.<key> }}` in a job name into the names it reports.

    A matrix job does not report the literal name written in the YAML: GitHub
    substitutes each matrix value, so `Analyze (${{ matrix.language }})` arrives
    as three separate contexts. Reading the literal made every matrix-named job
    invisible to the check below -- a required context could point at one and
    the guard would call it missing, or (worse, and the reason this matters)
    could point at a MISSPELLED one and the guard could not tell.

    Deliberately simple: one placeholder, and the values are read from the
    `<key>: [a, b, c]` list in the same file. A matrix this parser cannot read
    returns nothing extra, so the caller sees the literal and fails loudly
    rather than silently widening what counts as a real job name.
    """
    m = re.search(r"\$\{\{\s*matrix\.([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}", name)
    if not m:
        return {name}
    key = m.group(1)
    values = re.search(rf"^\s*{re.escape(key)}:\s*\[([^\]]*)\]\s*$", wf_text, re.M)
    if not values:
        return {name}
    expanded = {
        name[: m.start()] + v.strip().strip("\"'") + name[m.end() :]
        for v in values.group(1).split(",")
        if v.strip()
    }
    return expanded or {name}


def _workflow_job_names() -> set[str]:
    """Every `name:` a job in .github/workflows/ can report as a status context."""
    names: set[str] = set()
    for wf in (_REPO_ROOT / ".github" / "workflows").glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            # Job-level `name:` is indented; a workflow-level one is not.
            if stripped.startswith("name:") and line.startswith(" "):
                raw = stripped[len("name:") :].strip().strip("\"'")
                names |= _expand_matrix_names(raw, text)
    return names


def test_every_required_context_matches_a_real_job_name() -> None:
    """A required context no job produces can never be satisfied.

    `main` required `ruff format --check (scripts, blocking)` while the job had
    been renamed to `... (scripts + tests, blocking)`. Nothing compared the two,
    so the drift gate happily reported green -- it compares intent against LIVE,
    and both carried the same stale name. The only way to merge anything was an
    admin bypass, which is how a protection rule becomes weaker than no rule.
    """
    required = set(_emit("Factory", "main")["required_status_checks"]["contexts"])
    missing = sorted(required - _workflow_job_names())
    assert not missing, (
        "these contexts are REQUIRED on Factory/main but no workflow job "
        f"produces them, so they can never report: {missing}"
    )


def test_code_quality_is_not_path_filtered() -> None:
    """Its jobs are required contexts, so it must run on every PR.

    A path-filtered workflow does not report a "skipped" context -- it reports
    nothing, and a required context that never reports blocks the PR forever.
    That made every docs-only PR to main unmergeable (Factory#529).
    """
    wf = (_REPO_ROOT / ".github" / "workflows" / "code-quality.yml").read_text(encoding="utf-8")
    trigger_block = wf.split("jobs:", 1)[0]
    pull_request_section = trigger_block.split("pull_request:", 1)[1].split("push:", 1)[0]
    assert "paths:" not in pull_request_section, (
        "code-quality.yml produces required status contexts; a paths filter "
        "means they never report on a PR that does not match, blocking it forever"
    )


# --- Factory#467: the default branch IS the branching model ------------------


def _repo_table() -> dict[str, dict[str, str]]:
    """Parse `repo_config`'s per-repo declarations out of the script.

    Read from the script text rather than executed, so this stays offline like
    everything else in this file. `--emit` cannot help here: the default branch
    is not part of the protection payload it renders.
    """
    src = (_REPO_ROOT / "scripts" / "apply_branch_protection.sh").read_text(encoding="utf-8")
    table: dict[str, dict[str, str]] = {}
    for line in src.splitlines():
        stripped = line.strip()
        if not stripped.endswith(";;") or ")" not in stripped:
            continue
        repo = stripped.split(")", 1)[0].strip()
        if not repo or not repo[0].isalpha():
            continue
        fields = {}
        for key in ("DEFAULT_BRANCH", "BRANCHES"):
            marker = f'{key}="'
            if marker in stripped:
                fields[key] = stripped.split(marker, 1)[1].split('"', 1)[0]
        # The numeric flags are written unquoted (CODE_OWNER=1), so they need
        # the bare form rather than the quoted one above.
        for key in ("CODE_OWNER", "REVIEWS"):
            marker = f"{key}="
            if marker in stripped:
                fields[key] = stripped.split(marker, 1)[1].split(";", 1)[0].strip()
        if fields:
            table[repo] = fields
    return table


def test_every_declared_repo_names_a_default_branch() -> None:
    """A repo with no declared default is one this check silently skips."""
    table = _repo_table()
    missing = sorted(r for r, f in table.items() if "DEFAULT_BRANCH" not in f)
    assert not missing, f"no DEFAULT_BRANCH declared for: {missing}"
    assert len(table) >= 6, f"expected the whole fleet, parsed only {sorted(table)}"


def test_the_service_repos_default_to_dev() -> None:
    """THE ASSERTION WITH TEETH, and the whole point of Factory#467.

    The branching model was documented in all four repos and followed by 0 of 90
    PRs, because `gh pr create`, the web button, Renovate and every agent target
    the repo DEFAULT when given no --base. Documentation said dev; the default
    said main; the default won every time.

    Flipping one back to main silently restores 0% compliance, so the intended
    value is asserted rather than left as a setting somebody once clicked.
    """
    table = _repo_table()
    for repo in ("CFactory", "PFactory", "TFactory", "AIFactory"):
        assert table[repo]["DEFAULT_BRANCH"] == "dev", f"{repo} must default to dev"
    # The hub and gitops have no dev branch at all: main IS their working branch.
    for repo in ("Factory", "factory-gitops"):
        assert table[repo]["DEFAULT_BRANCH"] == "main"


def test_the_default_branch_is_always_a_protected_one() -> None:
    """A default branch outside BRANCHES would be unprotected by construction.

    Every PR lands there by default, so it is the last branch that should sit
    outside the protection table - and the two lists are declared separately,
    which is exactly how they drift apart.
    """
    for repo, fields in _repo_table().items():
        protected = fields.get("BRANCHES", "").split()
        assert fields["DEFAULT_BRANCH"] in protected, (
            f"{repo}: default branch {fields['DEFAULT_BRANCH']!r} is not in "
            f"BRANCHES {protected} — every PR would land on an unprotected branch"
        )


# --- Factory#611: a CODEOWNERS file that assigns nothing ----------------------


def _codeowners_verdict(payload: dict[str, object]) -> str:
    return _stdin_hook("--codeowners-stdin", payload).strip()


def test_a_codeowners_file_with_no_errors_is_clean() -> None:
    assert _codeowners_verdict({"errors": []}) == "CLEAN"


def test_a_codeowners_owner_without_write_access_is_reported() -> None:
    """The mutation, and it is not hypothetical.

    Measured live 2026-08-07: PFactory, TFactory and AIFactory each carry a root
    CODEOWNERS assigning all 8 rules to an account that is not a collaborator on
    any of them. GitHub ignores every such rule, so those paths have no owner at
    all while the file reads to a reader — an assessor included — as though they
    do. Three files, 24 rules, zero ownership, and nothing noticed.

    If this ever returns CLEAN the check has stopped seeing that, which is the
    state the fleet was already in.
    """
    verdict = _codeowners_verdict(
        {"errors": [{"line": 9, "kind": "Unknown owner"}, {"line": 12, "kind": "Unknown owner"}]}
    )
    assert verdict.startswith("2 rule(s) assign no owner")
    assert "line 9 Unknown owner" in verdict


def test_a_payload_with_no_errors_array_is_unparseable_not_clean() -> None:
    """Rule 4.7 in miniature. `.errors // []` would read an unrecognised response
    shape as "no problems found" — the same false pass this check exists to
    catch, one level up."""
    assert _codeowners_verdict({}) == "UNPARSEABLE"
    assert _codeowners_verdict({"message": "Not Found"}) == "UNPARSEABLE"


def test_codeowners_is_checked_exactly_where_the_intent_declares_an_owner() -> None:
    """Guards against silent scope loss (Factory#523): flipping CODE_OWNER to 0
    would stop the check running with no other visible effect."""
    table = _repo_table()
    declared = {repo for repo, fields in table.items() if fields.get("CODE_OWNER") == "1"}
    assert declared == {"PFactory", "TFactory", "AIFactory"}


# --------------------------------------------------------------------------
# --signatures (Factory#316). The flag is orthogonal to MODE: it selects WHICH
# object is acted on (required_signatures, never the protection object), while
# --apply still selects whether anything is written.
# --------------------------------------------------------------------------


def _signatures(*args: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the script's --signatures path with a `gh` that records its argv.

    The shim is the point, not a convenience: it is the only way to assert that
    a dry-run performs NO write. Asserting on stdout alone would pass just as
    happily against a version that printed "(dry-run)" and then called gh.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "gh-calls"
    # Quote the path: pytest's tmp_path is space-free today, but an unquoted
    # redirect target silently truncates the recording if that ever changes,
    # which would turn "no request was issued" into a false pass.
    (bindir / "gh").write_text(f'#!/usr/bin/env bash\necho "$@" >> "{calls}"\n')
    (bindir / "gh").chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}
    proc = subprocess.run(  # noqa: S603
        ["bash", str(_SCRIPT), "--signatures", *args],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    proc.gh_calls = calls.read_text() if calls.exists() else ""  # type: ignore[attr-defined]
    return proc


def test_signatures_dry_run_writes_nothing(tmp_path: Path) -> None:
    proc = _signatures("--repo", "factory-gitops", tmp_path=tmp_path)
    assert proc.returncode == 0
    assert proc.gh_calls == "", f"dry-run called gh: {proc.gh_calls!r}"  # type: ignore[attr-defined]
    assert "DRY-RUN complete" in proc.stdout


def test_signatures_apply_posts_required_signatures(tmp_path: Path) -> None:
    """The other direction (rule 4.9): a test that only proves the dry-run is
    silent would pass against a --signatures that never writes at all."""
    proc = _signatures("--apply", "--repo", "factory-gitops", tmp_path=tmp_path)
    assert proc.returncode == 0
    assert (
        "repos/olafkfreund/factory-gitops/branches/main/protection/required_signatures"
        in proc.gh_calls  # type: ignore[attr-defined]
    )
    assert "-X POST" in proc.gh_calls  # type: ignore[attr-defined]


def test_signatures_never_reports_on_a_protection_check_it_did_not_run(
    tmp_path: Path,
) -> None:
    """The false-green guard (Factory#642). --signatures reads no live
    protection, so falling through to the check summary would report on a
    comparison this path never performed.

    Asserting only that the OK line is absent would be vacuous: under a stub
    `gh` the fall-through prints DRIFT, not OK, so that assertion holds even
    with the guard deleted. The property that actually separates the two is
    that the path never reaches the live-protection read at all -- so assert
    the summary is absent AND that no request was issued. Deleting the
    `exit 0` on the --signatures path fails this test.
    """
    proc = _signatures("--repo", "Factory", tmp_path=tmp_path)
    assert "live branch protection matches" not in proc.stdout
    assert "DRIFT:" not in proc.stdout
    assert proc.gh_calls == "", f"reached the live read: {proc.gh_calls!r}"  # type: ignore[attr-defined]


def test_every_declared_repo_has_a_signer_preflight(tmp_path: Path) -> None:
    """Enabling required_signatures rejects the next unsigned push from any
    identity. A repo with no pre-flight line is one whose automation breaks
    without warning."""
    proc = _signatures(tmp_path=tmp_path)
    for repo in {r for r, _ in _DECLARED}:
        assert f"olafkfreund/{repo} : main : required_signatures" in proc.stdout
        assert proc.gh_calls == ""  # type: ignore[attr-defined]
    # factory-gitops is the one that freezes deploys; its warning must be loud.
    assert "FREEZES all deploys" in proc.stdout


def test_signatures_refuses_a_repo_with_no_signer_preflight(tmp_path: Path) -> None:
    """An unknown repo must be a hard error, not a printed string.

    `signer pre-flight: $(signers_note "$repo")` sent the unknown-repo message to
    stdout, so an unrecognised repo rendered as
    `signer pre-flight: unknown repo: X` and the run carried on — the absence of a
    checklist looking exactly like a checklist (Factory#642). Nothing may be
    written for a repo whose automation impact was never declared.
    """
    proc = _signatures("--apply", "--repo", "NotARepo", tmp_path=tmp_path)
    assert proc.returncode != 0
    assert proc.gh_calls == ""  # type: ignore[attr-defined]
    assert "signer pre-flight:" not in proc.stdout


# --------------------------------------------------------------------------
# The strip guard (#691)
# --------------------------------------------------------------------------


def _assert_no_strip(live_contexts: list[str], payload: dict[str, object]) -> int:
    """Run the script's ``assert_no_strip`` with a stubbed ``gh``.

    Extracted and evaluated rather than invoked through ``--apply``: exercising
    it for real would rewrite live branch protection, which is precisely the
    operation under test.
    """
    script = _SCRIPT.read_text()
    start = script.index("assert_no_strip() {")
    end = script.index("\n}\n", start) + 3
    harness = (
        "set -uo pipefail\n"
        "OWNER=olafkfreund\n"
        f"LIVE={json.dumps(json.dumps(live_contexts))}\n"
        'gh() { jq -r ".[]" <<<"$LIVE"; }\n'
        + script[start:end]
        + f"\nassert_no_strip Repo dev {json.dumps(json.dumps(payload))}\n"
    )
    # S603/S607: same justification as _emit above -- fixed argv, no
    # shell=True, and the only interpolated values are json.dumps of literals
    # defined in this file. The subject under test is a shell function, so
    # running bash is the point.
    return subprocess.run(  # noqa: S603
        ["bash", "-c", harness],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,  # the non-zero exit IS the assertion
    ).returncode


@pytest.mark.parametrize(
    ("case", "live", "wanted", "expected_rc"),
    [
        # Unchanged: the ordinary re-apply, must not be obstructed.
        ("unchanged", ["a", "b"], ["a", "b"], 0),
        # Tightening must never be blocked, or the guard becomes the obstacle
        # it was added to prevent.
        ("adds a check", ["a", "b"], ["a", "b", "c"], 0),
        # The #691 direction: a stale table silently weakening a branch.
        ("drops one check", ["a", "b", "c"], ["a"], 1),
        # required_status_checks: null is how "no checks at all" is expressed.
        ("drops every check", ["a"], None, 1),
        # Nothing live means nothing to strip -- first-time setup must work.
        ("branch not protected yet", [], ["a"], 0),
    ],
)
def test_the_guard_blocks_only_removal(
    case: str, live: list[str], wanted: list[str] | None, expected_rc: int
) -> None:
    """One parametrised body rather than five near-identical ones.

    The five cases differ only in their data, and pasting the body per case is
    exactly what the clone budget exists to stop (Factory#415) -- the first
    version of this file did paste it, and the gate caught it.
    """
    payload: dict[str, object] = {
        "required_status_checks": None if wanted is None else {"contexts": wanted}
    }
    assert _assert_no_strip(live, payload) == expected_rc, case


def test_codeql_and_sinks_are_required_on_every_code_repo() -> None:
    """Factory#943 part 1, and the two ways it is easy to get wrong.

    A gate nobody is required to pass is a notification, not a gate. These four
    were advisory everywhere while being green everywhere: measured job-level
    outcomes over the last 12 commits of each default branch gave Factory 11/11,
    PFactory 14/14, TFactory 13/13, AIFactory 10/12 and CFactory 10/12, with
    every non-success a `cancelled` (concurrency superseding an in-flight run),
    never a `failure`.

    Two traps this pins:

    * **The matrix contexts, not a roll-up.** CodeQL reports one context per
      language. The `CodeQL` roll-up does not post on every PR, so requiring it
      leaves PRs waiting forever on a check that never arrives (Factory#529).
    * **AIFactory spells it lowercase.** Required contexts match
      case-sensitively, so `Analyze` and `analyze` are different checks and only
      one of them ever reports on a given repo.

    factory-gitops is excluded on purpose: it runs neither job, and a context
    required where no workflow produces it can never report.
    """
    for repo in ("Factory", "PFactory", "TFactory", "CFactory"):
        contexts = set(_declared_contexts(repo, _repo_table()[repo]["DEFAULT_BRANCH"]))
        assert set(_CODEQL) <= contexts, f"{repo} does not require the CodeQL contexts"
        assert _SINKS in contexts, f"{repo} does not require {_SINKS}"

    ai = set(_declared_contexts("AIFactory", "dev"))
    assert set(_CODEQL_AI) <= ai, "AIFactory must require the lowercase spelling"
    assert not (set(_CODEQL) & ai), (
        "AIFactory must NOT require the capitalised spelling -- its job is named "
        "`analyze`, so `Analyze (...)` would never report and would wedge the branch"
    )

    gitops = set(_declared_contexts("factory-gitops", "main"))
    assert not (set(_CODEQL) & gitops) and _SINKS not in gitops, (
        "factory-gitops runs neither job; requiring them there can never be satisfied"
    )


def test_trivy_is_not_required_anywhere() -> None:
    """#943 asks for Trivy too, and it is deliberately absent.

    Trivy posts no check-run on any repo: it runs on push/deploy, not on
    `pull_request`. Requiring a context nothing produces is the Factory#529
    wedge. This pins the omission so a future reader does not "finish the job"
    by adding it without first moving Trivy onto the PR trigger.
    """
    table = _repo_table()
    for repo in _all_repos():
        # Iterate the branches the script actually declares rather than
        # guessing main/dev and swallowing the miss -- a swallowed miss would
        # silently examine nothing and pass.
        for branch in table[repo]["BRANCHES"].split():
            contexts = _declared_contexts(repo, branch)
            assert not [c for c in contexts if "trivy" in c.lower()], (
                f"{repo}@{branch} requires a Trivy context, but Trivy does not run "
                "on pull_request in any repo, so it can never report"
            )
