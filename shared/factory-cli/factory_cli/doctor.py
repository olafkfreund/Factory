"""Implementation of `factory doctor` across the four Factory portals."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Literal

from factory_cli._vendor.factory_common.client_errors import InputRejectedError
from factory_cli.config import (
    PORTAL_NAMES,
    PortalName,
    RuntimeContext,
    collect_known_secrets,
    resolve_portal_key,
    resolve_portal_url,
)
from factory_cli.submit import EXIT_OK, EXIT_PRECONDITION, EXIT_REJECTED
from factory_cli.transport import PortalTransport, redact_structure, redact_text

_HTTP_OK = int(HTTPStatus.OK)

_HEALTH_PATHS: dict[PortalName, str] = {
    "pfactory": "/api/health",
    "aifactory": "/api/health",
    "tfactory": "/api/health",
    "cfactory": "/health",
}

_PROTECTED_READ_PATHS: dict[PortalName, str] = {
    "pfactory": "/api/mcp-stdio/projects",
    "aifactory": "/api/mcp-stdio/projects",
    "tfactory": "/api/mcp-stdio/projects",
    "cfactory": "/api/workitems",
}


@dataclass(frozen=True)
class DoctorOutcome:
    """Result of `factory doctor`."""

    exit_code: int
    outcome: Literal["ok", "rejected", "unknown"]
    payload: dict[str, Any]
    lines: tuple[str, ...]


def run_doctor(  # noqa: PLR0912, PLR0915
    *,
    ctx: RuntimeContext | None = None,
) -> DoctorOutcome:
    """Check URL, key source, key kind, health version, and protected read on each portal."""
    rt = ctx or RuntimeContext()
    secrets = collect_known_secrets(env=rt.env, home=rt.home)
    portal_reports: dict[str, Any] = {}
    lines: list[str] = []
    failed = False

    for portal in PORTAL_NAMES:
        try:
            key = resolve_portal_key(portal, env=rt.env, home=rt.home)
        except ValueError as exc:
            return DoctorOutcome(
                exit_code=EXIT_PRECONDITION,
                outcome="rejected",
                payload={"outcome": "rejected", "detail": str(exc)},
                lines=(f"error: {exc}",),
            )
        key_source = key.source if key else "none"
        key_kind = key.kind if key else "none"

        try:
            url = resolve_portal_url(
                portal,
                env=rt.env,
                home=rt.home,
                config_path=rt.config_path,
            )
            transport = PortalTransport(
                url,
                token=key.value if key else None,
                secrets=secrets,
                timeout=10.0,
            )
            url_error: str | None = None
        except (InputRejectedError, ValueError) as exc:
            url = "<invalid>"
            transport = None
            url_error = redact_text(str(exc), secrets)

        health_version = "unreachable"
        health_failed = True
        if transport is not None:
            try:
                h_resp = transport.request("GET", _HEALTH_PATHS[portal])
                if h_resp.status == _HTTP_OK and h_resp.is_json and isinstance(h_resp.data, dict):
                    raw_ver = str(h_resp.data.get("version") or h_resp.data.get("status") or "ok")
                    health_version = redact_text(raw_ver, secrets)
                    health_failed = False
                elif h_resp.status == _HTTP_OK:
                    health_version = "reachable (not JSON)"
                    health_failed = False
                elif h_resp.status > 0:
                    health_version = f"http-{h_resp.status}"
            except InputRejectedError:
                health_version = "blocked"

        read_status = "unreachable"
        if transport is not None and key is not None:
            try:
                r_resp = transport.request("GET", _PROTECTED_READ_PATHS[portal])
                if r_resp.status == _HTTP_OK:
                    read_status = "ok"
                elif r_resp.status in (401, 403):
                    read_status = "denied"
            except InputRejectedError:
                read_status = "unreachable"
        if read_status != "ok" or health_failed:
            failed = True

        notes: list[str] = []
        if key_kind == "legacy":
            notes.append(
                "legacy key can only dry-run submit (live submit requires an acw_ user key)"
            )
        if portal == "cfactory":
            notes.append("CFactory key sees the whole tenant")
        if url_error:
            notes.append(f"url error: {url_error}")

        safe_url = redact_text(url, secrets)
        portal_reports[portal] = {
            "url": safe_url,
            "key_source": key_source,
            "key_kind": key_kind,
            "health_version": health_version,
            "protected_read": read_status,
            "notes": notes,
        }

        note_suffix = f" ({'; '.join(notes)})" if notes else ""
        lines.append(
            redact_text(
                f"{portal}: url={safe_url} key_source={key_source} key_kind={key_kind} "
                f"health={health_version} read={read_status}{note_suffix}",
                secrets,
            )
        )

    lines.append(
        "note: a legacy key can only dry-run submit; a CFactory key sees the whole tenant."
    )
    payload = redact_structure(
        {
            "outcome": "rejected" if failed else "ok",
            "portals": portal_reports,
            "notes": [
                "a legacy key can only dry-run submit",
                "a CFactory key sees the whole tenant",
            ],
        },
        secrets,
    )
    return DoctorOutcome(
        exit_code=EXIT_REJECTED if failed else EXIT_OK,
        outcome="rejected" if failed else "ok",
        payload=payload,
        lines=tuple(lines),
    )
