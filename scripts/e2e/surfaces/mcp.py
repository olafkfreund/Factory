"""Injected stdio transport for factory mcp actions."""

from collections.abc import Callable

from scripts.e2e.guard import Guard


class MCP:
    def __init__(self, guard: Guard, request: Callable[[str, dict], dict]) -> None:
        self.guard = guard
        self.request = request

    def call(self, kind: str, identity: str, method: str, **params: object) -> dict:
        def action() -> dict:
            response = self.request(method, params)
            if response.get("error"):
                raise RuntimeError("factory MCP action failed")
            return response["result"]

        return self.guard.mutate(kind, identity, action)
