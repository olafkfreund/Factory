"""Shared CLI and stdio MCP handlers for portal actions."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any, Literal

from factory_cli._common import CommandOutcome
from factory_cli._vendor.factory_common.client_errors import InputRejectedError
from factory_cli.config import PortalName, RuntimeContext, collect_known_secrets
from factory_cli.status import _make_transport, _validate_and_quote_segment
from factory_cli.submit import EXIT_OK, EXIT_PRECONDITION, EXIT_REJECTED, EXIT_UNKNOWN
from factory_cli.transport import (
    TransportResponse,
    extract_safe_detail,
    redact_structure,
    redact_text,
)

PROJECT_PORTALS: tuple[PortalName, ...] = ("aifactory", "pfactory", "tfactory")
JSON_RPC_INTERNAL_ERROR = -32603


def _outcome(
    kind: str, detail: Any, secrets: tuple[str, ...], *, exit_code: int = EXIT_OK
) -> CommandOutcome:
    outcome: Literal["ok", "unknown", "rejected"] = (
        "ok" if exit_code == EXIT_OK else "unknown" if exit_code == EXIT_UNKNOWN else "rejected"
    )
    safe = redact_structure(detail, secrets)
    payload = {"outcome": outcome, "action": kind, "result" if exit_code == 0 else "detail": safe}
    line = json.dumps(safe, sort_keys=True) if exit_code == 0 else f"{outcome}: {safe}"
    return CommandOutcome(exit_code, outcome, payload, (redact_text(line, secrets),))


def _request(  # noqa: PLR0913 - portal, request, context and redaction are the transport boundary
    portal: PortalName,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    rt: RuntimeContext,
    secrets: tuple[str, ...],
    action: str,
) -> CommandOutcome:
    transport, error, code = _make_transport(portal, rt, secrets)
    if transport is None:
        return _outcome(action, error or "portal unavailable", secrets, exit_code=code)
    try:
        response = transport.request(method, path, body=body)
    except InputRejectedError as exc:
        return _outcome(action, exc.client_message, secrets, exit_code=EXIT_PRECONDITION)
    except Exception as exc:  # noqa: BLE001 - do not leak transport internals
        return _outcome(action, type(exc).__name__, secrets, exit_code=EXIT_PRECONDITION)
    return _response(action, response, secrets, mutates=method != "GET" and action != "card list")


def _response(
    action: str, response: TransportResponse, secrets: tuple[str, ...], *, mutates: bool
) -> CommandOutcome:
    if HTTPStatus.OK <= response.status < HTTPStatus.MULTIPLE_CHOICES and response.is_json:
        data = response.data
        if isinstance(data, dict) and data.get("error") and not action.startswith("card "):
            return _outcome(
                action,
                extract_safe_detail(data, response.raw_text, secrets),
                secrets,
                exit_code=EXIT_REJECTED,
            )
        return _outcome(action, data, secrets)
    detail = response.network_error or extract_safe_detail(
        response.data, response.raw_text, secrets
    )
    if response.status == HTTPStatus.NOT_FOUND:
        detail = "not found"
    if response.status == 0 and not response.after_send:
        code = EXIT_PRECONDITION
    elif (
        mutates
        and response.after_send
        and (
            response.status == 0
            or response.status >= HTTPStatus.INTERNAL_SERVER_ERROR
            or HTTPStatus.MULTIPLE_CHOICES <= response.status < HTTPStatus.BAD_REQUEST
            or HTTPStatus.OK <= response.status < HTTPStatus.MULTIPLE_CHOICES
        )
    ):
        code = EXIT_UNKNOWN
    else:
        code = EXIT_REJECTED
    return _outcome(action, detail, secrets, exit_code=code)


def run_project(  # noqa: PLR0913 - mirrors the project create request
    operation: str,
    *,
    portal: PortalName | None = None,
    git_url: str | None = None,
    name: str | None = None,
    branch: str | None = None,
    ctx: RuntimeContext | None = None,
) -> CommandOutcome:
    """List projects across the three portals, or add one through its proxy."""
    rt = ctx or RuntimeContext()
    if portal is not None and portal not in PROJECT_PORTALS:
        return _outcome("project", "invalid portal", (), exit_code=EXIT_PRECONDITION)
    portals = (portal,) if portal else PROJECT_PORTALS
    secrets = collect_known_secrets(env=rt.env, home=rt.home, portals=portals)
    if operation == "list":
        results: dict[str, Any] = {}
        for item in portals:
            result = _request(
                item, "GET", "/api/mcp-stdio/projects", None, rt, secrets, "project list"
            )
            if result.exit_code != EXIT_OK:
                return result
            results[item] = result.payload["result"]
        return _outcome("project list", results, secrets)
    if operation != "add" or portal is None or not git_url:
        return _outcome(
            "project add", "portal and git URL are required", secrets, exit_code=EXIT_PRECONDITION
        )
    body = {"gitUrl": git_url}
    if name:
        body["name"] = name
    if branch:
        body["branch"] = branch
    return _request(portal, "POST", "/api/mcp-stdio/projects", body, rt, secrets, "project add")


def run_action(  # noqa: PLR0912 - action routing validates each supported ID shape
    action: str,
    target: str,
    *,
    feedback: str | None = None,
    ctx: RuntimeContext | None = None,
) -> CommandOutcome:
    """Approve/reject PF or AF plans, and recover/archive AF or TF tasks."""
    rt = ctx or RuntimeContext()
    prefix, sep, ident = target.strip().partition(":")
    portals: dict[str, PortalName] = {"pf": "pfactory", "af": "aifactory", "tf": "tfactory"}
    portal = portals.get(prefix)
    secrets = collect_known_secrets(env=rt.env, home=rt.home, portals=(portal,) if portal else ())
    if (
        action not in ("approve", "reject", "retry", "archive")
        or not sep
        or portal is None
        or (action in ("approve", "reject") and prefix == "tf")
        or (action in ("retry", "archive") and prefix == "pf")
    ):
        return _outcome(action, "invalid target for action", secrets, exit_code=EXIT_PRECONDITION)
    spec = ""
    try:
        if prefix == "tf":
            project, slash, spec = ident.partition("/")
            if not slash or not project.strip() or not spec.strip():
                raise InputRejectedError("expected tf:<project>/<spec>")
            _validate_and_quote_segment(project, label="project id")
            _validate_and_quote_segment(spec, label="spec id")
            safe_id = _validate_and_quote_segment(f"{project}:{spec}", label="task id")
        else:
            if not ident.strip() or (prefix == "af" and ":" in ident and not all(ident.split(":"))):
                raise InputRejectedError("invalid task id")
            safe_id = _validate_and_quote_segment(ident, label="task id")
        if action == "archive":
            if prefix == "af" and ":" not in ident:
                raise InputRejectedError("expected af:<project>:<task>")
            project = ident.split(":" if prefix == "af" else "/", 1)[0]
            safe_project = _validate_and_quote_segment(project, label="project id")
            path = f"/api/mcp-stdio/projects/{safe_project}/tasks/archive"
            body: dict[str, Any] = {"taskIds": [ident if prefix == "af" else f"{project}:{spec}"]}
        elif prefix == "pf":
            path = f"/api/mcp-stdio/plan/sessions/{safe_id}/{action}"
            body = {"approver": "factory-cli"}
            if action == "reject":
                if not feedback:
                    raise InputRejectedError("reject feedback is required")
                body["feedback"] = feedback
        else:
            suffix = {"approve": "approve-plan", "reject": "reject-plan", "retry": "recover"}[
                action
            ]
            path = f"/api/mcp-stdio/tasks/{safe_id}/{suffix}"
            body = (
                {"autoRestart": True}
                if action == "retry"
                else ({"feedback": feedback} if action == "reject" else {})
            )
            if action == "reject" and not feedback:
                raise InputRejectedError("reject feedback is required")
    except InputRejectedError as exc:
        return _outcome(action, exc.client_message, secrets, exit_code=EXIT_PRECONDITION)
    except ValueError:
        return _outcome(action, "invalid task id", secrets, exit_code=EXIT_PRECONDITION)
    result = _request(portal, "POST", path, body, rt, secrets, action)
    if action == "retry" and prefix == "af" and result.exit_code == EXIT_OK:
        data = result.payload["result"]
        if (
            isinstance(data, dict)
            and isinstance(data.get("data"), dict)
            and data["data"].get("autoRestarted") is False
        ):
            return _outcome(action, "task was not restarted", secrets, exit_code=EXIT_UNKNOWN)
    return result


def run_card(  # noqa: PLR0911, PLR0913 - one handler for four card operations
    action: str,
    *,
    card_key: str | None = None,
    title: str | None = None,
    status: str | None = None,
    tier: str | None = None,
    ctx: RuntimeContext | None = None,
) -> CommandOutcome:
    """Call a CFactory card tool through its JSON-RPC endpoint."""
    rt = ctx or RuntimeContext()
    secrets = collect_known_secrets(env=rt.env, home=rt.home, portals=("cfactory",))
    names = {
        "create": "cfactory_create_card",
        "move": "cfactory_move_card",
        "list": "cfactory_list_cards",
        "run": "cfactory_run_card",
    }
    if action not in names:
        return _outcome("card", "invalid card action", secrets, exit_code=EXIT_PRECONDITION)
    arguments = {
        k: v
        for k, v in {"card_key": card_key, "title": title, "status": status, "tier": tier}.items()
        if v is not None
    }
    allowed = {
        "create": {"card_key", "title", "status", "tier"},
        "move": {"card_key", "status"},
        "list": {"status", "tier"},
        "run": {"card_key"},
    }[action]
    arguments = {k: v for k, v in arguments.items() if k in allowed}
    required = {
        "create": ("title",),
        "move": ("card_key", "status"),
        "list": (),
        "run": ("card_key",),
    }[action]
    if any(not arguments.get(field, "").strip() for field in required):
        return _outcome(
            f"card {action}",
            f"required: {', '.join(required)}",
            secrets,
            exit_code=EXIT_PRECONDITION,
        )
    if tier is not None and tier not in ("low", "medium", "hard"):
        return _outcome(f"card {action}", "invalid tier", secrets, exit_code=EXIT_PRECONDITION)
    if status is not None and status not in ("backlog", "ready", "in_progress", "blocked", "done"):
        return _outcome(f"card {action}", "invalid status", secrets, exit_code=EXIT_PRECONDITION)
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": names[action], "arguments": arguments},
    }
    result = _request("cfactory", "POST", "/mcp", body, rt, secrets, f"card {action}")
    if result.exit_code != EXIT_OK:
        return result
    rpc = result.payload["result"]
    malformed_code = EXIT_REJECTED if action == "list" else EXIT_UNKNOWN
    if (
        not isinstance(rpc, dict)
        or rpc.get("jsonrpc") != "2.0"
        or rpc.get("id") != 1
        or ("result" not in rpc and "error" not in rpc)
    ):
        return _outcome(
            f"card {action}", "invalid JSON-RPC response", secrets, exit_code=malformed_code
        )
    if "error" in rpc:
        error = rpc["error"]
        if not isinstance(error, dict):
            return _outcome(
                f"card {action}", "invalid JSON-RPC error", secrets, exit_code=malformed_code
            )
        code = (
            EXIT_UNKNOWN
            if action != "list" and error.get("code") == JSON_RPC_INTERNAL_ERROR
            else EXIT_REJECTED
        )
        return _outcome(f"card {action}", error, secrets, exit_code=code)
    tool_result = rpc["result"]
    if not isinstance(tool_result, dict) or not isinstance(tool_result.get("content"), list):
        return _outcome(
            f"card {action}", "invalid tool response", secrets, exit_code=malformed_code
        )
    contents = tool_result["content"]
    try:
        data = json.loads(contents[0]["text"])
    except (IndexError, KeyError, TypeError, ValueError):
        if (
            tool_result.get("isError")
            and contents
            and isinstance(contents[0], dict)
            and isinstance(contents[0].get("text"), str)
        ):
            return _outcome(f"card {action}", contents[0]["text"], secrets, exit_code=EXIT_REJECTED)
        return _outcome(
            f"card {action}", "invalid tool response", secrets, exit_code=malformed_code
        )
    if tool_result.get("isError") or (isinstance(data, dict) and data.get("error")):
        return _outcome(f"card {action}", data, secrets, exit_code=EXIT_REJECTED)
    return _outcome(f"card {action}", data, secrets)
