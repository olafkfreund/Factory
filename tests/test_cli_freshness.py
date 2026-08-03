"""The agent-CLI freshness watchdog, checked offline (Factory#459).

The watchdog is scheduled and talks to npm, so the comparator would be untested
unless it is tested here — the same arrangement tests/test_pin_freshness.py and
tests/test_chart_vs_gitops.py use.

Everything here is synthetic and time is injected, so these assert the VERDICT
rather than the plumbing and do not change meaning as real releases ship.
"""

from __future__ import annotations

import sys
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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
