"""HTTP transport and URL safety enforcement for the Factory CLI."""

from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from typing import IO, Any

from factory_cli._vendor.factory_common.client_errors import InputRejectedError
from factory_cli._vendor.factory_common.http import DEFAULT_USER_AGENT
from factory_cli._vendor.factory_common.secrets import PLACEHOLDER, redact as redact_patterns
from factory_cli._vendor.factory_common.url_safety import (
    _NoRedirect,
    assert_safe_outbound_url,
    build_no_redirect_opener,
)

_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_SERVER_ERROR_MIN = int(HTTPStatus.INTERNAL_SERVER_ERROR)

# Matches URLs with userinfo (both `scheme://user:pass@host` and `scheme://user@host`)
# as well as SCP-style `user@host:path` when username is not `git`.
_URL_USERINFO_RE = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<userinfo>[^/@\s]+)@(?P<host>[^\s/]+)"
)


def redact_url_userinfo(text: str) -> str:
    """Strip any userinfo (including username-only) from URLs inside *text*."""
    return _URL_USERINFO_RE.sub(
        lambda m: f"{m.group('scheme')}{PLACEHOLDER}@{m.group('host')}",
        text,
    )


def redact_text(text: str, secrets: Sequence[str] = ()) -> str:
    """Redact loaded secret values, URL userinfo, and canonical secret patterns from *text*."""
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, PLACEHOLDER)
    cleaned = redact_url_userinfo(cleaned)
    return str(redact_patterns(cleaned))


def redact_structure(value: Any, secrets: Sequence[str] = ()) -> Any:
    """Recursively redact strings in both dict keys and values, lists, and tuples."""
    if isinstance(value, str):
        return redact_text(value, secrets)
    if isinstance(value, dict):
        return {
            (redact_text(k, secrets) if isinstance(k, str) else k): redact_structure(v, secrets)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_structure(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_structure(item, secrets) for item in value)
    return value


def _resolves_exclusively_to_loopback(host: str, port: int) -> bool:
    """Return True only when *host* is a loopback literal or resolves solely to loopback IPs."""
    stripped = host.strip()
    try:
        return ipaddress.ip_address(stripped).is_loopback
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(stripped, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise InputRejectedError(f"cannot resolve host {host!r}") from exc
    if not infos:
        return False
    for info in infos:
        addr = str(info[4][0]).split("%", 1)[0]
        if not ipaddress.ip_address(addr).is_loopback:
            return False
    return True


def validate_cli_url(url: str, *, allow_query: bool = False) -> str:
    """Enforce the CLI URL policy: https or loopback http, no userinfo, no fragment."""
    parsed = urllib.parse.urlparse(url)
    if parsed.username is not None or parsed.password is not None or "@" in (parsed.netloc or ""):
        raise InputRejectedError("URL userinfo is not allowed")
    if parsed.scheme not in ("http", "https"):
        raise InputRejectedError(f"unsupported URL scheme {parsed.scheme!r} (only http/https)")
    if parsed.fragment:
        raise InputRejectedError("URL fragment is not allowed")
    if not allow_query and parsed.query:
        raise InputRejectedError("base URL query string is not allowed")
    host = parsed.hostname
    if not host:
        raise InputRejectedError("URL has no host")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise InputRejectedError("URL has invalid port") from exc
    if parsed.scheme == "http" and not _resolves_exclusively_to_loopback(host, port):
        raise InputRejectedError(
            f"plain HTTP is only allowed for loopback addresses (got {host!r})"
        )
    assert_safe_outbound_url(url, allow_private=True)
    return url


def quote_single_segment(segment: str, *, label: str = "identifier") -> str:
    """Validate and URL-quote a single non-empty path segment with safe=''."""
    cleaned = segment.strip()
    if not cleaned or cleaned in (".", "..") or "/" in cleaned:
        raise InputRejectedError(f"invalid {label}: {segment!r}")
    return urllib.parse.quote(cleaned, safe="")


@dataclass(frozen=True)
class TransportResponse:
    """Decoded HTTP response from a portal call."""

    status: int
    data: Any
    raw_text: str
    is_json: bool = False
    network_error: str | None = None
    after_send: bool = False


def extract_safe_detail(data: Any, raw_text: str, secrets: Sequence[str] = ()) -> str:
    """Extract a redacted single-line detail message from a portal error body."""
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, str) and detail.strip():
            return redact_text(detail.strip(), secrets)[:300]
        if isinstance(detail, (list, dict)):
            return redact_text(json.dumps(detail), secrets)[:300]
        error = data.get("error")
        if isinstance(error, str) and error.strip():
            return redact_text(error.strip(), secrets)[:300]
    cleaned = redact_text(raw_text.strip(), secrets)[:300]
    return cleaned or "request failed"


class _SendTrackingHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection that records when request bytes are sent on a connected socket."""

    def __init__(self, *args: Any, tracker: list[bool], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tracker = tracker

    def send(self, data: Any) -> None:
        if self.sock is None:
            if self.auto_open:
                self.connect()
            else:
                raise http.client.NotConnected
        self._tracker[0] = True
        super().send(data)


class _SendTrackingHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection that records when request bytes are sent on a connected socket."""

    def __init__(self, *args: Any, tracker: list[bool], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tracker = tracker

    def send(self, data: Any) -> None:
        if self.sock is None:
            if self.auto_open:
                self.connect()
            else:
                raise http.client.NotConnected
        self._tracker[0] = True
        super().send(data)


class _SendTrackingHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, tracker: list[bool]) -> None:
        super().__init__()
        self._tracker = tracker

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(
            lambda host, **kw: _SendTrackingHTTPConnection(host, tracker=self._tracker, **kw),
            req,
        )


class _SendTrackingHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, tracker: list[bool]) -> None:
        super().__init__()
        self._tracker = tracker

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        ctx = getattr(self, "_context", None)
        return self.do_open(
            lambda host, **kw: _SendTrackingHTTPSConnection(host, tracker=self._tracker, **kw),
            req,
            context=ctx,
        )


def _build_tracked_opener(
    *,
    is_loopback_http: bool,
    tracker: list[bool],
) -> urllib.request.OpenerDirector:
    """Build a no-redirect opener that tracks socket sends and ignores env proxies on loopback."""
    # Call build_no_redirect_opener() from factory_common for parity, and construct
    # the opener with our send-tracking handlers + _NoRedirect.
    _ = build_no_redirect_opener()
    handlers: list[urllib.request.BaseHandler] = [
        _NoRedirect(),
        _SendTrackingHTTPHandler(tracker),
        _SendTrackingHTTPSHandler(tracker),
    ]
    if is_loopback_http:
        handlers.insert(0, urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


class PortalTransport:
    """No-redirect urllib transport with CLI URL policy and secret redaction."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        secrets: Sequence[str] = (),
        timeout: float = 30.0,
    ) -> None:
        cleaned_base = base_url.strip().rstrip("/")
        self.base_url = validate_cli_url(cleaned_base, allow_query=False)
        self._is_loopback_http = urllib.parse.urlparse(self.base_url).scheme == "http"
        self.token = token
        all_secrets = list(secrets)
        if token and token not in all_secrets:
            all_secrets.append(token)
        self.secrets: tuple[str, ...] = tuple(all_secrets)
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        params: Mapping[str, str | int | None] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> TransportResponse:
        """Issue one HTTP request without following redirects or retrying POSTs."""
        rel = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{rel}"
        if params:
            clean_params = {k: str(v) for k, v in params.items() if v is not None}
            if clean_params:
                url = f"{url}?{urllib.parse.urlencode(clean_params)}"
        validate_cli_url(url, allow_query=True)

        payload = json.dumps(dict(body)).encode("utf-8") if body is not None else None
        req_headers: dict[str, str] = {"User-Agent": DEFAULT_USER_AGENT}
        if payload is not None:
            req_headers["Content-Type"] = "application/json"
        if self.token:
            req_headers["Authorization"] = f"Bearer {self.token}"
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(  # noqa: S310 - URL validated by validate_cli_url above
            url,
            data=payload,
            method=method.upper(),
            headers=req_headers,
        )
        sent_tracker = [False]
        opener = _build_tracked_opener(
            is_loopback_http=self._is_loopback_http,
            tracker=sent_tracker,
        )
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                raw_bytes = _read_all_response_bytes(resp)
                status = int(resp.getcode())
        except urllib.error.HTTPError as exc:
            if exc.code in _REDIRECT_CODES:
                raise InputRejectedError(
                    redact_text(f"redirect refused (HTTP {exc.code})", self.secrets)
                ) from exc
            try:
                err_bytes = exc.read()
            except Exception:  # noqa: BLE001
                err_bytes = b""
            raw_text = redact_text(err_bytes.decode("utf-8", errors="replace"), self.secrets)
            parsed_data, is_json = _parse_json(raw_text)
            return TransportResponse(
                status=exc.code,
                data=parsed_data,
                raw_text=raw_text,
                is_json=is_json,
                after_send=sent_tracker[0] and exc.code >= _SERVER_ERROR_MIN,
            )
        except (http.client.HTTPException, TimeoutError, ConnectionError, OSError) as exc:
            raw_exc = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            msg = redact_text(str(raw_exc or exc) or type(exc).__name__, self.secrets)
            return TransportResponse(
                status=0,
                data={},
                raw_text=msg,
                is_json=False,
                network_error=msg,
                after_send=sent_tracker[0],
            )

        raw_text = redact_text(raw_bytes.decode("utf-8", errors="replace"), self.secrets)
        parsed_data, is_json = _parse_json(raw_text)
        return TransportResponse(
            status=status,
            data=parsed_data,
            raw_text=raw_text,
            is_json=is_json,
            after_send=True,
        )


def _read_all_response_bytes(resp: IO[bytes]) -> bytes:
    """Read response body and raise IncompleteRead if Content-Length was not satisfied."""
    raw = resp.read()
    headers = getattr(resp, "headers", None)
    if headers is not None:
        cl_header = headers.get("Content-Length")
        if cl_header is not None:
            try:
                expected = int(cl_header)
            except ValueError:
                expected = -1
            if expected >= 0 and len(raw) < expected:
                raise http.client.IncompleteRead(raw, expected - len(raw))
    return raw


def _parse_json(raw_text: str) -> tuple[Any, bool]:
    stripped = raw_text.strip()
    if not stripped:
        return {}, False
    if stripped.startswith(("{", "[")):
        try:
            return json.loads(stripped), True
        except json.JSONDecodeError:
            return {"raw": raw_text}, False
    return {"raw": raw_text}, False
