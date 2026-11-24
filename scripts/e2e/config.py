"""Pinned campaign settings; environment and CLI endpoint overrides are ignored."""

import os
from dataclasses import dataclass
from pathlib import Path

from scripts.parr_regression import DEFAULTS

HOSTS = dict(DEFAULTS)
# Optional org pin (owner amendment 2026-11-24: existing keys, no dedicated org).
# Empty means each resource must keep the org it was onboarded with.
ORG = os.environ.get("E2E_ORG", "")
KEY_FILES = {service: Path.home() / f".{service}" / ".token" for service in HOSTS}
GITHUB_TOKEN_FILE = Path("/run/agenix/api-github-token")
CAMPAIGN_CAP_USD = 60
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
