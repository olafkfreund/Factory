#!/usr/bin/env python3
"""RFC-0013 deployment-metrics MCP — dependency-free STUB provider.

Implements the two tools of the deployment-metrics MCP contract
(`apis/deployment-metrics.mcp.md`) so PFactory can populate the additive
`deployment` block of the Task Contract today, before a real provider
(GitHub Deployments / Argo CD / Datadog) exists:

  * ``deploy_history(repo, env=..., limit=...)`` — recent deploy events.
  * ``dora_metrics(repo, env=..., window_days=...)`` — DORA delivery context.

The defining property is **honesty**: the stub DEGRADES, it never FABRICATES.
With no fixture it returns a well-formed envelope with ``available=False`` and a
``reason`` (and ``null`` metrics) — it never invents a healthy-looking delivery
record. A caller (a test, a demo, or a future real backend transposed onto the
same shape) may pass a ``fixture`` to get well-formed sample data.

``compute_dora_metrics`` (Factory#252) is the real computation: it derives the
four DORA metrics — deployment frequency, lead time for changes, change
failure rate, time to restore — from raw deploy/incident event records, with
correct math and honest edge-case handling. ``dora_metrics`` runs a fixture's
raw events through it, so a well-formed fixture now yields a genuinely
*computed* envelope rather than an echo of caller-supplied numbers. This is
CODE-ONLY: no live provider is wired here — a real backend just needs to
supply the same raw event shape.

The ``dora_metrics`` envelope maps 1:1 onto ``$defs.deployment.dora_context`` in
``apis/task-contract.schema.json`` — that schema is the source of truth.

Pure + dependency-free so PFactory vendors it.
Run directly for the self-tests: ``python3 scripts/deployment_metrics_stub.py``.
"""

from __future__ import annotations

import statistics
import sys
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

SOURCE = "stub"
_DEFAULT_WINDOW_DAYS = 30
_DEFAULT_HISTORY_LIMIT = 20
_UNAVAILABLE_REASON = "no provider configured (stub default)"

# Deploy `status` values that count as a failed deploy for change-failure-rate.
# Anything else (including a missing status) counts as success — mirrors the
# DeployEvent contract, which leaves `status` a free-text field.
_FAILURE_STATUSES = frozenset({"failure", "failed", "error", "rolled_back", "rollback"})
_SECONDS_PER_HOUR = 3600.0


class DeployEvent(TypedDict, total=False):
    """One deploy event in a ``deploy_history`` response."""

    env: str
    status: str
    at: str
    ref: str
    url: str


class DeployHistory(TypedDict):
    """The ``deploy_history`` tool envelope."""

    source: str
    repo: str
    env: str | None
    available: bool
    reason: str | None
    deploys: list[DeployEvent]


class DoraContext(TypedDict):
    """The ``dora_metrics`` tool envelope (mirrors $defs.deployment.dora_context)."""

    source: str
    repo: str
    env: str | None
    available: bool
    reason: str | None
    deploy_success_rate: dict[str, Any] | None
    lead_time_p50_hours: float | None
    change_fail_rate: float | None
    last_deploy: dict[str, Any] | None


class DeploymentFrequency(TypedDict):
    """Deploy volume inside the metrics window."""

    deploys_per_day: float
    total_deploys: int
    successful_deploys: int


class DoraMetricsSample(TypedDict):
    """How many events actually contributed to each metric (not a metric itself)."""

    deploys: int
    lead_time_observations: int
    resolved_incidents: int


class DoraMetricsResult(TypedDict):
    """The four DORA metrics computed from raw deploy/incident event records."""

    window_days: int
    window_start: str
    window_end: str
    deployment_frequency: DeploymentFrequency
    lead_time_p50_hours: float | None
    change_fail_rate: float | None
    time_to_restore_p50_hours: float | None
    sample: DoraMetricsSample


def deploy_history(
    repo: str,
    env: str | None = None,
    limit: int = _DEFAULT_HISTORY_LIMIT,
    fixture: dict[str, Any] | None = None,
) -> DeployHistory:
    """Recent deploy events for ``repo``/``env``, newest first.

    With no ``fixture`` returns an honest ``available=False`` envelope (no
    backend wired). A ``fixture`` may supply ``deploys`` (a list of events);
    only then is ``available`` true and the list is truncated to ``limit``.
    """
    if not fixture or not fixture.get("deploys"):
        return {
            "source": SOURCE,
            "repo": repo,
            "env": env,
            "available": False,
            "reason": _UNAVAILABLE_REASON,
            "deploys": [],
        }

    deploys: list[DeployEvent] = list(fixture["deploys"])[:limit]
    return {
        "source": str(fixture.get("source", SOURCE)),
        "repo": repo,
        "env": env,
        "available": True,
        "reason": None,
        "deploys": deploys,
    }


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp defensively. Never raises; returns None on bad input."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _is_number(value: Any) -> bool:
    """True for int/float, excluding bool (bool is a subtype of int in Python)."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def compute_dora_metrics(
    deploys: list[dict[str, Any]],
    incidents: list[dict[str, Any]] | None = None,
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    now: str | None = None,
) -> DoraMetricsResult:
    """Compute the four DORA metrics from raw deploy/incident event records.

    Pure function: no I/O, no live provider, deterministic given its inputs.

    Args:
        deploys: Deploy events. Each MAY have ``at`` (ISO-8601 timestamp;
            required for the event to be counted at all), ``status``
            (anything in ``_FAILURE_STATUSES`` counts as failed, else
            success), and ``lead_time_hours`` (time from commit/merge to this
            deploy — optional; deploys without it still count toward
            frequency and change-failure-rate but not lead time).
        incidents: Incident events, each with ``opened_at`` and
            ``resolved_at`` (ISO-8601). An incident missing either, or with
            ``resolved_at`` before ``opened_at``, is dropped (unresolved or
            malformed — doesn't contribute to time-to-restore).
        window_days: Size of the trailing window in days (clamped to >= 1).
        now: ISO-8601 timestamp anchoring the window's end. Defaults to the
            latest valid timestamp seen across all events (deterministic and
            testable without wall-clock time); falls back to the current UTC
            time only when no event has a parseable timestamp.

    Returns:
        The four metrics plus the window bounds and sample sizes used to
        compute them. A metric is ``None`` — never a fabricated ``0`` — when
        there is no data to support it (honesty rule, matches the rest of
        this stub).

    Edge cases: empty input (frequency 0, other metrics None), a single event
    (metrics collapse to that event's own value), and time-window bucketing
    (events outside ``[now - window_days, now]`` are excluded from every
    metric, both boundaries inclusive).
    """
    window_days = max(1, window_days)
    incidents = incidents or []

    dated_deploys = [
        (event, ts)
        for event in deploys
        if isinstance(event, dict) and (ts := _parse_timestamp(event.get("at"))) is not None
    ]
    resolved_incidents = [
        (opened, resolved)
        for event in incidents
        if isinstance(event, dict)
        and (opened := _parse_timestamp(event.get("opened_at"))) is not None
        and (resolved := _parse_timestamp(event.get("resolved_at"))) is not None
        and resolved >= opened
    ]

    now_dt = _parse_timestamp(now) if now else None
    if now_dt is None:
        candidates = [ts for _, ts in dated_deploys] + [r for _, r in resolved_incidents]
        now_dt = max(candidates) if candidates else datetime.now(UTC)
    window_start = now_dt - timedelta(days=window_days)

    in_window_deploys = [(e, ts) for e, ts in dated_deploys if window_start <= ts <= now_dt]
    in_window_incidents = [
        (opened, resolved)
        for opened, resolved in resolved_incidents
        if window_start <= resolved <= now_dt
    ]

    total_deploys = len(in_window_deploys)
    failed_deploys = sum(
        1
        for event, _ in in_window_deploys
        if str(event.get("status", "success")).lower() in _FAILURE_STATUSES
    )

    lead_times = [
        float(event["lead_time_hours"])
        for event, _ in in_window_deploys
        if _is_number(event.get("lead_time_hours"))
    ]
    restore_hours = [
        (resolved - opened).total_seconds() / _SECONDS_PER_HOUR
        for opened, resolved in in_window_incidents
    ]

    return {
        "window_days": window_days,
        "window_start": window_start.isoformat(),
        "window_end": now_dt.isoformat(),
        "deployment_frequency": {
            "deploys_per_day": round(total_deploys / window_days, 4),
            "total_deploys": total_deploys,
            "successful_deploys": total_deploys - failed_deploys,
        },
        "lead_time_p50_hours": statistics.median(lead_times) if lead_times else None,
        "change_fail_rate": (failed_deploys / total_deploys) if total_deploys else None,
        "time_to_restore_p50_hours": (statistics.median(restore_hours) if restore_hours else None),
        "sample": {
            "deploys": total_deploys,
            "lead_time_observations": len(lead_times),
            "resolved_incidents": len(in_window_incidents),
        },
    }


def _most_recent_deploy(deploys: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The deploy with the latest parseable ``at``, or None if none parse."""
    dated = [
        (event, ts)
        for event in deploys
        if isinstance(event, dict) and (ts := _parse_timestamp(event.get("at"))) is not None
    ]
    return max(dated, key=lambda pair: pair[1])[0] if dated else None


def dora_metrics(
    repo: str,
    env: str | None = None,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    fixture: dict[str, Any] | None = None,
) -> DoraContext:
    """DORA delivery context for ``repo``/``env``.

    With no ``fixture`` (or one with no ``deploys``) returns ``available=False``
    and ``null`` metrics — the downstream RFC-0013 policy then treats delivery
    health as UNKNOWN, never healthy.

    A ``fixture`` with raw ``deploys`` (and optional ``incidents``) event
    records is run through ``compute_dora_metrics`` for a genuinely computed,
    ``available=True`` envelope — this no longer just echoes back
    caller-supplied numbers (Factory#252).
    """
    if not fixture or not fixture.get("deploys"):
        return {
            "source": SOURCE,
            "repo": repo,
            "env": env,
            "available": False,
            "reason": _UNAVAILABLE_REASON,
            "deploy_success_rate": None,
            "lead_time_p50_hours": None,
            "change_fail_rate": None,
            "last_deploy": None,
        }

    computed = compute_dora_metrics(
        fixture["deploys"], fixture.get("incidents"), window_days=window_days
    )
    change_fail_rate = computed["change_fail_rate"]
    deploy_success_rate = (
        {
            "value": round(1.0 - change_fail_rate, 4),
            "window_days": window_days,
            "sample": computed["deployment_frequency"]["total_deploys"],
        }
        if change_fail_rate is not None
        else None
    )

    return {
        "source": str(fixture.get("source", SOURCE)),
        "repo": repo,
        "env": env,
        "available": True,
        "reason": None,
        "deploy_success_rate": deploy_success_rate,
        "lead_time_p50_hours": computed["lead_time_p50_hours"],
        "change_fail_rate": change_fail_rate,
        "last_deploy": _most_recent_deploy(fixture["deploys"]),
    }


# --------------------------------------------------------------------------- #
def _require(cond: bool, msg: str) -> None:
    """Lint-clean assert for the self-tests (avoids S101 under the strict bar)."""
    if not cond:
        raise AssertionError(msg)


def _test_stub_envelopes() -> None:
    """The honesty contract: no fixture (or an empty one) => available=False, null metrics."""
    repo = "olafkfreund/my-app"

    # Default: degrades honestly, never fabricates.
    h = deploy_history(repo, env="production")
    _require(h["available"] is False and h["deploys"] == [], str(h))
    _require(h["reason"] == _UNAVAILABLE_REASON and h["source"] == SOURCE, str(h))

    d = dora_metrics(repo, env="production")
    _require(d["available"] is False, str(d))
    # available=False => every metric is null (schema/honesty rule).
    _require(d["deploy_success_rate"] is None, str(d))
    _require(d["lead_time_p50_hours"] is None, str(d))
    _require(d["change_fail_rate"] is None, str(d))
    _require(d["last_deploy"] is None, str(d))

    # Empty / event-less fixtures still degrade.
    _require(deploy_history(repo, fixture={"deploys": []})["available"] is False, "empty history")
    _require(dora_metrics(repo, fixture={})["available"] is False, "empty dora")
    _require(dora_metrics(repo, fixture={"deploys": []})["available"] is False, "empty deploys")


def _test_compute_dora_metrics() -> None:
    """Real DORA computation (Factory#252): correct math + empty/single/window edge cases."""
    repo = "olafkfreund/my-app"

    # compute_dora_metrics: empty input -> zero frequency, every rate/median None.
    zero_deploys = 0
    empty = compute_dora_metrics([], [])
    _require(empty["deployment_frequency"]["total_deploys"] == zero_deploys, str(empty))
    _require(empty["deployment_frequency"]["deploys_per_day"] == 0.0, str(empty))
    _require(empty["lead_time_p50_hours"] is None, str(empty))
    _require(empty["change_fail_rate"] is None, str(empty))
    _require(empty["time_to_restore_p50_hours"] is None, str(empty))

    # compute_dora_metrics: single successful deploy with a lead time.
    one_deploy = 1
    expected_frequency = 0.1  # 1 deploy / 10-day window
    expected_lead_time = 4.0
    single = compute_dora_metrics(
        [
            {
                "at": "2026-06-15T12:00:00Z",
                "status": "success",
                "lead_time_hours": expected_lead_time,
            }
        ],
        now="2026-06-15T12:00:00Z",
        window_days=10,
    )
    _require(single["deployment_frequency"]["total_deploys"] == one_deploy, str(single))
    _require(single["deployment_frequency"]["deploys_per_day"] == expected_frequency, str(single))
    _require(single["lead_time_p50_hours"] == expected_lead_time, str(single))
    _require(single["change_fail_rate"] == 0.0, str(single))
    _require(single["time_to_restore_p50_hours"] is None, str(single))

    # compute_dora_metrics: time-window bucketing excludes events outside the
    # window, on both ends. Deploy A is well before window start (excluded), B
    # is inside, C is exactly at window end (inclusive).
    in_window_deploys = 2
    half = 0.5
    windowed = compute_dora_metrics(
        [
            {"at": "2026-06-01T00:00:00Z", "status": "success"},  # excluded (too old)
            {"at": "2026-06-05T00:00:00Z", "status": "failure"},  # in window
            {"at": "2026-06-10T00:00:00Z", "status": "success"},  # in window (boundary)
        ],
        now="2026-06-10T00:00:00Z",
        window_days=7,
    )
    _require(windowed["deployment_frequency"]["total_deploys"] == in_window_deploys, str(windowed))
    _require(windowed["change_fail_rate"] == half, str(windowed))

    # compute_dora_metrics: deployment frequency, lead time, change failure
    # rate and time-to-restore together, from a realistic mixed history.
    four_deploys, two_successes, two_incidents = 4, 2, 2
    expected_median_lead_time = 4.0  # median of [2.0, 8.0, 4.0]
    expected_mttr_hours = 1.75  # median of [2h, 1.5h]
    full = compute_dora_metrics(
        deploys=[
            {"at": "2026-06-01T00:00:00Z", "status": "success", "lead_time_hours": 2.0},
            {"at": "2026-06-02T00:00:00Z", "status": "failure", "lead_time_hours": 8.0},
            {"at": "2026-06-03T00:00:00Z", "status": "rolled_back"},
            {"at": "2026-06-04T00:00:00Z", "status": "success", "lead_time_hours": 4.0},
        ],
        incidents=[
            {"opened_at": "2026-06-02T01:00:00Z", "resolved_at": "2026-06-02T03:00:00Z"},
            {"opened_at": "2026-06-03T05:00:00Z", "resolved_at": None},  # unresolved: dropped
            {"opened_at": "2026-06-03T10:00:00Z", "resolved_at": "2026-06-03T11:30:00Z"},
        ],
        now="2026-06-04T00:00:00Z",
        window_days=30,
    )
    _require(full["deployment_frequency"]["total_deploys"] == four_deploys, str(full))
    _require(full["deployment_frequency"]["successful_deploys"] == two_successes, str(full))
    _require(full["change_fail_rate"] == half, str(full))
    _require(full["lead_time_p50_hours"] == expected_median_lead_time, str(full))
    _require(full["time_to_restore_p50_hours"] == expected_mttr_hours, str(full))
    _require(full["sample"]["resolved_incidents"] == two_incidents, str(full))

    # dora_metrics: fixture of raw events -> genuinely computed envelope, not
    # an echo of caller-supplied numbers.
    computed_fixture = {
        "source": "github-deployments",
        "deploys": [
            {"at": "2026-06-01T00:00:00Z", "status": "success", "lead_time_hours": 3.0},
            {"at": "2026-06-02T00:00:00Z", "status": "failure", "lead_time_hours": 5.0},
        ],
        "incidents": [
            {"opened_at": "2026-06-02T00:00:00Z", "resolved_at": "2026-06-02T02:00:00Z"},
        ],
    }
    d2 = dora_metrics(repo, env="production", window_days=30, fixture=computed_fixture)
    two_deploys = 2
    _require(d2["available"] is True and d2["reason"] is None, str(d2))
    _require(d2["source"] == "github-deployments", str(d2))
    _require(d2["change_fail_rate"] == half, str(d2))
    _require(d2["lead_time_p50_hours"] == expected_median_lead_time, str(d2))
    expected_success_rate = {"value": half, "window_days": 30, "sample": two_deploys}
    _require(d2["deploy_success_rate"] == expected_success_rate, str(d2))
    last_deploy = d2["last_deploy"]
    _require(last_deploy is not None and last_deploy["status"] == "failure", str(d2))


def _test() -> None:
    _test_stub_envelopes()
    _test_compute_dora_metrics()
    sys.stdout.write("deployment_metrics_stub self-tests: passed\n")


if __name__ == "__main__":
    _test()
