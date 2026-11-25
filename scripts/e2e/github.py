"""Minimal GitHub repo client; token is read only for a request."""

import base64
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts.e2e.config import GITHUB_TOKEN_FILE

HTTP_NOT_FOUND = 404
SHA_LENGTH = 40


HTTP_FORBIDDEN = 403


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: object) -> Request | None:
        return None


def _git_auth_env(token: str) -> dict[str, str]:
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        **os.environ,
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "http.extraheader",
        "GIT_CONFIG_VALUE_0": f"Authorization: basic {basic}",
        "GIT_CONFIG_KEY_1": "credential.helper",
        "GIT_CONFIG_VALUE_1": "",
        "GIT_TERMINAL_PROMPT": "0",
    }


RATE_LIMIT_MAX_WAIT_S = 900


def _rate_limit_wait(exc: HTTPError) -> float | None:
    """Seconds until the core limit resets, or None when this is not a rate limit."""
    headers = exc.headers
    if headers is None or exc.code not in {403, 429} or headers.get("X-RateLimit-Remaining") != "0":
        return None
    try:
        wait = int(headers.get("X-RateLimit-Reset", "")) - time.time() + 1
    except ValueError:
        return None
    return min(max(wait, 1.0), RATE_LIMIT_MAX_WAIT_S)


class GitHub:
    def __init__(
        self, token_file: Path = GITHUB_TOKEN_FILE, open_url: Callable[..., Any] | None = None
    ) -> None:
        self.token_file = token_file
        self.open_url = open_url or build_opener(NoRedirect).open
        self.sleep: Callable[[float], None] = time.sleep

    def __repr__(self) -> str:
        return "GitHub()"

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            return self._request(method, path, payload)
        except HTTPError as exc:
            wait = _rate_limit_wait(exc)
            if wait is None:
                raise
            # A rate-limited request was not executed, so one retry after reset is safe.
            self.sleep(wait)
            return self._request(method, path, payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        if (
            not path.startswith("/")
            or "//" in path
            or not (path.startswith("/repos/olafkfreund/") or path == "/user/repos")
        ):
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
        if not full_name.startswith("olafkfreund/"):
            raise ValueError("unsafe owner")
        return cast(
            dict[str, Any], self.request("PUT", f"/repos/{full_name}/topics", {"names": topics})
        )

    def create_repo(self, name: str) -> dict[str, Any]:
        # GitHub REST: POST /user/repos (personal account, owner decision 2026-11-24);
        # Guard.create_repo writes intent first.
        return cast(
            dict[str, Any],
            self.request(
                "POST",
                "/user/repos",
                {
                    "name": name,
                    "private": False,
                    "auto_init": False,
                },  # Factory#3890: PF/TF cannot clone private repos yet (owner: public for now)
            ),
        )

    def read_repo(self, full_name: str) -> dict[str, Any] | None:
        if not full_name.startswith("olafkfreund/"):
            raise ValueError("unsafe owner")
        try:
            return cast(dict[str, Any], self.request("GET", f"/repos/{full_name}"))
        except HTTPError as exc:
            if exc.code == HTTP_NOT_FOUND:
                return None
            raise

    def delete_repo(self, full_name: str) -> object:
        if not full_name.startswith("olafkfreund/"):
            raise ValueError("unsafe owner")
        return self.request("DELETE", f"/repos/{full_name}")

    def pull_requests(self, full_name: str) -> list[dict[str, Any]]:
        if not full_name.startswith("olafkfreund/"):
            raise ValueError("unsafe owner")
        return cast(
            list[dict[str, Any]], self.request("GET", f"/repos/{full_name}/pulls?state=all")
        )

    def pull_request(self, full_name: str) -> dict[str, Any]:
        pulls = self.pull_requests(full_name)
        if len(pulls) != 1:
            raise RuntimeError("expected exactly one PR in campaign repo")
        return cast(
            dict[str, Any], self.request("GET", f"/repos/{full_name}/pulls/{pulls[0]['number']}")
        )

    def pull_files(self, full_name: str, number: int) -> list[dict[str, Any]]:
        if not full_name.startswith("olafkfreund/") or number < 1:
            raise ValueError("unsafe PR")
        # shared/factory-github/gh_client.py:887-906 uses this REST path.
        return cast(
            list[dict[str, Any]],
            self.request("GET", f"/repos/{full_name}/pulls/{number}/files?per_page=100"),
        )

    def check_runs(self, full_name: str, sha: str) -> dict[str, Any]:
        if not full_name.startswith("olafkfreund/") or len(sha) != SHA_LENGTH:
            raise ValueError("unsafe check target")
        return cast(
            dict[str, Any], self.request("GET", f"/repos/{full_name}/commits/{sha}/check-runs")
        )

    def protect_main(self, full_name: str) -> dict[str, Any]:
        if not full_name.startswith("olafkfreund/"):
            raise ValueError("unsafe owner")
        # GitHub REST PUT /repos/{owner}/{repo}/branches/{branch}/protection.
        # shortcut: the olafkfreund org is on the Free plan, where private repos get 403
        # "Upgrade to GitHub Pro" for branch protection. Recorded as unavailable rather than
        # failing S1; upgrade when the org plan changes or the test repos go public.
        try:
            return self._protect(full_name)
        except HTTPError as exc:
            if exc.code == HTTP_FORBIDDEN:
                return {"unavailable": "branch protection needs a paid plan for private repos"}
            raise

    def _protect(self, full_name: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.request(
                "PUT",
                f"/repos/{full_name}/branches/main/protection",
                {
                    "required_status_checks": {"strict": True, "contexts": ["tests"]},
                    "enforce_admins": False,
                    "required_pull_request_reviews": None,
                    "restrictions": None,
                },
            ),
        )

    def main_protection(self, full_name: str) -> dict[str, Any]:
        if not full_name.startswith("olafkfreund/"):
            raise ValueError("unsafe owner")
        return cast(
            dict[str, Any], self.request("GET", f"/repos/{full_name}/branches/main/protection")
        )

    def create_issue(self, full_name: str, title: str) -> dict[str, Any]:
        if not full_name.startswith("olafkfreund/"):
            raise ValueError("unsafe owner")
        return cast(
            dict[str, Any], self.request("POST", f"/repos/{full_name}/issues", {"title": title})
        )

    def push_starter(self, starter: Path, triple: Path, full_name: str, work: Path) -> None:
        if not full_name.startswith("olafkfreund/"):
            raise ValueError("unsafe owner")
        token = self.token_file.read_text(encoding="utf-8").strip()
        if not token:
            raise RuntimeError("GitHub token is empty")
        shutil.copytree(starter, work, dirs_exist_ok=True)
        workflow = work / ".github" / "workflows" / "tests.yml"
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(
            "name: tests\non: [push, pull_request]\njobs:\n  tests:\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - uses: actions/setup-python@v5\n"
            "        with:\n          python-version: '3.12'\n"
            "      - run: python -m pip install pytest\n"
            "      - run: python -m pytest -q\n",
            encoding="utf-8",
        )
        env = _git_auth_env(token)
        git_executable = shutil.which("git")
        if git_executable is None:
            raise RuntimeError("git unavailable")

        def git(*args: str) -> None:
            subprocess.run(  # noqa: S603
                [git_executable, *args],
                cwd=work,
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        git("init", "-b", "main")
        git("add", ".")
        git(
            "-c",
            "user.name=Factory E2E",
            "-c",
            "user.email=e2e@freundcloud.com",
            "commit",
            "-m",
            "test: seed e2e fixture",
        )
        for stage in ("intent", "spec", "plan"):
            source = next((triple / stage).glob("*.md"))
            destination = work / stage / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            approved = source.read_text(encoding="utf-8")
            if not approved.startswith("---\nstatus: approved\n"):
                raise RuntimeError("fixture artifact lacks approved frontmatter")
            destination.write_text(approved.replace("status: approved", "status: draft", 1))
            git("add", str(destination.relative_to(work)))
            git(
                "-c",
                "user.name=Factory E2E",
                "-c",
                "user.email=e2e@freundcloud.com",
                "commit",
                "-m",
                f"docs({stage}): draft e2e fixture",
            )
            destination.write_text(approved)
            git("add", str(destination.relative_to(work)))
            git(
                "-c",
                "user.name=Factory E2E",
                "-c",
                "user.email=e2e@freundcloud.com",
                "commit",
                "-m",
                f"docs({stage}): approve e2e fixture",
            )
        shutil.copy2(triple / "execution.json", work / "execution.json")
        git("add", "execution.json")
        git(
            "-c",
            "user.name=Factory E2E",
            "-c",
            "user.email=e2e@freundcloud.com",
            "commit",
            "-m",
            "test: pin e2e execution profile",
        )
        url = f"https://github.com/{full_name}.git"
        git("push", url, "HEAD:main")
        # `factory submit` reads the triple from this checkout and needs an `origin`
        # remote and origin/main; the URL carries no credential (auth is header-only).
        git("remote", "add", "origin", url)
        git("update-ref", "refs/remotes/origin/main", "HEAD")

    def fetch_commit(self, full_name: str, sha: str, work: Path) -> None:
        if (
            not full_name.startswith("olafkfreund/")
            or len(sha) != SHA_LENGTH
            or any(c not in "0123456789abcdef" for c in sha.lower())
        ):
            raise ValueError("unsafe repository or SHA")
        token = self.token_file.read_text(encoding="utf-8").strip()
        git_executable = shutil.which("git")
        if not token or git_executable is None:
            raise RuntimeError("GitHub credential or git unavailable")
        env = _git_auth_env(token)
        subprocess.run(  # noqa: S603
            [git_executable, "fetch", f"https://github.com/{full_name}.git", sha],
            cwd=work,
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
