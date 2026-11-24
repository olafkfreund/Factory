"""Injected stdio transport for factory mcp actions."""

import re
from collections.abc import Callable

from scripts.e2e.guard import Guard, GuardRefusalError

ID_SHAPED = re.compile(r"(?:\b(?:af|pf|tf):\S+|\b(?:task|card)-[\w-]+|\b[A-Z]+-\d+\b)")


class MCP:
    def __init__(self, guard: Guard, request: Callable[[str, dict], dict]) -> None:
        self.guard = guard
        self.request = request

    def call(self, service: str, kind: str, identity: str, method: str, **params: object) -> dict:
        if any(ID_SHAPED.search(str(value)) for value in params.values()) or any(
            key in params
            for key in ("id", "key", "task_id", "card_key", "project_id", "session_id", "spec_id")
        ):
            raise GuardRefusalError("caller supplied another target")
        target_field = "key" if kind == "card" else "id"
        if target_field in params:
            raise GuardRefusalError("caller supplied mutation target")

        def action() -> dict:
            response = self.request(method, {**params, target_field: identity})
            if response.get("error"):
                raise RuntimeError("factory MCP action failed")
            return response["result"]

        return self.guard.mutate(service, kind, identity, action)
