#!/usr/bin/env python3
"""Validate apis/task-contract.schema.json and exercise the RFC-0007 access block.

Repo-idiomatic self-test (mirrors scripts/verification_gate.py): run directly to
check the contract schema is a valid JSON Schema and that the additive
``$defs.access`` block (RFC-0007) is optional, accepts a well-formed access
declaration, and rejects malformed ones. No external test harness needed:

    python scripts/validate_task_contract.py
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "apis" / "task-contract.schema.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _base() -> dict:
    """A minimal, otherwise-valid v2 contract (one phase, one subtask)."""
    return {
        "contract_version": "2",
        "feature": "demo",
        "workflow_type": "feature",
        "phases": [{"phase": 1, "name": "p", "subtasks": [{"id": "t1", "description": "d"}]}],
    }


def _errors(validator: Draft202012Validator, doc: dict) -> list[str]:
    return [e.message for e in validator.iter_errors(doc)]


if __name__ == "__main__":
    schema = load_schema()
    Draft202012Validator.check_schema(schema)  # the schema is itself valid
    v = Draft202012Validator(schema)

    # access is optional — a contract without it validates.
    assert "access" not in schema.get("required", []), "access must not be required"
    assert _errors(v, _base()) == [], "minimal contract (no access) should validate"

    # a well-formed access block validates (A: machine-native, D: un-automatable).
    ok = dict(
        _base(),
        access={
            "requirements": [
                {
                    "resource": "sandbox-aws",
                    "auth_class": "A-machine-native",
                    "bootstrap": "none",
                    "credential_ref": None,
                },
                {
                    "resource": "keycloak",
                    "auth_class": "D-un-automatable",
                    "bootstrap": "human",
                    "curated": False,
                    "human_approval": {
                        "approved_by": "op",
                        "approved_at": "2026-06-16",
                        "scope": "test realm",
                    },
                    "mvp_note": "push-approval MFA, human-driven",
                },
            ]
        },
    )
    assert _errors(v, ok) == [], f"well-formed access should validate, got {_errors(v, ok)}"

    # malformed access is rejected.
    bad_enum = dict(
        _base(),
        access={"requirements": [{"resource": "x", "auth_class": "E-nope", "bootstrap": "none"}]},
    )
    assert _errors(v, bad_enum), "unknown auth_class must be rejected"

    missing_required = dict(
        _base(), access={"requirements": [{"resource": "x", "auth_class": "A-machine-native"}]}
    )  # no bootstrap
    assert _errors(v, missing_required), "missing bootstrap must be rejected"

    unknown_prop = dict(
        _base(),
        access={
            "requirements": [
                {"resource": "x", "auth_class": "A-machine-native", "bootstrap": "none", "junk": 1}
            ]
        },
    )
    assert _errors(v, unknown_prop), "unknown property must be rejected"

    empty_block = dict(_base(), access={})  # requirements is required
    assert _errors(v, empty_block), "access without requirements must be rejected"

    # --- RFC-0005 environment manifest --------------------------------------
    # environment is optional — a contract without it validates.
    assert "environment" not in schema.get("required", []), "environment must not be required"

    # a well-formed Nix-provisioned environment (browser lane) validates.
    env_ok = dict(
        _base(),
        environment={
            "language": "python",
            "toolchain": {"python": "3.13"},
            "system_packages": ["chromium"],
            "build_commands": ["true"],
            "verify_commands": ["pytest -q", "npx playwright test"],
            "serve_command": "python -m uvicorn app:app --port 8099",
            "provisioning": {"method": "nix", "ref": "flake.nix", "generated": True},
            "network": "restricted",
            "proof": {"verify": ["python --version", "chromium --version"]},
        },
    )
    assert _errors(v, env_ok) == [], (
        f"well-formed environment should validate, got {_errors(v, env_ok)}"
    )

    # malformed environment is rejected.
    bad_method = dict(_base(), environment={"provisioning": {"method": "conda"}})
    assert _errors(v, bad_method), "unknown provisioning.method must be rejected"

    missing_method = dict(_base(), environment={"provisioning": {"ref": "flake.nix"}})
    assert _errors(v, missing_method), "provisioning without method must be rejected"

    bad_network = dict(_base(), environment={"network": "open"})
    assert _errors(v, bad_network), "unknown network posture must be rejected"

    env_unknown_prop = dict(_base(), environment={"junk": 1})
    assert _errors(v, env_unknown_prop), "unknown environment property must be rejected"

    print(
        "OK: task-contract schema valid; RFC-0007 $defs.access + "
        "RFC-0005 $defs.environment optional + constraints enforced."
    )
