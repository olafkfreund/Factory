"""Pinned campaign settings; environment and CLI endpoint overrides are ignored."""

import os
from dataclasses import dataclass
from pathlib import Path

from scripts.parr_regression import DEFAULTS

HOSTS = dict(DEFAULTS)
# Key-authenticated CFactory lives on its MCP host; the portal host sits behind SSO and
# answers API keys with a 302. Same host the factory CLI uses (factory_cli/config.py).
HOSTS["cfactory"] = "https://cfactory-mcp.freundcloud.org.uk"
# Optional org pin (owner amendment 2026-11-24: existing keys, no dedicated org).
# Empty means each resource must keep the org it was onboarded with.
ORG = os.environ.get("E2E_ORG", "")


def _key_file(service: str) -> Path:
    # A user-bound key (needed for PFactory live emit) wins over the legacy key.
    user_key = Path.home() / f".{service}" / ".e2e-token"
    return user_key if user_key.is_file() else Path.home() / f".{service}" / ".token"


KEY_FILES = {service: _key_file(service) for service in HOSTS}
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
