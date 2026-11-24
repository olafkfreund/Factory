"""Budget reservation, source reconciliation and confirmed remote stop."""

import time
from collections.abc import Callable

from scripts.e2e.config import CAMPAIGN_CAP_USD, CAMPAIGN_HOURS, MAX_LANES
from scripts.e2e.guard import Guard

STOP_RETRIES = 3


class StopUnconfirmedError(Exception):
    """The lane must block because the remote task may still be running."""


class Budget:
    def __init__(self, guard: Guard) -> None:
        self.guard = guard
        self.started = time.monotonic()
        self.reserved = 0.0
        self.lanes: set[str] = set()
        self.blocked: set[str] = set()

    def reserve(self, lane: str, amount: float) -> None:
        if (
            lane in self.blocked
            or time.monotonic() - self.started >= CAMPAIGN_HOURS * 3600
            or amount <= 0
            or self.reserved + amount > CAMPAIGN_CAP_USD
            or (lane not in self.lanes and len(self.lanes) >= MAX_LANES)
        ):
            raise ValueError("campaign budget or lane limit reached")
        self.reserved += amount
        self.lanes.add(lane)

    def cap(
        self,
        lane: str,
        task_id: str,
        stop: Callable[[str], object],
        status: Callable[[str], dict],
        *,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self.guard.mutate("task", task_id, lambda: stop(task_id))
        for attempt in range(STOP_RETRIES):
            if status(task_id).get("is_running") is False:
                return
            if attempt < STOP_RETRIES - 1:
                wait(1)
        self.blocked.add(lane)
        raise StopUnconfirmedError("remote stop unconfirmed; lane blocked")


def poll_usage(
    task_id: str,
    read: Callable[[str], dict],
    deadline: float,
    *,
    now: Callable[[], float] = time.monotonic,
    wait: Callable[[float], None] = time.sleep,
) -> tuple[dict, list[str]]:
    """Poll AIF /api/tasks/{id}/token-usage until nonzero or deadline."""
    while True:
        usage = read(task_id)
        if usage.get("total_tokens", 0) > 0:
            return usage, []
        if now() >= deadline:
            return usage, ["missing usage"]
        wait(1)


def registry_costs(rows: list[dict], registered_ids: set[str]) -> float:
    """Filter CFactory token and rollup rows before summing their costs."""
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
