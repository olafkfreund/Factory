"""The agent-CLI freshness watchdog, checked offline (Factory#459).

The watchdog is scheduled and talks to npm, so the comparator would be untested
unless it is tested here — the same arrangement tests/test_pin_freshness.py and
tests/test_chart_vs_gitops.py use.

Everything here is synthetic and time is injected, so these assert the VERDICT
rather than the plumbing and do not change meaning as real releases ship.
"""

from __future__ import annotations

import base64
import sys
import urllib.error
from datetime import UTC, datetime

# scripts/ is put on sys.path by tests/conftest.py.
import check_cli_freshness as cf
import pytest

_NOW = datetime(2026, 8, 3, tzinfo=UTC)
_PIN = cf.Pin("AIFactory", "@openai/codex", "0.144.6")


def _doc(latest: str, published: str | None) -> dict[str, object]:
    return {"dist-tags": {"latest": latest}, "time": ({latest: published} if published else {})}


def test_builtin_self_test_passes() -> None:
    assert cf.main(["--self-test"]) == 0


def test_a_pin_equal_to_latest_is_current_however_old() -> None:
    """Age is measured on the LATEST release, not the pinned one.

    A package that simply has not moved for a year is not stale, and treating it
    as stale would make the watchdog noisy about something nobody can act on.
    """
    _, failure = cf.assess(_PIN, _doc("0.144.6", "2025-01-01T00:00:00Z"), now=_NOW, max_age_days=30)
    assert failure is None


def test_a_long_ignored_release_alerts() -> None:
    """THE ASSERTION WITH TEETH — the gap Factory#459 is about.

    Nothing proposes these bumps: the Renovate App is not installed, and
    Dependabot's docker ecosystem parses only FROM lines so it cannot see an
    `npm install -g @pkg@version` bake step. Without this, "no bump PRs" and
    "nothing to update" are indistinguishable — which is how Factory#436 sat
    unnoticed for nine weeks.
    """
    line, failure = cf.assess(
        _PIN, _doc("0.146.0", "2026-05-01T00:00:00Z"), now=_NOW, max_age_days=30
    )
    assert failure is not None
    assert "0.146.0" in failure, "the failure must name what to bump to"
    assert "0.146.0" in line, "the report must name it too, not just a verdict"


def test_a_recent_release_is_within_the_window() -> None:
    """Not red-by-construction: these CLIs ship every few days.

    A window tight enough to fire on every release is a gate that means nothing
    within a week (Factory#538).
    """
    _, failure = cf.assess(_PIN, _doc("0.146.0", "2026-07-29T00:00:00Z"), now=_NOW, max_age_days=30)
    assert failure is None


def test_the_window_is_the_only_thing_excusing_it() -> None:
    """Mutation guard on the budget itself: at zero, the same input fails.

    Without this, a window accidentally set to infinity would pass every other
    case in this file.
    """
    _, failure = cf.assess(_PIN, _doc("0.146.0", "2026-07-29T00:00:00Z"), now=_NOW, max_age_days=0)
    assert failure is not None


def test_an_unmeasurable_age_is_reported_not_skipped() -> None:
    """A newer version with no publish date is still a newer version.

    Skipping it would turn a registry quirk into a silent pass, which is the
    Factory#500 shape.
    """
    _, failure = cf.assess(_PIN, _doc("0.146.0", None), now=_NOW, max_age_days=30)
    assert failure is not None


def test_a_registry_entry_with_no_latest_is_unreadable_input() -> None:
    with pytest.raises(cf.SourceUnavailableError):
        cf.assess(_PIN, {"dist-tags": {}}, now=_NOW, max_age_days=30)


def test_only_the_tracked_clis_are_parsed() -> None:
    """Build tooling pinned in the same bake step is deliberately ignored.

    Its version is frozen on purpose; reporting it would be the noise that gets
    a real alert muted.
    """
    dockerfile = (
        "RUN npm install -g \\\n"
        "        @anthropic-ai/claude-code@2.1.215 \\\n"
        "        @some/build-tool@1.0.0\n"
    )
    pins = cf.parse_pins("AIFactory", dockerfile)
    assert [p.package for p in pins] == ["@anthropic-ai/claude-code"]


def test_scope_cannot_shrink_unnoticed() -> None:
    """Silent scope loss (gate-honesty §3): both registries are enumerated.

    Dropping a package or a repo narrows the watchdog while every remaining case
    still passes.
    """
    assert set(cf.TRACKED) == {
        "@anthropic-ai/claude-code",
        "@openai/codex",
        "@google/gemini-cli",
    }
    assert set(cf.REPOS) == {"AIFactory", "PFactory", "TFactory"}
    assert "CFactory" not in cf.REPOS, "the cockpit runs no agent and pins none of these"


_BAKE = (
    "RUN npm install -g \\\n"
    "        @anthropic-ai/claude-code@2.1.215 \\\n"
    "        @openai/codex@0.144.6 \\\n"
    "        @google/gemini-cli@0.51.0\n"
    "RUN npm install -g @some/build-tool@1.0.0\n"
)
_PINNED = {
    "@anthropic-ai/claude-code": "2.1.215",
    "@openai/codex": "0.144.6",
    "@google/gemini-cli": "0.51.0",
}


def test_the_rewriter_moves_only_what_it_was_asked_to() -> None:
    out = cf.rewrite(_BAKE, {"@openai/codex": "0.147.0"})
    assert "@openai/codex@0.147.0" in out
    assert "@anthropic-ai/claude-code@2.1.215" in out, "a tracked pin not named is left alone"
    assert "@some/build-tool@1.0.0" in out, "an untracked package is never rewritten"
    assert len(cf.parse_pins("AIFactory", out)) == len(cf.TRACKED), "the result still parses"


def test_a_rewrite_that_matches_nothing_raises() -> None:
    """THE ASSERTION WITH TEETH on the bump half, and the defect this issue names.

    factory-gitops' renovate.json customManager is still valid and still "runs";
    it has matched nothing since TFactory#791 moved the pins out of the manifests
    it scans, and reports success having found no dependencies. A bumper that
    edits a file it cannot actually see must be loud, not quietly successful.
    """
    with pytest.raises(cf.SourceUnavailableError):
        cf.rewrite("RUN npm install -g claude-code\n", {"@openai/codex": "0.147.0"})


def test_nothing_to_bump_is_a_no_op_not_an_error() -> None:
    assert cf.rewrite(_BAKE, {}) == _BAKE


def test_no_branch_to_retract_is_the_steady_state_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: GitHub answers a delete of a missing ref with 422, not 404.

    Once the pins are current this is what EVERY weekly run does, so treating it
    as an error turns the healthy case red every week -- the cry-wolf shape that
    gets a job muted, on the most common path there is. Caught live, not here,
    which is why it is pinned here.
    """
    calls: list[str] = []

    def fake_api(method: str, path: str, _token: str, _body: object = None) -> object:
        calls.append(f"{method} {path}")
        if method == "DELETE":
            raise urllib.error.HTTPError(path, 422, "Unprocessable Entity", {}, None)  # type: ignore[arg-type]
        if path.endswith("/contents/Dockerfile?ref=dev"):
            return {"content": base64.b64encode(_BAKE.encode()).decode(), "sha": "deadbeef"}
        return {"default_branch": "dev"}

    monkeypatch.setattr(cf, "_api", fake_api)
    registry = {pkg: {"dist-tags": {"latest": ver}} for pkg, ver in _PINNED.items()}
    line = cf.propose_bump("PFactory", registry, "token")

    assert "nothing proposed" in line
    assert not any(c.startswith("POST") or c.startswith("PUT") for c in calls), (
        "a run with nothing to bump must not write anything"
    )


def _bump_api(pr_state: str = "open") -> tuple[list[tuple[str, str, object]], object]:
    """A fake GitHub for the bump path. Returns (recorded calls, the fake)."""
    calls: list[tuple[str, str, object]] = []

    def fake_api(method: str, path: str, _token: str, body: object = None) -> object:
        calls.append((method, path, body))
        routes: list[tuple[bool, object]] = [
            (
                path.endswith("/contents/Dockerfile?ref=dev"),
                {"content": base64.b64encode(_BAKE.encode()).decode(), "sha": "filesha"},
            ),
            ("/git/ref/heads/dev" in path, {"object": {"sha": "BASEHEAD"}}),
            ("/git/commits/BASEHEAD" in path, {"tree": {"sha": "basetree"}}),
            (method == "POST" and path.endswith("/git/trees"), {"sha": "newtree"}),
            (method == "POST" and path.endswith("/git/commits"), {"sha": "NEWCOMMIT"}),
            ("/pulls?" in path, []),
            ("/pulls" in path, {"state": pr_state, "html_url": "https://example.invalid/pr/1"}),
        ]
        return next((value for matched, value in routes if matched), {"default_branch": "dev"})

    return calls, fake_api


def test_the_branch_never_points_at_the_bare_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression, and the bug that made "refreshed in place" a false claim.

    Forcing the branch back to base and then writing the file onto it leaves the
    branch byte-identical to base in between, so the PR momentarily has zero
    commits -- and GitHub CLOSES a PR whose commits all disappear. Measured on
    real PRs: AIFactory#1198 and TFactory#978 were closed by the refresh that was
    supposed to update them. The next run then opens a NEW PR every week, which is
    precisely the churn one fixed branch exists to prevent.

    So no ref write may ever carry the base head.
    """
    calls, fake = _bump_api()
    monkeypatch.setattr(cf, "_api", fake)
    registry = {pkg: {"dist-tags": {"latest": "9.9.9"}} for pkg in cf.TRACKED}
    cf.propose_bump("PFactory", registry, "token")

    ref_writes = [
        (m, p, b) for m, p, b in calls if "/git/ref" in p and m in {"PATCH", "POST", "PUT"}
    ]
    assert ref_writes, "the branch must actually be written"
    for _, path, body in ref_writes:
        assert isinstance(body, dict)
        assert body.get("sha") != "BASEHEAD", (
            f"{path} points the bump branch at the bare base commit, which empties "
            "the PR and makes GitHub close it"
        )


def test_a_pr_that_is_not_open_is_not_a_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling the endpoint is not the same as having an open pull request.

    Without this post-condition the bumper reports success over a closed PR --
    an automation nobody merges, by construction.
    """
    _, fake = _bump_api(pr_state="closed")
    monkeypatch.setattr(cf, "_api", fake)
    registry = {pkg: {"dist-tags": {"latest": "9.9.9"}} for pkg in cf.TRACKED}
    with pytest.raises(cf.SourceUnavailableError, match="not open"):
        cf.propose_bump("PFactory", registry, "token")


# --------------------------------------------------------------------------- #
# A pin AHEAD of the registry (Factory#615)                                     #
# --------------------------------------------------------------------------- #


_AHEAD = cf.Pin("AIFactory", "@openai/codex", "0.147.0")


def test_a_pin_ahead_of_the_registry_alerts() -> None:
    """THE ASSERTION WITH TEETH for #615, and the case the docstring got wrong.

    `assess` treated any `latest != pin.version` as behind without comparing
    them, and the exit-code docs promised "0 - every pin is within the window (or
    ahead of the registry)". Both cannot be right, and neither was: it exited 1
    describing an ahead pin as behind.

    A pin ahead of latest is not a hypothetical. It is what an upstream YANK
    looks like from here -- the event factory-gitops' cli-canary exists to catch
    -- so the contract and the behaviour now agree ON ALERTING. "The version we
    deploy is no longer the one npm serves" is not a passing state.
    """
    _, failure = cf.assess(
        _AHEAD, _doc("0.146.0", "2026-01-01T00:00:00Z"), now=_NOW, max_age_days=30
    )
    assert failure is not None


def test_an_ahead_pin_is_not_described_as_behind() -> None:
    """The old output, verbatim:

        AIFactory/@openai/codex 0.147.0 - behind 0.146.0, published 218d ago

    The pin is ahead, and "218 days" was the age of an OLDER release presented as
    evidence of neglect. A reader sent looking for a missed bump is looking for
    the wrong thing entirely.
    """
    line, failure = cf.assess(
        _AHEAD, _doc("0.146.0", "2026-01-01T00:00:00Z"), now=_NOW, max_age_days=30
    )
    assert "AHEAD" in line
    assert "behind" not in line
    assert failure is not None
    assert "yanked" in failure, "the failure names the actual suspicion"
    assert "days" not in failure, "no staleness clock on a release we are already past"


def test_ordering_is_numeric_not_lexicographic() -> None:
    """0.9.0 vs 0.10.0 is where a string compare silently inverts the verdict."""
    _, failure = cf.assess(
        cf.Pin("AIFactory", "@openai/codex", "0.9.0"),
        _doc("0.10.0", "2026-07-29T00:00:00Z"),
        now=_NOW,
        max_age_days=30,
    )
    assert failure is None, "0.9.0 is BEHIND 0.10.0, and within the window"
    line, _ = cf.assess(
        cf.Pin("AIFactory", "@openai/codex", "0.10.0"),
        _doc("0.9.0", "2026-07-29T00:00:00Z"),
        now=_NOW,
        max_age_days=30,
    )
    assert "AHEAD" in line


# --------------------------------------------------------------------------- #
# The ref the verdict is about (Factory#612)                                    #
# --------------------------------------------------------------------------- #


def _stub_refs(
    monkeypatch: pytest.MonkeyPatch, *, on_main: dict[str, str], on_default: dict[str, str]
) -> None:
    """Serve a different Dockerfile per ref, and a registry that is current."""

    def fake_dockerfile(_repo: str, ref: str = cf._DEPLOYED_REF, **_kw: object) -> str:
        pins = on_main if ref == "main" else on_default
        return "RUN npm install -g " + " ".join(f"{p}@{v}" for p, v in pins.items()) + "\n"

    def fake_registry(package: str, **_kw: object) -> dict[str, object]:
        # latest is what the default branch has -- i.e. the bump was correct.
        return _doc(on_default[package], "2020-01-01T00:00:00Z")

    monkeypatch.setattr(cf, "fetch_dockerfile", fake_dockerfile)
    monkeypatch.setattr(cf, "fetch_registry", fake_registry)


_BUMPED_ON_DEV = {**_PINNED, "@openai/codex": "0.146.0"}


def test_a_bump_merged_to_dev_does_not_silence_the_alarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE ASSERTION WITH TEETH for #612.

    The watchdog read `HEAD`, which raw.githubusercontent resolves to the DEFAULT
    branch -- `dev` in all three repos, and `dev` is not deployed. AIFactory ships
    via release/X.Y.Z -> main and deploy.yml fires on push-to-main, so a bump
    merged to dev turned this job green while the image the fleet runs still
    baked the old CLI.

    An alarm that goes quiet before the fix reaches the cluster is worse than no
    alarm: "the watchdog is green" and "the deployed pin is current" stop being
    the same statement and nothing says so.
    """
    _stub_refs(monkeypatch, on_main=_PINNED, on_default=_BUMPED_ON_DEV)
    assert cf.main([]) == 1, "main still bakes 0.144.6, so the fleet is still behind"


def test_the_report_names_the_bump_that_has_not_shipped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The second fact. Red alone would not say the fix is already written."""
    _stub_refs(monkeypatch, on_main=_PINNED, on_default=_BUMPED_ON_DEV)
    cf.main([])
    out = capsys.readouterr().out
    assert "the default branch has 0.146.0" in out
    assert "main still has 0.144.6" in out


def test_refs_that_agree_produce_no_second_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Control: the extra line must appear only when the refs disagree.

    A note on every pin every week is the noise that gets a report skimmed, and
    it would make the test above pass for the wrong reason.
    """
    _stub_refs(monkeypatch, on_main=_BUMPED_ON_DEV, on_default=_BUMPED_ON_DEV)
    cf.main([])
    assert "the default branch has" not in capsys.readouterr().out


def test_the_deployed_ref_is_the_one_that_deploys() -> None:
    """Named, so narrowing it back to the default branch is a visible diff.

    factory-gitops' cli-canary reads `main` with the comment "each one's
    deploy.yml triggers on push-to-main, so main is the ref whose pins actually
    reach the cluster". That reasoning was always right; this watchdog now
    follows it.
    """
    assert cf._DEPLOYED_REF == "main"
    assert cf._PROPOSED_REF == "HEAD", "the default branch, resolved without an API call"


def test_one_branch_per_repo_so_a_sitting_pr_is_never_duplicated() -> None:
    """An automation whose PRs pile up unmerged trains people to ignore it.

    A single fixed branch is what makes the weekly run refresh the open PR in
    place instead of opening a second one, so this name is load-bearing.
    """
    assert cf._BUMP_BRANCH == "chore/agent-cli-pins"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
