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


def _normalise(payload: dict) -> dict:
    out = subprocess.run(  # noqa: S603
        ["bash", str(_SCRIPT), "--normalise-stdin"],  # noqa: S607
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


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
    """dev carries the same CI checks as main but no review requirement.

    This is the decision Factory#468 exists to stop a script from silently
    reverting: a solo maintainer (and the factory's own agents) have nobody to
    approve their PRs, so a review requirement on the integration branch stalls
    every merge, and `strict` forces a rebase before each one.
    """
    main, dev = _emit(repo, "main"), _emit(repo, "dev")

    assert main["required_pull_request_reviews"] is not None
    assert main["required_pull_request_reviews"]["required_approving_review_count"] == 1
    assert main["required_status_checks"]["strict"] is True
    assert main["required_conversation_resolution"] is True

    assert dev["required_pull_request_reviews"] is None
    assert dev["required_status_checks"]["strict"] is False
    assert dev["required_conversation_resolution"] is False

    # Same gate set on both: dev is looser about review, never about CI.
    assert dev["required_status_checks"]["contexts"] == main["required_status_checks"]["contexts"]


def test_check_contexts_are_per_repo() -> None:
    """CFactory's CI jobs are named differently from the Python services'.

    The bug in Factory#468 was one repo's check names hardcoded into a script
    vendored to repos whose jobs are named differently. Lock the distinction.
    """
    assert _emit("CFactory", "main")["required_status_checks"]["contexts"] == [
        "Backend pytest",
        "Frontend typecheck + build",
    ]
    assert _emit("TFactory", "main")["required_status_checks"]["contexts"] == [
        "backend (ruff + pytest)",
        "critical (fast PR gate)",
    ]
    # AIFactory has no required frontend check, despite having a frontend suite.
    assert _emit("AIFactory", "main")["required_status_checks"]["contexts"] == [
        "backend (ruff + pytest)",
    ]


def test_gitops_requires_no_review_and_no_checks() -> None:
    # Bot-driven CD: a review requirement would rest entirely on the admin bypass.
    intent = _emit("factory-gitops", "main")
    assert intent["required_pull_request_reviews"] is None
    assert intent["required_status_checks"] is None
    assert intent["allow_force_pushes"] is False
    assert intent["allow_deletions"] is False


# --- the comparator, both directions (rule 4.9) ------------------------------


def test_matching_live_response_compares_equal() -> None:
    """A live response that matches intent must normalise to the same JSON.

    If this fails the gate is always-red. Uses the API's own wire shape, so a
    normaliser that only understands the intent shape is caught here.
    """
    for repo, branch, contexts, strict, reviews, convres in [
        ("TFactory", "main", ["backend (ruff + pytest)", "critical (fast PR gate)"], True, 1, True),
        (
            "TFactory",
            "dev",
            ["backend (ruff + pytest)", "critical (fast PR gate)"],
            False,
            None,
            False,
        ),
        ("CFactory", "main", ["Backend pytest", "Frontend typecheck + build"], True, 1, True),
        ("AIFactory", "dev", ["backend (ruff + pytest)"], False, None, False),
    ]:
        code_owner = repo in {"PFactory", "TFactory", "AIFactory"} and reviews is not None
        live = _live_shaped(
            contexts=contexts,
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
        contexts=["backend (ruff + pytest)"],
        strict=False,
        reviews=None,
        conversation_resolution=False,
    )
    del live["required_status_checks"]["contexts"]
    assert _normalise(live) == _emit("AIFactory", "dev")


def test_unordered_contexts_compare_equal() -> None:
    # GitHub does not promise an order; a spurious diff would train people to
    # ignore the gate.
    live = _live_shaped(
        contexts=["critical (fast PR gate)", "backend (ruff + pytest)"],
        strict=False,
        reviews=None,
        conversation_resolution=False,
    )
    assert _normalise(live) == _emit("TFactory", "dev")


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda d: d["required_status_checks"].update(strict=True),
            id="strict-flipped-on-dev",
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
        contexts=["backend (ruff + pytest)", "critical (fast PR gate)"],
        strict=False,
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
