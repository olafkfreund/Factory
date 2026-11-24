"""Factory CLI surface with an injected subprocess runner."""

import json
import subprocess
from collections.abc import Callable

from scripts.e2e.guard import Guard


class CLI:
    def __init__(
        self, guard: Guard, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    ) -> None:
        self.guard = guard
        self.run = run

    def call(self, kind: str, identity: str, *args: str) -> dict:
        def action() -> dict:
            result = self.run(
                ["factory", *args, "--json"], capture_output=True, text=True, check=False
            )
            if result.returncode:
                raise RuntimeError(f"factory CLI failed with exit {result.returncode}")
            return json.loads(result.stdout)

        return self.guard.mutate(kind, identity, action)
