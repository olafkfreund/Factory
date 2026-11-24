"""Minimal GitHub repo client; token is read only for a request."""

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.e2e.config import GITHUB_TOKEN_FILE


class GitHub:
    def __init__(self, token_file: Path = GITHUB_TOKEN_FILE, open_url=urlopen) -> None:
        self.token_file = token_file
        self.open_url = open_url

    def __repr__(self) -> str:
        return "GitHub()"

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
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
                return json.load(response)
        except (HTTPError, URLError, OSError, ValueError) as exc:
            raise RuntimeError(f"GitHub request failed ({type(exc).__name__})") from None

    def set_topics(self, full_name: str, topics: list[str]) -> dict:
        if not full_name.startswith("Freundcloud/"):
            raise ValueError("unsafe owner")
        return self.request("PUT", f"/repos/{full_name}/topics", {"names": topics})
