"""Injected stdio transport for factory mcp actions."""

import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from scripts.e2e.config import KEY_FILES
from scripts.e2e.guard import Guard, GuardRefusalError
from scripts.e2e.surfaces.cli import CLI_ROOT, isolated_env

_MCP_CALL = """
import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def main():
    request = json.load(sys.stdin)
    server = StdioServerParameters(command=sys.executable,
                                   args=["-m", "factory_cli", "mcp"], env=dict(os.environ))
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.call_tool(request["tool"], request["arguments"])
            print(json.dumps({"error": result.isError,
                              "content": [item.text for item in result.content
                                          if hasattr(item, "text")]}))
asyncio.run(main())
"""


def invoke(  # noqa: PLR0913
    tool: str,
    arguments: dict[str, object],
    *,
    cwd: Path,
    key_files: dict[str, Path] | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    allow_rejected: bool = False,
) -> dict[str, Any]:
    if not tool.startswith("factory_"):
        raise ValueError("unknown factory MCP tool")
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv unavailable")
    with tempfile.TemporaryDirectory(prefix="factory-e2e-") as home:
        result = run(
            [
                uv,
                "run",
                "--no-project",
                "--with-editable",
                str(CLI_ROOT),
                "python",
                "-c",
                _MCP_CALL,
            ],
            input=json.dumps({"tool": tool, "arguments": arguments}),
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
            env=isolated_env(home, KEY_FILES if key_files is None else key_files),
            timeout=120,
        )
    if result.returncode:
        raise RuntimeError(f"factory MCP transport failed with exit {result.returncode}")
    envelope = json.loads(result.stdout)
    if envelope["error"] or not envelope["content"]:
        raise RuntimeError("factory MCP tool failed")
    payload = json.loads(envelope["content"][0])
    if payload.get("outcome") != "ok" and not allow_rejected:
        raise RuntimeError("factory MCP action rejected")
    return cast(dict[str, Any], payload)


ID_SHAPED = re.compile(
    r"(?:\b(?:af|pf|tf):\S+|\b(?:task|card)-[\w-]+|\b[A-Z]+-\d+\b|\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b|\b\d+\b)",
    re.I,
)


class MCP:
    def __init__(
        self, guard: Guard, request: Callable[[str, dict[str, object]], dict[str, Any]]
    ) -> None:
        self.guard = guard
        self.request = request

    def call(
        self, service: str, kind: str, identity: str, method: str, **params: object
    ) -> dict[str, Any]:
        if any(ID_SHAPED.search(str(value)) for value in params.values()) or any(
            key.lower().replace("_", "")
            in {"id", "key", "taskid", "cardkey", "projectid", "sessionid", "specid"}
            for key in params
        ):
            raise GuardRefusalError("caller supplied another target")
        target_field = "key" if kind == "card" else "id"
        if target_field in params:
            raise GuardRefusalError("caller supplied mutation target")

        def action() -> dict[str, Any]:
            response = self.request(method, {**params, target_field: identity})
            if response.get("error"):
                raise RuntimeError("factory MCP action failed")
            return cast(dict[str, Any], response["result"])

        return cast(dict[str, Any], self.guard.mutate(service, kind, identity, action))
