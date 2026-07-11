#!/usr/bin/env python3
"""Unit tests for the real DORA computation (scripts/deployment_metrics_stub.py).

Factory#252 CODE-ONLY slice: de-stub the deployment-metrics / DORA computation.
``compute_dora_metrics`` is a pure function over raw deploy/incident event
records — no live provider, no cluster, no network. These tests lock its math
and its edge-case handling (empty input, single event, time-window bucketing,
malformed data) so that when a real provider is wired in later it computes
correctly from day one.

The module's own dependency-free self-test (``python3
scripts/deployment_metrics_stub.py``) already exercises the headline scenarios;
this file adds the exhaustive edge-case matrix pytest is better suited for.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import deployment_metrics_stub as dms  # noqa: E402  (path set above)

# --------------------------------------------------------------------------- #
# compute_dora_metrics — empty input
# --------------------------------------------------------------------------- #


def test_empty_input_has_zero_frequency_and_null_metrics() -> None:
    result = dms.compute_dora_metrics([], [])

    freq = result["deployment_frequency"]
    assert freq["total_deploys"] == 0
    assert freq["successful_deploys"] == 0
    assert freq["deploys_per_day"] == 0.0
    assert result["lead_time_p50_hours"] is None
    assert result["change_fail_rate"] is None
    assert result["time_to_restore_p50_hours"] is None
    assert result["sample"] == {
        "deploys": 0,
        "lead_time_observations": 0,
        "resolved_incidents": 0,
    }


def test_none_incidents_defaults_to_empty() -> None:
    # incidents=None (the default) must behave identically to incidents=[].
    with_none = dms.compute_dora_metrics(
        [{"at": "2026-01-01T00:00:00Z", "status": "success"}], now="2026-01-01T00:00:00Z"
    )
    with_empty = dms.compute_dora_metrics(
        [{"at": "2026-01-01T00:00:00Z", "status": "success"}], [], now="2026-01-01T00:00:00Z"
    )
    assert with_none == with_empty


# --------------------------------------------------------------------------- #
# compute_dora_metrics — single event
# --------------------------------------------------------------------------- #


def test_single_successful_deploy_with_lead_time() -> None:
    result = dms.compute_dora_metrics(
        [{"at": "2026-06-15T12:00:00Z", "status": "success", "lead_time_hours": 4.0}],
        now="2026-06-15T12:00:00Z",
        window_days=10,
    )

    freq = result["deployment_frequency"]
    assert freq["total_deploys"] == 1
    assert freq["successful_deploys"] == 1
    assert freq["deploys_per_day"] == pytest.approx(0.1)
    assert result["lead_time_p50_hours"] == 4.0
    assert result["change_fail_rate"] == 0.0
    assert result["time_to_restore_p50_hours"] is None  # no incidents at all


def test_single_failed_deploy_has_change_fail_rate_one() -> None:
    result = dms.compute_dora_metrics(
        [{"at": "2026-06-15T12:00:00Z", "status": "failure"}],
        now="2026-06-15T12:00:00Z",
    )
    assert result["change_fail_rate"] == 1.0
    assert result["deployment_frequency"]["successful_deploys"] == 0


def test_single_deploy_without_lead_time_leaves_lead_time_null() -> None:
    # Deploy still counts toward frequency/change-failure-rate, just not lead time.
    result = dms.compute_dora_metrics(
        [{"at": "2026-06-15T12:00:00Z", "status": "success"}], now="2026-06-15T12:00:00Z"
    )
    assert result["deployment_frequency"]["total_deploys"] == 1
    assert result["lead_time_p50_hours"] is None
    assert result["sample"]["lead_time_observations"] == 0


def test_single_resolved_incident_sets_time_to_restore() -> None:
    result = dms.compute_dora_metrics(
        [],
        [{"opened_at": "2026-06-01T00:00:00Z", "resolved_at": "2026-06-01T02:30:00Z"}],
        now="2026-06-01T02:30:00Z",
    )
    assert result["time_to_restore_p50_hours"] == 2.5
    assert result["sample"]["resolved_incidents"] == 1


# --------------------------------------------------------------------------- #
# compute_dora_metrics — time-window bucketing
# --------------------------------------------------------------------------- #


def test_window_excludes_events_before_the_window() -> None:
    result = dms.compute_dora_metrics(
        [
            {"at": "2026-05-01T00:00:00Z", "status": "success"},  # 40 days before `now`
            {"at": "2026-06-08T00:00:00Z", "status": "success"},  # inside
        ],
        now="2026-06-10T00:00:00Z",
        window_days=7,
    )
    assert result["deployment_frequency"]["total_deploys"] == 1


def test_window_boundaries_are_inclusive() -> None:
    # window_days=7 from now=2026-06-10 -> start is exactly 2026-06-03T00:00:00Z.
    result = dms.compute_dora_metrics(
        [
            {"at": "2026-06-03T00:00:00Z", "status": "success"},  # exactly at start
            {"at": "2026-06-10T00:00:00Z", "status": "success"},  # exactly at end (`now`)
        ],
        now="2026-06-10T00:00:00Z",
        window_days=7,
    )
    assert result["deployment_frequency"]["total_deploys"] == 2


def test_window_excludes_events_after_now() -> None:
    result = dms.compute_dora_metrics(
        [
            {"at": "2026-06-05T00:00:00Z", "status": "success"},
            {"at": "2026-06-20T00:00:00Z", "status": "success"},  # after `now`
        ],
        now="2026-06-10T00:00:00Z",
        window_days=30,
    )
    assert result["deployment_frequency"]["total_deploys"] == 1


def test_now_defaults_to_latest_event_timestamp_when_omitted() -> None:
    # No explicit `now` -> anchored at the latest valid timestamp across all
    # events, so the function is deterministic without relying on wall-clock.
    result = dms.compute_dora_metrics(
        [
            {"at": "2026-06-01T00:00:00Z", "status": "success"},
            {"at": "2026-06-05T00:00:00Z", "status": "success"},
        ],
        window_days=10,
    )
    assert result["window_end"] == "2026-06-05T00:00:00+00:00"
    assert result["deployment_frequency"]["total_deploys"] == 2


def test_window_days_is_clamped_to_at_least_one() -> None:
    # window_days=0 (or negative) must not raise (ZeroDivisionError) or silently
    # return an unbounded window; it is clamped to the minimum of 1 day.
    result = dms.compute_dora_metrics(
        [{"at": "2026-06-10T00:00:00Z", "status": "success"}],
        now="2026-06-10T00:00:00Z",
        window_days=0,
    )
    assert result["window_days"] == 1
    assert result["deployment_frequency"]["deploys_per_day"] == 1.0


# --------------------------------------------------------------------------- #
# compute_dora_metrics — change failure rate + lead time + MTTR math
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("statuses", "expected_rate"),
    [
        (["success", "success", "success"], 0.0),
        (["failure", "failure"], 1.0),
        (["success", "failure", "failure", "success"], 0.5),
        (["success", "rolled_back"], 0.5),
        (["success", "rollback", "error", "failed"], 0.75),
    ],
)
def test_change_fail_rate_math(statuses: list[str], expected_rate: float) -> None:
    deploys = [
        {"at": f"2026-06-{i + 1:02d}T00:00:00Z", "status": status}
        for i, status in enumerate(statuses)
    ]
    result = dms.compute_dora_metrics(deploys, now="2026-06-30T00:00:00Z", window_days=60)
    assert result["change_fail_rate"] == pytest.approx(expected_rate)


def test_deploy_with_missing_status_counts_as_success() -> None:
    result = dms.compute_dora_metrics([{"at": "2026-06-01T00:00:00Z"}], now="2026-06-01T00:00:00Z")
    assert result["change_fail_rate"] == 0.0


def test_lead_time_median_even_count() -> None:
    deploys = [
        {"at": "2026-06-01T00:00:00Z", "status": "success", "lead_time_hours": 2.0},
        {"at": "2026-06-02T00:00:00Z", "status": "success", "lead_time_hours": 6.0},
    ]
    result = dms.compute_dora_metrics(deploys, now="2026-06-02T00:00:00Z", window_days=30)
    assert result["lead_time_p50_hours"] == 4.0  # mean of the two middle values


def test_lead_time_ignores_deploys_missing_the_field() -> None:
    deploys = [
        {"at": "2026-06-01T00:00:00Z", "status": "success", "lead_time_hours": 10.0},
        {"at": "2026-06-02T00:00:00Z", "status": "success"},  # no lead_time_hours
    ]
    result = dms.compute_dora_metrics(deploys, now="2026-06-02T00:00:00Z", window_days=30)
    assert result["lead_time_p50_hours"] == 10.0
    assert result["sample"]["lead_time_observations"] == 1


def test_time_to_restore_ignores_unresolved_incidents() -> None:
    incidents = [
        {"opened_at": "2026-06-01T00:00:00Z", "resolved_at": "2026-06-01T01:00:00Z"},
        {"opened_at": "2026-06-02T00:00:00Z", "resolved_at": None},  # still open
        {"opened_at": "2026-06-03T00:00:00Z"},  # missing resolved_at entirely
    ]
    result = dms.compute_dora_metrics([], incidents, now="2026-06-03T00:00:00Z", window_days=30)
    assert result["time_to_restore_p50_hours"] == 1.0
    assert result["sample"]["resolved_incidents"] == 1


def test_time_to_restore_drops_incident_resolved_before_it_opened() -> None:
    # resolved_at earlier than opened_at is malformed data, not a fast fix.
    incidents = [{"opened_at": "2026-06-02T00:00:00Z", "resolved_at": "2026-06-01T00:00:00Z"}]
    result = dms.compute_dora_metrics([], incidents, now="2026-06-02T00:00:00Z", window_days=30)
    assert result["time_to_restore_p50_hours"] is None


# --------------------------------------------------------------------------- #
# compute_dora_metrics — malformed / defensive input
# --------------------------------------------------------------------------- #


def test_unparseable_deploy_timestamps_are_skipped_not_raised() -> None:
    deploys = [
        {"at": "not-a-timestamp", "status": "success"},
        {"status": "success"},  # missing `at` entirely
        {"at": None, "status": "success"},
        "not-even-a-dict",  # malformed event shape
        {"at": "2026-06-01T00:00:00Z", "status": "success"},
    ]
    result = dms.compute_dora_metrics(deploys, now="2026-06-01T00:00:00Z", window_days=30)  # type: ignore[arg-type]
    assert result["deployment_frequency"]["total_deploys"] == 1


def test_non_numeric_lead_time_hours_is_ignored() -> None:
    deploys = [
        {"at": "2026-06-01T00:00:00Z", "status": "success", "lead_time_hours": "fast"},
        {
            "at": "2026-06-02T00:00:00Z",
            "status": "success",
            "lead_time_hours": True,
        },  # bool, not a real number
    ]
    result = dms.compute_dora_metrics(deploys, now="2026-06-02T00:00:00Z", window_days=30)
    assert result["lead_time_p50_hours"] is None
    assert result["sample"]["lead_time_observations"] == 0


# --------------------------------------------------------------------------- #
# dora_metrics() — the MCP-facing envelope, now backed by real computation
# --------------------------------------------------------------------------- #


def test_dora_metrics_degrades_honestly_with_no_fixture() -> None:
    result = dms.dora_metrics("olafkfreund/my-app")
    assert result["available"] is False
    assert result["reason"] == dms._UNAVAILABLE_REASON
    assert result["deploy_success_rate"] is None
    assert result["lead_time_p50_hours"] is None
    assert result["change_fail_rate"] is None
    assert result["last_deploy"] is None


def test_dora_metrics_degrades_when_fixture_has_no_deploys() -> None:
    assert dms.dora_metrics("r", fixture={"incidents": []})["available"] is False
    assert dms.dora_metrics("r", fixture={"deploys": []})["available"] is False


def test_dora_metrics_computes_from_raw_fixture_events() -> None:
    fixture = {
        "source": "github-deployments",
        "deploys": [
            {"at": "2026-06-01T00:00:00Z", "status": "success", "lead_time_hours": 3.0},
            {"at": "2026-06-02T00:00:00Z", "status": "failure", "lead_time_hours": 5.0},
        ],
        "incidents": [
            {"opened_at": "2026-06-02T00:00:00Z", "resolved_at": "2026-06-02T02:00:00Z"},
        ],
    }
    result = dms.dora_metrics(
        "olafkfreund/my-app", env="production", window_days=30, fixture=fixture
    )

    assert result["available"] is True
    assert result["reason"] is None
    assert result["source"] == "github-deployments"
    assert result["change_fail_rate"] == 0.5
    assert result["lead_time_p50_hours"] == 4.0
    assert result["deploy_success_rate"] == {"value": 0.5, "window_days": 30, "sample": 2}
    assert result["last_deploy"] is not None
    assert result["last_deploy"]["status"] == "failure"  # the later of the two, by `at`


def test_dora_metrics_picks_the_true_latest_deploy_by_parsed_time_not_string_order() -> None:
    # String-sorting "...+02:00" vs "...Z" would pick the wrong one; a real
    # datetime comparison must be used.
    fixture = {
        "deploys": [
            {"at": "2026-06-01T23:00:00+02:00", "status": "success"},  # 21:00 UTC
            {"at": "2026-06-01T22:00:00Z", "status": "failure"},  # 22:00 UTC — actually later
        ],
    }
    result = dms.dora_metrics("r", fixture=fixture)
    assert result["last_deploy"]["status"] == "failure"


def test_dora_metrics_with_no_change_failures_has_no_deploy_success_rate_gap() -> None:
    fixture = {"deploys": [{"at": "2026-06-01T00:00:00Z", "status": "success"}]}
    result = dms.dora_metrics("r", fixture=fixture)
    assert result["deploy_success_rate"] == {
        "value": 1.0,
        "window_days": dms._DEFAULT_WINDOW_DAYS,
        "sample": 1,
    }
    assert result["change_fail_rate"] == 0.0


def test_deploy_history_is_unaffected_raw_listing_not_a_metric() -> None:
    # deploy_history() itself does no computation — it lists raw events. Confirms
    # the de-stub didn't change its (already-correct) behaviour.
    fixture = {
        "deploys": [
            {"env": "production", "status": "success", "at": "2026-06-18T10:00:00Z"},
            {"env": "staging", "status": "success", "at": "2026-06-17T09:00:00Z"},
        ]
    }
    result = dms.deploy_history("r", limit=1, fixture=fixture)
    assert result["available"] is True
    assert len(result["deploys"]) == 1
    assert result["deploys"][0]["env"] == "production"  # not reordered/recomputed


def test_module_self_test_still_passes() -> None:
    # Locks the module's own dependency-free self-test as a regression guard.
    dms._test()
