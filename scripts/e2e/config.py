"""Pinned campaign settings; environment and CLI endpoint overrides are ignored."""

from dataclasses import dataclass

from scripts.parr_regression import DEFAULTS

HOSTS = dict(DEFAULTS)
ORG = "factory-e2e"
CAMPAIGN_CAP_USD = 450
MAX_LANES = 3
CAMPAIGN_HOURS = 8
SWEEP_AGE_DAYS = 7


@dataclass(frozen=True)
class Limit:
    usd: int
    minutes: int


LIMITS = {
    project: Limit(25 if project in {"P3", "P4"} else 15, 90 if project in {"P3", "P4"} else 60)
    for project in ("P1", "P2", "P3", "P4", "P5")
}
