"""Factory CLI surface with an injected subprocess runner."""

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from scripts.e2e.config import HOSTS, KEY_FILES
from scripts.e2e.guard import Guard, GuardRefusalError

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

    def call(self, service: str, kind: str, identity: str, verb: str, *args: str) -> dict[str, Any]:
        if any(
            ID_SHAPED.search(arg)
            or arg.startswith(("--config", "--api-url", "--token", "--key", "--home"))
            for arg in (verb, *args)
        ):
            raise GuardRefusalError("caller supplied another target")

        def action() -> dict[str, Any]:
            with tempfile.TemporaryDirectory(prefix="factory-e2e-") as home:
                env = {
                    "PATH": os.environ.get("PATH", os.defpath),
                    "HOME": home,
                    "XDG_CONFIG_HOME": home,
                    **{f"{name.upper()}_API_URL": url for name, url in HOSTS.items()},
                }
                if service in self.key_files:
                    env[f"{service.upper()}_API_TOKEN_FILE"] = str(self.key_files[service])
                result = self.run(
                    ["factory", verb, identity, *args, "--json"],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=env,
                )
            if result.returncode:
                raise RuntimeError(f"factory CLI failed with exit {result.returncode}")
            return cast(dict[str, Any], json.loads(result.stdout))

        return cast(dict[str, Any], self.guard.mutate(service, kind, identity, action))
