"""Result fields shared by CLI and MCP commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class CommandOutcome:
    exit_code: int
    outcome: Literal["ok", "rejected", "unknown"]
    payload: dict[str, Any]
    lines: tuple[str, ...]
