"""Stdio MCP server for `factory_submit`, `factory_test`, `factory_status`, `factory_doctor`."""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from typing import Any, Literal, Protocol, cast

from factory_cli.actions import run_action, run_card, run_project
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


def handle_factory_project_list(
    portal: str | None = None, *, ctx: RuntimeContext | None = None
) -> str:
    return dump_mcp_json(run_project("list", portal=cast(Any, portal), ctx=ctx).payload, ctx=ctx)


def handle_factory_project_add(
    portal: str,
    git_url: str,
    name: str | None = None,
    branch: str | None = None,
    *,
    ctx: RuntimeContext | None = None,
) -> str:
    return dump_mcp_json(
        run_project(
            "add", portal=cast(Any, portal), git_url=git_url, name=name, branch=branch, ctx=ctx
        ).payload,
        ctx=ctx,
    )


def handle_factory_action(
    action: str,
    target: str,
    feedback: str | None = None,
    *,
    ctx: RuntimeContext | None = None,
) -> str:
    return dump_mcp_json(run_action(action, target, feedback=feedback, ctx=ctx).payload, ctx=ctx)


def handle_factory_card(  # noqa: PLR0913 - mirrors the card tool arguments
    action: str,
    card_key: str | None = None,
    title: str | None = None,
    status: str | None = None,
    tier: str | None = None,
    *,
    ctx: RuntimeContext | None = None,
) -> str:
    return dump_mcp_json(
        run_card(action, card_key=card_key, title=title, status=status, tier=tier, ctx=ctx).payload,
        ctx=ctx,
    )


def build_mcp_server() -> McpServerProtocol:
    """Construct the MCP server with Factory tools registered."""
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

    def factory_project_list(portal: str | None = None) -> str:
        return handle_factory_project_list(portal)

    def factory_project_add(
        portal: str, git_url: str, name: str | None = None, branch: str | None = None
    ) -> str:
        return handle_factory_project_add(portal, git_url, name, branch)

    def factory_approve(target: str) -> str:
        return handle_factory_action("approve", target)

    def factory_reject(target: str, feedback: str) -> str:
        return handle_factory_action("reject", target, feedback)

    def factory_retry(target: str) -> str:
        return handle_factory_action("retry", target)

    def factory_archive(target: str) -> str:
        return handle_factory_action("archive", target)

    def factory_card_create(
        title: str, card_key: str | None = None, tier: str | None = None, status: str | None = None
    ) -> str:
        return handle_factory_card("create", card_key, title, status, tier)

    def factory_card_move(card_key: str, status: str) -> str:
        return handle_factory_card("move", card_key, status=status)

    def factory_card_list(status: str | None = None, tier: str | None = None) -> str:
        return handle_factory_card("list", status=status, tier=tier)

    def factory_card_run(card_key: str) -> str:
        return handle_factory_card("run", card_key)

    for fn, name, description in (
        (
            factory_project_list,
            "factory_project_list",
            "List registered projects on AIFactory, PFactory, and TFactory.",
        ),
        (
            factory_project_add,
            "factory_project_add",
            "Register a Git repository on one Factory portal.",
        ),
        (factory_approve, "factory_approve", "Approve a PF session or AF task plan."),
        (factory_reject, "factory_reject", "Reject a PF session or AF task plan with feedback."),
        (factory_retry, "factory_retry", "Recover and restart an AF or TF task."),
        (factory_archive, "factory_archive", "Archive an AF or TF task."),
        (factory_card_create, "factory_card_create", "Create a CFactory card."),
        (factory_card_move, "factory_card_move", "Move a CFactory card to another column."),
        (factory_card_list, "factory_card_list", "List CFactory cards."),
        (factory_card_run, "factory_card_run", "Run a CFactory card through the pipeline."),
    ):
        server.add_tool(fn, name=name, description=description)
    return server


def run_mcp_stdio() -> int:
    """Run the stdio MCP server until EOF."""
    server = build_mcp_server()
    server.run(transport="stdio")
    return 0
