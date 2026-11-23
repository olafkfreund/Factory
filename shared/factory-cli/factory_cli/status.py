"""Implementation of `factory status` across PFactory, AIFactory, TFactory, and CFactory."""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Literal

from factory_cli._common import CommandOutcome
from factory_cli._vendor.factory_common.client_errors import InputRejectedError
from factory_cli.config import (
    PortalName,
    RuntimeContext,
    collect_known_secrets,
    resolve_portal_key,
    resolve_portal_url,
)
from factory_cli.submit import (
    EXIT_OK,
    EXIT_PRECONDITION,
    EXIT_REJECTED,
    extract_aifactory_task_id,
)
from factory_cli.transport import (
    PortalTransport,
    TransportResponse,
    extract_safe_detail,
    redact_structure,
    redact_text,
)

_HTTP_OK = int(HTTPStatus.OK)
_HTTP_NOT_FOUND = int(HTTPStatus.NOT_FOUND)
_AUTH_FAIL_CODES = frozenset({int(HTTPStatus.UNAUTHORIZED), int(HTTPStatus.FORBIDDEN)})
_STATUS_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._:#-]+$")


@dataclass(frozen=True)
class StatusOutcome(CommandOutcome):
    """Result of a `factory status` query."""


def _validate_and_quote_segment(segment: str, *, label: str = "identifier") -> str:
    """Validate segment against `^[A-Za-z0-9._:#-]+$`, reject `.`/`..`, and quote with safe=''."""
    if not segment or segment in (".", "..") or not _STATUS_SEGMENT_RE.match(segment):
        raise ValueError(f"invalid {label}: {segment!r}")
    return urllib.parse.quote(segment, safe="")


def _extract_aifactory_task_id(session_data: dict[str, Any]) -> str | None:
    contract_result = session_data.get("contract_result")
    if not isinstance(contract_result, dict):
        return None
    return extract_aifactory_task_id(contract_result)


def _make_transport(
    portal: PortalName,
    rt: RuntimeContext,
    secrets: tuple[str, ...],
) -> tuple[PortalTransport | None, str | None, int]:
    try:
        key = resolve_portal_key(portal, env=rt.env, home=rt.home)
    except ValueError as exc:
        return None, str(exc), EXIT_PRECONDITION
    if key is None:
        return None, f"{portal} key not configured", EXIT_PRECONDITION
    try:
        url = resolve_portal_url(
            portal,
            env=rt.env,
            home=rt.home,
            config_path=rt.config_path,
        )
    except ValueError as exc:
        return None, str(exc), EXIT_PRECONDITION
    try:
        return PortalTransport(url, token=key.value, secrets=secrets), None, EXIT_OK
    except InputRejectedError as exc:
        return None, str(exc), EXIT_PRECONDITION


def _rejected_status(
    detail: str,
    *,
    exit_code: int = EXIT_REJECTED,
    secrets: tuple[str, ...] = (),
) -> StatusOutcome:
    safe = redact_text(detail, secrets)
    return StatusOutcome(
        exit_code=exit_code,
        outcome="rejected",
        payload=redact_structure({"outcome": "rejected", "detail": safe}, secrets),
        lines=(safe if safe == "not found" else f"error: {safe}",),
    )


def _portal_error_detail(resp: TransportResponse, secrets: tuple[str, ...]) -> str:
    if resp.status == _HTTP_NOT_FOUND:
        return "not found"
    return resp.network_error or extract_safe_detail(resp.data, resp.raw_text, secrets)


def _handle_portal_error(resp: TransportResponse, secrets: tuple[str, ...]) -> StatusOutcome:
    detail = _portal_error_detail(resp, secrets)
    return _rejected_status(detail, exit_code=EXIT_REJECTED, secrets=secrets)


def _safe_request(
    transport: PortalTransport,
    method: str,
    path: str,
    secrets: tuple[str, ...],
) -> TransportResponse:
    """Issue a transport request, catching any unexpected exception into a status=0 response."""
    try:
        return transport.request(method, path)
    except Exception as exc:  # noqa: BLE001
        msg = redact_text(str(exc) or type(exc).__name__, secrets)
        return TransportResponse(
            status=0,
            data={},
            raw_text=msg,
            is_json=False,
            network_error=msg,
            after_send=False,
        )


def _follow_aifactory_task(
    af_task_id: str,
    rt: RuntimeContext,
    secrets: tuple[str, ...],
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    lines = [f"aifactory_task_id: af:{af_task_id}"]
    try:
        safe_task = _validate_and_quote_segment(af_task_id, label="AIFactory task id")
    except ValueError as exc:
        err_msg = redact_text(str(exc), secrets)
        lines.append(f"aifactory_error: {err_msg}")
        return None, err_msg, lines

    af_transport, af_transport_err, _ = _make_transport("aifactory", rt, secrets)
    if af_transport is None:
        if af_transport_err != "aifactory key not configured":
            err_msg = redact_text(af_transport_err or "aifactory error", secrets)
            lines.append(f"aifactory_error: {err_msg}")
            return None, err_msg, lines
        return None, None, lines

    af_resp = _safe_request(af_transport, "GET", f"/api/mcp-stdio/tasks/{safe_task}", secrets)
    if af_resp.status == _HTTP_OK and af_resp.is_json and isinstance(af_resp.data, dict):
        af_data = af_resp.data
        lines.append(f"aifactory_status: {af_data.get('status', 'unknown')}")
        return af_data, None, lines

    err_msg = redact_text(_portal_error_detail(af_resp, secrets), secrets)
    if err_msg == "not found":
        lines.append("aifactory_status: not found")
    else:
        lines.append(f"aifactory_error: {err_msg}")
    return None, err_msg, lines


def _status_pf(session_id: str, rt: RuntimeContext, secrets: tuple[str, ...]) -> StatusOutcome:
    if not session_id:
        return _rejected_status(
            "missing PFactory session id after pf:",
            exit_code=EXIT_PRECONDITION,
            secrets=secrets,
        )
    try:
        safe_id = _validate_and_quote_segment(session_id, label="PFactory session id")
    except ValueError as exc:
        return _rejected_status(str(exc), exit_code=EXIT_PRECONDITION, secrets=secrets)

    transport, err, err_code = _make_transport("pfactory", rt, secrets)
    if transport is None:
        return _rejected_status(err or "pfactory error", exit_code=err_code, secrets=secrets)

    resp = _safe_request(transport, "GET", f"/api/mcp-stdio/plan/sessions/{safe_id}", secrets)
    if resp.status != _HTTP_OK or not resp.is_json or not isinstance(resp.data, dict):
        return _handle_portal_error(resp, secrets)

    pf_data = resp.data
    status_str = str(pf_data.get("status") or "unknown")
    correlation_key = str(pf_data.get("correlation_key") or f"pf-{session_id}")
    contract_result = pf_data.get("contract_result")
    af_task_id = _extract_aifactory_task_id(pf_data)

    lines = [
        f"pfactory_session: pf:{session_id}",
        f"pfactory_status: {status_str}",
        f"correlation_key: {correlation_key}",
    ]
    af_data: dict[str, Any] | None = None
    af_error: str | None = None

    if af_task_id:
        af_data, af_error, extra_lines = _follow_aifactory_task(af_task_id, rt, secrets)
        lines.extend(extra_lines)

    outcome_literal: Literal["ok", "rejected"] = "rejected" if af_error is not None else "ok"
    exit_code = EXIT_REJECTED if af_error is not None else EXIT_OK
    payload_dict: dict[str, Any] = {
        "outcome": outcome_literal,
        "kind": "pf",
        "session_id": session_id,
        "pfactory_status": status_str,
        "correlation_key": correlation_key,
        "contract_result": contract_result,
        "aifactory_task_id": af_task_id,
        "aifactory_task": af_data,
    }
    if af_error is not None:
        payload_dict["detail"] = af_error

    payload = redact_structure(payload_dict, secrets)
    return StatusOutcome(
        exit_code=exit_code,
        outcome=outcome_literal,
        payload=payload,
        lines=tuple(lines),
    )


def _status_af(task_id: str, rt: RuntimeContext, secrets: tuple[str, ...]) -> StatusOutcome:
    if not task_id:
        return _rejected_status(
            "missing AIFactory task id after af:",
            exit_code=EXIT_PRECONDITION,
            secrets=secrets,
        )
    try:
        safe_task = _validate_and_quote_segment(task_id, label="AIFactory task id")
    except ValueError as exc:
        return _rejected_status(str(exc), exit_code=EXIT_PRECONDITION, secrets=secrets)

    transport, err, err_code = _make_transport("aifactory", rt, secrets)
    if transport is None:
        return _rejected_status(err or "aifactory error", exit_code=err_code, secrets=secrets)

    resp = _safe_request(transport, "GET", f"/api/mcp-stdio/tasks/{safe_task}", secrets)
    if resp.status != _HTTP_OK or not resp.is_json or not isinstance(resp.data, dict):
        return _handle_portal_error(resp, secrets)

    af_task = resp.data
    st = str(af_task.get("status") or "unknown")
    lines = [
        f"aifactory_task_id: af:{task_id}",
        f"aifactory_status: {st}",
    ]
    if af_task.get("title"):
        lines.append(f"title: {af_task['title']}")
    payload = redact_structure(
        {
            "outcome": "ok",
            "kind": "af",
            "task_id": task_id,
            "aifactory_status": st,
            "task": af_task,
        },
        secrets,
    )
    return StatusOutcome(exit_code=EXIT_OK, outcome="ok", payload=payload, lines=tuple(lines))


def _status_tf(rest: str, rt: RuntimeContext, secrets: tuple[str, ...]) -> StatusOutcome:
    project_id, sep, spec_id = rest.partition("/")
    clean_proj = project_id.strip()
    clean_spec = spec_id.strip()
    if not sep or not clean_proj or not clean_spec:
        return _rejected_status(
            "expected tf:<project>/<spec>",
            exit_code=EXIT_PRECONDITION,
            secrets=secrets,
        )
    try:
        safe_proj = _validate_and_quote_segment(clean_proj, label="TFactory project id")
        safe_spec = _validate_and_quote_segment(clean_spec, label="TFactory spec id")
    except ValueError as exc:
        return _rejected_status(str(exc), exit_code=EXIT_PRECONDITION, secrets=secrets)

    transport, err, err_code = _make_transport("tfactory", rt, secrets)
    if transport is None:
        return _rejected_status(err or "tfactory error", exit_code=err_code, secrets=secrets)

    resp = _safe_request(
        transport,
        "GET",
        f"/api/mcp-stdio/spec-tasks/{safe_proj}/{safe_spec}",
        secrets,
    )
    if resp.status != _HTTP_OK or not resp.is_json or not isinstance(resp.data, dict):
        return _handle_portal_error(resp, secrets)

    tf_data = resp.data
    status_json = tf_data.get("status_json")
    tf_status = (
        str(status_json.get("status") or "unknown")
        if isinstance(status_json, dict)
        else str(tf_data.get("status") or "unknown")
    )
    lines = [
        f"tf_id: tf:{clean_proj}/{clean_spec}",
        f"tfactory_status: {tf_status}",
    ]
    payload = redact_structure(
        {
            "outcome": "ok",
            "kind": "tf",
            "project_id": clean_proj,
            "spec_id": clean_spec,
            "tfactory_status": tf_status,
            "spec_task": tf_data,
        },
        secrets,
    )
    return StatusOutcome(exit_code=EXIT_OK, outcome="ok", payload=payload, lines=tuple(lines))


def _status_cf(ident: str, rt: RuntimeContext, secrets: tuple[str, ...]) -> StatusOutcome:
    try:
        safe_key = _validate_and_quote_segment(ident, label="correlation key")
    except ValueError as exc:
        return _rejected_status(str(exc), exit_code=EXIT_PRECONDITION, secrets=secrets)

    cf_transport, err, err_code = _make_transport("cfactory", rt, secrets)
    if cf_transport is None and err_code == EXIT_PRECONDITION and err and "not configured" in err:
        return _rejected_status(
            "use pf:/af:/tf: ids (no CFactory key configured)",
            exit_code=EXIT_PRECONDITION,
            secrets=secrets,
        )
    if cf_transport is None:
        return _rejected_status(err or "cfactory error", exit_code=err_code, secrets=secrets)

    resp = _safe_request(cf_transport, "GET", f"/api/workitems/{safe_key}", secrets)
    if resp.status in _AUTH_FAIL_CODES:
        return _rejected_status(
            "use pf:/af:/tf: ids",
            exit_code=EXIT_PRECONDITION,
            secrets=secrets,
        )
    if resp.status != _HTTP_OK or not resp.is_json or not isinstance(resp.data, dict):
        return _handle_portal_error(resp, secrets)

    cf_data = resp.data
    lines = [
        f"correlation_key: {ident}",
        f"status: {cf_data.get('status', 'unknown')}",
    ]
    payload = redact_structure(
        {
            "outcome": "ok",
            "kind": "cf",
            "correlation_key": ident,
            "workitem": cf_data,
        },
        secrets,
    )
    return StatusOutcome(exit_code=EXIT_OK, outcome="ok", payload=payload, lines=tuple(lines))


def run_status(
    target: str,
    *,
    ctx: RuntimeContext | None = None,
) -> StatusOutcome:
    """Query status for `pf:<session>`, `af:<task>`, `tf:<project>/<spec>`, or a correlation key."""
    rt = ctx or RuntimeContext()
    ident = target.strip()
    if not ident:
        secrets = collect_known_secrets(env=rt.env, home=rt.home, portals=())
        return _rejected_status(
            "status identifier is required",
            exit_code=EXIT_PRECONDITION,
            secrets=secrets,
        )
    if ident.startswith("pf:"):
        secrets = collect_known_secrets(
            env=rt.env,
            home=rt.home,
            portals=("pfactory", "aifactory"),
        )
        return _status_pf(ident[3:].strip(), rt, secrets)
    if ident.startswith("af:"):
        secrets = collect_known_secrets(env=rt.env, home=rt.home, portals=("aifactory",))
        return _status_af(ident[3:].strip(), rt, secrets)
    if ident.startswith("tf:"):
        secrets = collect_known_secrets(env=rt.env, home=rt.home, portals=("tfactory",))
        return _status_tf(ident[3:].strip(), rt, secrets)
    secrets = collect_known_secrets(env=rt.env, home=rt.home, portals=("cfactory",))
    return _status_cf(ident, rt, secrets)
