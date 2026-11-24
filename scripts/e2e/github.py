"""Minimal GitHub repo client; token is read only for a request."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts.e2e.config import GITHUB_TOKEN_FILE


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: object) -> Request | None:
        return None


class GitHub:
    def __init__(
        self, token_file: Path = GITHUB_TOKEN_FILE, open_url: Callable[..., Any] | None = None
    ) -> None:
        self.token_file = token_file
        self.open_url = open_url or build_opener(NoRedirect).open

    def __repr__(self) -> str:
        return "GitHub()"

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not path.startswith("/") or "//" in path or not path.startswith("/repos/"):
            raise ValueError("invalid GitHub path")
        try:
            token = self.token_file.read_text(encoding="utf-8").strip()
            request = Request(
                f"https://api.github.com{path}",
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                method=method,
            )
            with self.open_url(request, timeout=20) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except HTTPError:
            raise
        except (URLError, OSError, ValueError) as exc:
            raise RuntimeError(f"GitHub request failed ({type(exc).__name__})") from None

    def set_topics(self, full_name: str, topics: list[str]) -> dict[str, Any]:
        if not full_name.startswith("Freundcloud/"):
            raise ValueError("unsafe owner")
        return self.request("PUT", f"/repos/{full_name}/topics", {"names": topics})
