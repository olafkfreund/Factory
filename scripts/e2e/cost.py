"""Budget reservation, source reconciliation and confirmed remote stop."""

import math
import time
from collections.abc import Callable
from typing import Any

from scripts.e2e.config import CAMPAIGN_CAP_USD, CAMPAIGN_HOURS, MAX_LANES
from scripts.e2e.guard import Guard

STOP_TIMEOUT = 60
TERMINAL_STOPS = {"cancelled", "stopped"}


class StopUnconfirmedError(Exception):
    """The lane must block because the remote task may still be running."""


class Budget:
    def __init__(self, guard: Guard, cap_usd: float = CAMPAIGN_CAP_USD) -> None:
        if not math.isfinite(cap_usd) or cap_usd <= 0:
            raise ValueError("campaign cap must be finite and positive")
        self.guard = guard
        self.cap_usd = cap_usd
        self.started = time.monotonic()
        self.reserved = 0.0
        self.spent = 0.0
        self.allocations: dict[str, float] = {}
        self.lanes: set[str] = set()
        self.blocked: set[str] = set()

    def reserve(self, lane: str, amount: float) -> None:
        if (
            lane in self.blocked
            or time.monotonic() - self.started >= CAMPAIGN_HOURS * 3600
            or amount <= 0
            or self.spent + self.reserved + amount > self.cap_usd
            or (lane not in self.lanes and len(self.lanes) >= MAX_LANES)
        ):
            raise ValueError("campaign budget or lane limit reached")
        self.reserved += amount
        self.lanes.add(lane)
        self.allocations[lane] = self.allocations.get(lane, 0) + amount

    def release(self, lane: str, spent: float) -> None:
        if lane in self.blocked:
            return
        self.reserved -= self.allocations.pop(lane, 0)
        self.spent += spent
        self.lanes.discard(lane)

    def cap(  # noqa: PLR0913
        self,
        lane: str,
        task_id: str | tuple[str, str, str],
        stop: Callable[[str], object],
        status: Callable[[str], dict[str, Any]],
        *,
        timeout: float = STOP_TIMEOUT,
        now: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        service, kind, identity = (
            task_id if isinstance(task_id, tuple) else ("aifactory", "task", task_id)
        )

        def stop_once() -> object:
            try:
                return stop(identity)
            except RuntimeError as exc:
                # A finished task has nothing to stop; AIF's 404 hid the real timeout (#3882).
                if str(exc).endswith("HTTP 404") and status(identity).get("status") in TERMINAL_STOPS:
                    return None
                raise

        try:
            self.guard.mutate(service, kind, identity, stop_once)
            deadline = now() + timeout
            while True:
                if status(identity).get("status") in TERMINAL_STOPS:
                    return
                if now() >= deadline:
                    raise StopUnconfirmedError("remote stop unconfirmed; lane blocked")
                wait(min(1, max(0, deadline - now())))
        except Exception:
            self.blocked.add(lane)
            raise


def poll_usage(
    task_id: str,
    read: Callable[[str], dict[str, Any]],
    deadline: float,
    *,
    now: Callable[[], float] = time.monotonic,
    wait: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], list[str]]:
    """Poll AIF /api/tasks/{id}/token-usage until nonzero or deadline."""
    while True:
        usage = read(task_id)
        if usage.get("total_tokens", 0) > 0:
            return usage, []
        if now() >= deadline:
            return usage, ["missing usage"]
        wait(1)


def registry_costs(rows: list[dict[str, Any]], registered_ids: set[str]) -> float:
    return sum(
        float(row.get("cost_usd") or 0) for row in rows if row.get("task_id") in registered_ids
    )


def reconcile(
    stage_costs: list[float], journey_cost: float, source_costs: dict[str, float]
) -> list[str]:
    findings = []
    if abs(sum(stage_costs) - journey_cost) > max(journey_cost * 0.01, 0.01):
        findings.append("stage cost sum differs by over 1%")
    for name, amount in source_costs.items():
        if abs(amount - journey_cost) > max(journey_cost * 0.05, 0.01):
            findings.append(f"{name} cost drift exceeds 5%")
    return findings
