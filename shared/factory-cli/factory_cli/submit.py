"""Implementation of `factory submit` (PFactory ingest-approved -> approve -> emit-contract)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from http import HTTPStatus
from pathlib import Path
from typing import Any

from factory_cli._common import CommandOutcome
from factory_cli._vendor.factory_common.client_errors import InputRejectedError
from factory_cli.config import (
    RuntimeContext,
    collect_known_secrets,
    resolve_portal_key,
    resolve_portal_url,
)
from factory_cli.gitartifacts import (
    PreconditionError,
    parse_slug,
    remote_branch_warning,
    resolve_repo_identity,
    verify_and_load_artifacts,
)
from factory_cli.transport import (
    PortalTransport,
    TransportResponse,
    extract_safe_detail,
    quote_single_segment,
    redact_structure,
    redact_text,
)

EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_PRECONDITION = 2
EXIT_UNKNOWN = 3

_HTTP_OK = int(HTTPStatus.OK)
_HTTP_SERVER_ERR = int(HTTPStatus.INTERNAL_SERVER_ERROR)
_HTTP_REDIRECT = int(HTTPStatus.MULTIPLE_CHOICES)
_HTTP_CLIENT_ERR = int(HTTPStatus.BAD_REQUEST)
_HTTP_CONFLICT = int(HTTPStatus.CONFLICT)


@dataclass(frozen=True)
class SubmitOutcome(CommandOutcome):
    """Result of a submit run (used by both CLI and MCP)."""


@dataclass(frozen=True)
class _SessionState:
    session_id: str
    correlation_key: str
    status: str
    deduped: bool
    children: list[dict[str, str]]
    hard_failures: list[Any]


def extract_aifactory_task_id(contract_result: dict[str, Any]) -> str | None:
    """Extract the AIFactory task identifier verbatim from PFactory's `contract_result`."""
    corr = contract_result.get("correlation")
    if isinstance(corr, dict) and corr.get("task_id"):
        return str(corr["task_id"])
    resp = contract_result.get("response")
    if isinstance(resp, dict):
        for key in ("task_id", "taskId", "id"):
            if resp.get(key):
                return str(resp[key])
    if contract_result.get("task_id"):
        return str(contract_result["task_id"])
    return None


def _extract_children(session_data: dict[str, Any]) -> list[dict[str, str]]:
    raw_children = session_data.get("children")
    if not isinstance(raw_children, list):
        epic = session_data.get("epic")
        if isinstance(epic, dict) and isinstance(epic.get("children"), list):
            raw_children = epic["children"]
    if not isinstance(raw_children, list):
        return []
    return [
        {
            "key": str(item.get("key") or item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "kind": str(item.get("kind") or "task"),
        }
        for item in raw_children
        if isinstance(item, dict)
    ]


def _extract_hard_failures(ingest_data: dict[str, Any]) -> list[Any]:
    readiness = ingest_data.get("readiness")
    if isinstance(readiness, dict) and isinstance(readiness.get("hard_failures"), list):
        return list(readiness["hard_failures"])
    review = ingest_data.get("review")
    if isinstance(review, dict):
        rev_readiness = review.get("readiness")
        if isinstance(rev_readiness, dict) and isinstance(rev_readiness.get("hard_failures"), list):
            return list(rev_readiness["hard_failures"])
    return []


def _session_lines(session_id: str | None, correlation_key: str | None) -> list[str]:
    lines: list[str] = []
    if session_id:
        lines.append(f"session_id: pf:{session_id}")
    if correlation_key:
        lines.append(f"correlation_key: {correlation_key}")
    return lines


def _rejected(
    detail: str,
    *,
    exit_code: int = EXIT_REJECTED,
    session_id: str | None = None,
    correlation_key: str | None = None,
    secrets: tuple[str, ...] = (),
) -> SubmitOutcome:
    safe_detail = redact_text(detail, secrets)
    lines = _session_lines(session_id, correlation_key)
    lines.append(f"error: {safe_detail}")
    payload: dict[str, Any] = redact_structure(
        {
            "outcome": "rejected",
            "session_id": session_id,
            "correlation_key": correlation_key,
            "detail": safe_detail,
        },
        secrets,
    )
    return SubmitOutcome(
        exit_code=exit_code,
        outcome="rejected",
        payload=payload,
        lines=tuple(lines),
    )


def _unknown(
    detail: str,
    *,
    session_id: str | None,
    correlation_key: str | None,
    secrets: tuple[str, ...] = (),
) -> SubmitOutcome:
    safe_detail = redact_text(detail, secrets)
    lines = _session_lines(session_id, correlation_key)
    lines.append(f"outcome unknown: {safe_detail}")
    if session_id:
        lines.append(f"reconcile with: factory status pf:{session_id}")
    payload: dict[str, Any] = redact_structure(
        {
            "outcome": "unknown",
            "session_id": session_id,
            "correlation_key": correlation_key,
            "detail": f"outcome unknown: {safe_detail}",
        },
        secrets,
    )
    return SubmitOutcome(
        exit_code=EXIT_UNKNOWN,
        outcome="unknown",
        payload=payload,
        lines=tuple(lines),
    )


def _handle_non_200(
    resp: TransportResponse,
    *,
    session_id: str | None,
    correlation_key: str | None,
    is_emit: bool,
    secrets: tuple[str, ...],
) -> SubmitOutcome:
    detail = resp.network_error or extract_safe_detail(resp.data, resp.raw_text, secrets)
    if resp.status == -1:
        return _rejected(
            detail,
            exit_code=EXIT_PRECONDITION,
            session_id=session_id,
            correlation_key=correlation_key,
            secrets=secrets,
        )
    if resp.after_send and (
        resp.status == 0
        or resp.status >= _HTTP_SERVER_ERR
        or _HTTP_REDIRECT <= resp.status < _HTTP_CLIENT_ERR
        or (resp.status == _HTTP_OK and (not resp.is_json or not isinstance(resp.data, dict)))
    ):
        return _unknown(
            detail,
            session_id=session_id,
            correlation_key=correlation_key,
            secrets=secrets,
        )
    if is_emit and resp.status == _HTTP_CONFLICT and "in progress" in detail.lower():
        return _unknown(
            detail, session_id=session_id, correlation_key=correlation_key, secrets=secrets
        )
    return _rejected(
        detail,
        exit_code=EXIT_REJECTED,
        session_id=session_id,
        correlation_key=correlation_key,
        secrets=secrets,
    )


def _parse_session_state(ingest_data: dict[str, Any]) -> _SessionState:
    session_id = str(ingest_data.get("session_id") or "").strip()
    correlation_key = str(
        ingest_data.get("correlation_key") or (f"pf-{session_id}" if session_id else "")
    )
    return _SessionState(
        session_id=session_id,
        correlation_key=correlation_key,
        status=str(ingest_data.get("status") or ""),
        deduped=bool(ingest_data.get("deduped", False)),
        children=_extract_children(ingest_data),
        hard_failures=_extract_hard_failures(ingest_data),
    )


def _build_ok_outcome(
    state: _SessionState,
    contract_result: dict[str, Any],
    *,
    dry_run: bool,
    secrets: tuple[str, ...],
) -> SubmitOutcome:
    if dry_run:
        contract = contract_result.get("contract")
        contract_summary: dict[str, Any] = {
            "signed": bool(contract_result.get("signed")),
            "endpoint": contract_result.get("endpoint"),
            "feature": contract.get("feature") if isinstance(contract, dict) else None,
            "child_count": len(state.children),
        }
        lines = [
            f"session_id: pf:{state.session_id}",
            f"correlation_key: {state.correlation_key}",
            f"dry_run: true (signed={contract_summary['signed']}, children={len(state.children)})",
            *(f"  - [{child['kind']}] {child['title']}" for child in state.children),
        ]
        return SubmitOutcome(
            exit_code=EXIT_OK,
            outcome="ok",
            payload=redact_structure(
                {
                    "outcome": "ok",
                    "session_id": state.session_id,
                    "correlation_key": state.correlation_key,
                    "dry_run": True,
                    "children": state.children,
                    "contract_summary": contract_summary,
                    "contract_result": contract_result,
                },
                secrets,
            ),
            lines=tuple(lines),
        )

    task_id = extract_aifactory_task_id(contract_result)
    lines = [
        f"session_id: pf:{state.session_id}",
        f"correlation_key: {state.correlation_key}",
    ]
    if task_id:
        lines.append(f"aifactory_task_id: af:{task_id}")
    return SubmitOutcome(
        exit_code=EXIT_OK,
        outcome="ok",
        payload=redact_structure(
            {
                "outcome": "ok",
                "session_id": state.session_id,
                "correlation_key": state.correlation_key,
                "aifactory_task_id": task_id,
                "dry_run": False,
                "deduped": state.deduped,
                "children": state.children,
                "contract_result": contract_result,
            },
            secrets,
        ),
        lines=tuple(lines),
    )


def _safe_submit_request(
    transport: PortalTransport,
    method: str,
    path: str,
    *,
    body: dict[str, Any],
    secrets: tuple[str, ...],
) -> TransportResponse:
    try:
        return transport.request(method, path, body=body)
    except InputRejectedError as exc:
        msg = redact_text(str(exc), secrets)
        return TransportResponse(
            status=-1,
            data={},
            raw_text=msg,
            is_json=False,
            network_error=msg,
            after_send=False,
        )


def _ingest_and_emit(
    transport: PortalTransport,
    ingest_body: dict[str, Any],
    *,
    dry_run: bool,
    secrets: tuple[str, ...],
) -> SubmitOutcome:
    ingest_resp = _safe_submit_request(
        transport,
        "POST",
        "/api/mcp-stdio/plan/sessions/ingest-approved",
        body=ingest_body,
        secrets=secrets,
    )
    if (
        ingest_resp.status != _HTTP_OK
        or not ingest_resp.is_json
        or not isinstance(ingest_resp.data, dict)
    ):
        return _handle_non_200(
            ingest_resp, session_id=None, correlation_key=None, is_emit=False, secrets=secrets
        )

    state = _parse_session_state(ingest_resp.data)
    try:
        safe_session_id = quote_single_segment(state.session_id, label="session_id")
    except InputRejectedError as exc:
        return _rejected(
            str(exc),
            exit_code=EXIT_REJECTED,
            session_id=state.session_id or None,
            correlation_key=state.correlation_key or None,
            secrets=secrets,
        )

    if state.hard_failures:
        return _rejected(
            f"readiness hard failures: {state.hard_failures}",
            exit_code=EXIT_REJECTED,
            session_id=state.session_id,
            correlation_key=state.correlation_key,
            secrets=secrets,
        )

    skip_approve = state.deduped and state.status in ("approved", "emitted")
    if not skip_approve:
        approve_resp = _safe_submit_request(
            transport,
            "POST",
            f"/api/mcp-stdio/plan/sessions/{safe_session_id}/approve",
            # PFactory ApproveBody requires `approver` (Factory#3882 live run: {} -> 500).
            body={"approver": "factory-cli"},
            secrets=secrets,
        )
        if approve_resp.status != _HTTP_OK:
            return _handle_non_200(
                approve_resp,
                session_id=state.session_id,
                correlation_key=state.correlation_key,
                is_emit=False,
                secrets=secrets,
            )

    emit_resp = _safe_submit_request(
        transport,
        "POST",
        f"/api/mcp-stdio/plan/sessions/{safe_session_id}/emit-contract",
        body={"dry_run": dry_run},
        secrets=secrets,
    )
    if (
        emit_resp.status != _HTTP_OK
        or not emit_resp.is_json
        or not isinstance(emit_resp.data, dict)
    ):
        return _handle_non_200(
            emit_resp,
            session_id=state.session_id,
            correlation_key=state.correlation_key,
            is_emit=True,
            secrets=secrets,
        )

    return _evaluate_emit_response(state, emit_resp.data, dry_run=dry_run, secrets=secrets)


def _evaluate_emit_response(
    state: _SessionState,
    emit_data: dict[str, Any],
    *,
    dry_run: bool,
    secrets: tuple[str, ...],
) -> SubmitOutcome:
    corr_key = str(emit_data.get("correlation_key") or state.correlation_key)
    children = state.children or _extract_children(emit_data)
    updated_state = _SessionState(
        session_id=state.session_id,
        correlation_key=corr_key,
        status=state.status,
        deduped=state.deduped,
        children=children,
        hard_failures=state.hard_failures,
    )

    raw_cr = emit_data.get("contract_result")
    contract_result = raw_cr if isinstance(raw_cr, dict) else emit_data

    if contract_result.get("outcome") == "unknown":
        errs = contract_result.get("errors")
        msg = (
            "; ".join(str(e) for e in errs)
            if isinstance(errs, list) and errs
            else "downstream task creation outcome could not be confirmed"
        )
        return _unknown(
            msg,
            session_id=updated_state.session_id,
            correlation_key=updated_state.correlation_key,
            secrets=secrets,
        )

    if contract_result.get("ok") is not True:
        errs = contract_result.get("errors")
        detail = (
            "; ".join(str(e) for e in errs)
            if isinstance(errs, list) and errs
            else str(
                contract_result.get("aifactory_detail")
                or contract_result.get("detail")
                or "contract emission failed"
            )
        )
        return _rejected(
            detail,
            exit_code=EXIT_REJECTED,
            session_id=updated_state.session_id,
            correlation_key=updated_state.correlation_key,
            secrets=secrets,
        )

    return _build_ok_outcome(updated_state, contract_result, dry_run=dry_run, secrets=secrets)


def run_submit(
    slug_or_path: str,
    *,
    base_ref: str | None = None,
    project_id: str | None = None,
    dry_run: bool = False,
    ctx: RuntimeContext | None = None,
) -> SubmitOutcome:
    """Execute the `factory submit` workflow and return a structured outcome."""
    rt = ctx or RuntimeContext()
    secrets = collect_known_secrets(env=rt.env, home=rt.home, portals=("pfactory",))
    work_dir = rt.cwd or Path.cwd()

    try:
        slug = parse_slug(slug_or_path)
        identity = resolve_repo_identity(work_dir, base_ref=base_ref, require_base=True)
        artifacts = verify_and_load_artifacts(
            identity.root,
            slug,
            head_sha=identity.head_sha,
        )
        pf_key = resolve_portal_key("pfactory", env=rt.env, home=rt.home)
        if pf_key is None:
            raise PreconditionError(
                "PFactory key not configured (set $PFACTORY_MCP_KEY or ~/.pfactory/.mcp-key)"
            )
        pf_url = resolve_portal_url(
            "pfactory",
            env=rt.env,
            home=rt.home,
            config_path=rt.config_path,
        )
    except (PreconditionError, ValueError) as exc:
        if isinstance(exc, InputRejectedError):
            return _rejected(str(exc), exit_code=EXIT_REJECTED, secrets=secrets)
        return _rejected(str(exc), exit_code=EXIT_PRECONDITION, secrets=secrets)

    try:
        transport = PortalTransport(pf_url, token=pf_key.value, secrets=secrets)
    except InputRejectedError as exc:
        return _rejected(str(exc), exit_code=EXIT_PRECONDITION, secrets=secrets)

    outcome = _ingest_and_emit(
        transport,
        {
            "slug": slug,
            "provider": identity.provider,
            "repo": identity.repo,
            "base_ref": identity.base_ref,
            "branch": identity.branch,
            "head_sha": identity.head_sha,
            "project_id": project_id,
            "artifacts": [art.to_payload() for art in artifacts],
        },
        dry_run=dry_run,
        secrets=secrets,
    )
    warning = remote_branch_warning(identity)
    return replace(outcome, lines=(*outcome.lines, warning)) if warning else outcome
