"""Factory CLI surface with an injected subprocess runner."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from scripts.e2e.config import HOSTS, KEY_FILES
from scripts.e2e.guard import Guard, GuardRefusalError

CLI_ROOT = Path(__file__).resolve().parents[3] / "shared" / "factory-cli"
CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")


def isolated_env(home: str, key_files: dict[str, Path]) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": home,
        "XDG_CONFIG_HOME": home,
        "PYTHONPATH": str(CLI_ROOT),
        **{f"{name.upper()}_API_URL": url for name, url in HOSTS.items()},
        **{f"{name.upper()}_API_TOKEN_FILE": str(path) for name, path in key_files.items()},
    }
    if CA_BUNDLE.is_file():
        env["SSL_CERT_FILE"] = str(CA_BUNDLE)
    return env


ID_SHAPED = re.compile(
    r"(?:\b(?:af|pf|tf):\S+|\b(?:task|card)-[\w-]+|\b[A-Z]+-\d+\b|\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b|\b\d+\b)",
    re.I,
)


class CLI:
    def __init__(
        self,
        guard: Guard,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        key_files: dict[str, Path] | None = None,
    ) -> None:
        self.guard = guard
        self.run = run
        self.key_files = KEY_FILES if key_files is None else key_files

    def execute(
        self, args: list[str], *, cwd: Path | None = None, allow_rejected: bool = False
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="factory-e2e-") as home:
            env = isolated_env(home, self.key_files)
            uv = shutil.which("uv")
            if uv is None:
                raise RuntimeError("uv unavailable")
            result = self.run(
                [
                    uv,
                    "run",
                    "--no-project",
                    "--with-editable",
                    str(CLI_ROOT),
                    "python",
                    "-m",
                    "factory_cli",
                    *args,
                ],
                capture_output=True,
                text=True,
                check=False,
                env=env,
                cwd=cwd,
            )
        if result.returncode and not allow_rejected:
            # The CLI already redacts keys; the caller redacts again before persisting.
            lines = (result.stderr or result.stdout or "").strip().splitlines()
            # Drop uv's own build chatter so the CLI's message survives the length cap.
            tail = [ln for ln in lines if not ln.lstrip().startswith(("Built ", "Installed "))][-3:]
            raise RuntimeError(
                f"factory CLI {args[0] if args else ''} failed with exit {result.returncode}: "
                + " | ".join(tail)[:600]
            )
        output = result.stderr if result.returncode else result.stdout
        try:
            data = cast(dict[str, Any], json.loads(output))
        except json.JSONDecodeError:
            data = dict(line.split(": ", 1) for line in output.splitlines() if ": " in line)
        if result.returncode:
            data["outcome"] = "rejected"
        return data

    def call(self, service: str, kind: str, identity: str, verb: str, *args: str) -> dict[str, Any]:
        if any(
            ID_SHAPED.search(arg)
            or arg.startswith(("--config", "--api-url", "--token", "--key", "--home"))
            for arg in (verb, *args)
        ):
            raise GuardRefusalError("caller supplied another target")

        def action() -> dict[str, Any]:
            return self.execute([verb, identity, *args])

        return cast(dict[str, Any], self.guard.mutate(service, kind, identity, action))
