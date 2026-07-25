"""Shared helpers for the ``apis/`` contract-schema tests.

Every contract test here does the same three things: load a JSON Schema out of
``apis/``, load example instances beside it, and assert on the validation errors
those examples produce. Keeping that boilerplate in one place is not just tidiness
-- the repo enforces a jscpd clone budget that only ever ratchets DOWN, so a
second copy of the loader block makes the next contract test impossible to add
without raising a ceiling that is meant to fall.

``jsonschema`` is passed in rather than imported here on purpose: the test modules
acquire it via ``pytest.importorskip`` so the suite skips cleanly outside the Nix
devShell, and importing it at module scope would defeat that.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
APIS = REPO_ROOT / "apis"


def load_json(path: Path) -> dict[str, Any]:
    """Parse one JSON document."""
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def schema(filename: str) -> dict[str, Any]:
    """Load a schema by filename from ``apis/``."""
    return load_json(APIS / filename)


def example(subdir: str, name: str, suffix: str = ".json") -> dict[str, Any]:
    """Load ``apis/examples/<subdir>/<name><suffix>``."""
    return load_json(APIS / "examples" / subdir / f"{name}{suffix}")


def validator_for(jsonschema: Any, doc_schema: dict[str, Any]) -> Any:
    """A Draft 2020-12 validator bound to ``doc_schema``."""
    return jsonschema.Draft202012Validator(doc_schema)


def error_messages(jsonschema: Any, doc_schema: dict[str, Any], doc: dict[str, Any]) -> list[str]:
    """Validation error messages for ``doc``, empty when it conforms."""
    return [e.message for e in validator_for(jsonschema, doc_schema).iter_errors(doc)]
