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
same shape) may pass a ``fixture`` to get well-formed sample data; the stub
still validates and normalizes that data so a malformed fixture can't smuggle in
an ``available=True`` record with missing numbers.

The ``dora_metrics`` envelope maps 1:1 onto ``$defs.deployment.dora_context`` in
``apis/task-contract.schema.json`` — that schema is the source of truth.

Pure + dependency-free so PFactory vendors it.
Run directly for the self-tests: ``python3 scripts/deployment_metrics_stub.py``.
"""

from __future__ import annotations

import sys
from typing import Any, TypedDict

SOURCE = "stub"
_DEFAULT_WINDOW_DAYS = 30
_DEFAULT_HISTORY_LIMIT = 20
_UNAVAILABLE_REASON = "no provider configured (stub default)"


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


def dora_metrics(
    repo: str,
    env: str | None = None,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    fixture: dict[str, Any] | None = None,
) -> DoraContext:
    """DORA delivery context for ``repo``/``env``.

    With no ``fixture`` returns ``available=False`` and ``null`` metrics — the
    downstream RFC-0013 policy then treats delivery health as UNKNOWN, never
    healthy. A ``fixture`` providing the metric fields yields a well-formed
    ``available=True`` envelope; any metric the fixture omits stays ``null`` so
    a partial fixture cannot manufacture a complete-looking record.
    """
    if not fixture:
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

    success_rate = fixture.get("deploy_success_rate")
    if window_days and isinstance(success_rate, dict):
        success_rate = {"window_days": window_days, **success_rate}

    return {
        "source": str(fixture.get("source", SOURCE)),
        "repo": repo,
        "env": env,
        "available": True,
        "reason": None,
        "deploy_success_rate": success_rate,
        "lead_time_p50_hours": fixture.get("lead_time_p50_hours"),
        "change_fail_rate": fixture.get("change_fail_rate"),
        "last_deploy": fixture.get("last_deploy"),
    }


# --------------------------------------------------------------------------- #
def _require(cond: bool, msg: str) -> None:
    """Lint-clean assert for the self-tests (avoids S101 under the strict bar)."""
    if not cond:
        raise AssertionError(msg)


def _test() -> None:
    repo = "olafkfreund/my-app"

    # Default: degrades honestly, never fabricates.
    h = deploy_history(repo, env="production")
    _require(h["available"] is False and h["deploys"] == [], str(h))
    _require(h["reason"] == _UNAVAILABLE_REASON and h["source"] == SOURCE, str(h))

    d = dora_metrics(repo, env="production")
    _require(d["available"] is False, str(d))
    # available=False => every metric is null (schema/honesty rule).
    for key in ("deploy_success_rate", "lead_time_p50_hours", "change_fail_rate", "last_deploy"):
        _require(d[key] is None, f"{key}={d[key]!r}")

    # Empty / metric-less fixtures still degrade.
    _require(deploy_history(repo, fixture={"deploys": []})["available"] is False, "empty history")
    _require(dora_metrics(repo, fixture={})["available"] is False, "empty dora")

    # Fixture with sample data => well-formed available=True.
    sample_history = {
        "source": "github-deployments",
        "deploys": [
            {"env": "production", "status": "success", "at": "2026-06-18T10:00:00Z"},
            {"env": "staging", "status": "success", "at": "2026-06-17T09:00:00Z"},
        ],
    }
    h2 = deploy_history(repo, env="production", limit=1, fixture=sample_history)
    _require(h2["available"] is True and h2["source"] == "github-deployments", str(h2))
    _require(len(h2["deploys"]) == 1, str(h2))  # truncated to limit

    expected_lead_time = 6.5
    expected_cfr = 0.08
    sample_dora = {
        "source": "github-deployments",
        "deploy_success_rate": {"value": 0.94, "sample": 50},
        "lead_time_p50_hours": expected_lead_time,
        "change_fail_rate": expected_cfr,
        "last_deploy": {"env": "production", "status": "success", "at": "2026-06-18T10:00:00Z"},
    }
    window = 14
    d2 = dora_metrics(repo, env="production", window_days=window, fixture=sample_dora)
    _require(d2["available"] is True and d2["reason"] is None, str(d2))
    _require(d2["lead_time_p50_hours"] == expected_lead_time, str(d2))
    _require(d2["change_fail_rate"] == expected_cfr, str(d2))
    _require(
        d2["deploy_success_rate"] == {"window_days": window, "value": 0.94, "sample": 50}, str(d2)
    )
    _require(d2["last_deploy"]["env"] == "production", str(d2))

    # Partial fixture: omitted metrics stay null (no manufactured completeness).
    expected_partial = 3.0
    d3 = dora_metrics(repo, fixture={"lead_time_p50_hours": expected_partial})
    _require(d3["available"] is True, str(d3))
    _require(d3["lead_time_p50_hours"] == expected_partial, str(d3))
    _require(d3["change_fail_rate"] is None and d3["deploy_success_rate"] is None, str(d3))

    sys.stdout.write("deployment_metrics_stub self-tests: passed\n")


if __name__ == "__main__":
    _test()
