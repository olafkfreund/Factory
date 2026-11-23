"""Stdio MCP server for `factory_submit`, `factory_test`, `factory_status`, `factory_doctor`."""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from typing import Any, Literal, Protocol, cast

from factory_cli.config import RuntimeContext, collect_known_secrets
from factory_cli.doctor import run_doctor
from factory_cli.status import run_status
from factory_cli.submit import run_submit
from factory_cli.testrun import run_test
from factory_cli.transport import redact_structure, redact_text


class McpServerProtocol(Protocol):
    """Minimal protocol shared by `mcp` 1.x `FastMCP` and `mcp` 2.x `MCPServer`."""

    def add_tool(
        self,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Any: ...

    def run(
        self,
        transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
    ) -> Any: ...


def _create_mcp_server(name: str) -> McpServerProtocol:
    for mod_name, attr in (
        ("mcp.server.mcpserver", "MCPServer"),
        ("mcp.server.fastmcp", "FastMCP"),
    ):
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            continue
        cls = getattr(mod, attr, None)
        if callable(cls):
            return cast(McpServerProtocol, cls(name))
    raise ModuleNotFoundError("mcp SDK is required to run `factory mcp`")


def dump_mcp_json(
    payload: Any,
    *,
    ctx: RuntimeContext | None = None,
) -> str:
    """Recursively redact both keys and values in *payload* before serialising to JSON."""
    rt = ctx or RuntimeContext()
    secrets = collect_known_secrets(env=rt.env, home=rt.home)
    safe_payload = redact_structure(payload, secrets)
    return redact_text(json.dumps(safe_payload, indent=2), secrets)


def handle_factory_submit(
    slug: str,
    *,
    base_ref: str | None = None,
    project_id: str | None = None,
    dry_run: bool = True,
    ctx: RuntimeContext | None = None,
) -> str:
    """MCP handler for `factory_submit` (defaults to `dry_run=True`)."""
    outcome = run_submit(
        slug,
        base_ref=base_ref,
        project_id=project_id,
        dry_run=dry_run,
        ctx=ctx,
    )
    return dump_mcp_json(outcome.payload, ctx=ctx)


def handle_factory_test(  # noqa: PLR0913
    project_id: str,
    branch: str,
    *,
    spec: str | None = None,
    criteria: str | None = None,
    pr_number: int | None = None,
    ctx: RuntimeContext | None = None,
) -> str:
    """MCP handler for `factory_test`."""
    outcome = run_test(
        project_id,
        branch,
        spec_slug=spec,
        criteria_file=criteria,
        pr_number=pr_number,
        ctx=ctx,
    )
    return dump_mcp_json(outcome.payload, ctx=ctx)


def handle_factory_status(
    target: str,
    *,
    ctx: RuntimeContext | None = None,
) -> str:
    """MCP handler for `factory_status`."""
    outcome = run_status(target, ctx=ctx)
    return dump_mcp_json(outcome.payload, ctx=ctx)


def handle_factory_doctor(
    *,
    ctx: RuntimeContext | None = None,
) -> str:
    """MCP handler for `factory_doctor`."""
    outcome = run_doctor(ctx=ctx)
    return dump_mcp_json(outcome.payload, ctx=ctx)


def build_mcp_server() -> McpServerProtocol:
    """Construct the MCP server with the four Factory tools registered."""
    server = _create_mcp_server("factory")

    def factory_submit(
        slug: str,
        base_ref: str | None = None,
        project_id: str | None = None,
        dry_run: bool = True,
    ) -> str:
        return handle_factory_submit(
            slug,
            base_ref=base_ref,
            project_id=project_id,
            dry_run=dry_run,
        )

    def factory_test(
        project_id: str,
        branch: str,
        spec: str | None = None,
        criteria: str | None = None,
        pr_number: int | None = None,
    ) -> str:
        return handle_factory_test(
            project_id=project_id,
            branch=branch,
            spec=spec,
            criteria=criteria,
            pr_number=pr_number,
        )

    def factory_status(target: str) -> str:
        return handle_factory_status(target)

    def factory_doctor() -> str:
        return handle_factory_doctor()

    server.add_tool(
        factory_submit,
        name="factory_submit",
        description=(
            "Submit an approved intent/spec/plan triple to PFactory and emit a signed contract "
            "to AIFactory. Defaults to dry_run=true."
        ),
    )
    server.add_tool(
        factory_test,
        name="factory_test",
        description=(
            "Schedule a TFactory verification run for an existing registered project "
            "from spec/<slug>.md Verification bullets or a criteria file."
        ),
    )
    server.add_tool(
        factory_status,
        name="factory_status",
        description=(
            "Check status of pf:<session>, af:<task>, tf:<project>/<spec>, "
            "or a bare correlation key (requires CFactory key; tenant-wide view)."
        ),
    )
    server.add_tool(
        factory_doctor,
        name="factory_doctor",
        description="Inspect portal URLs, key sources, key kinds, health versions, and access.",
    )
    return server


def run_mcp_stdio() -> int:
    """Run the stdio MCP server until EOF."""
    server = build_mcp_server()
    server.run(transport="stdio")
    return 0
