#!/usr/bin/env python3
"""Self-test for the RFC-0019 agent-skills manifest contract.

Behaviour-locking tests for `apis/agent-skills-manifest.schema.json` and the
reference instances under `apis/examples/agent-skills/`:

1. The schema is itself a valid Draft 2020-12 schema.
2. Every committed example validates - the four service manifests and the
   CFactory fleet aggregate.
3. The fleet aggregate is not stale: each `services[]` entry equals the service
   manifest it was folded in from (envelope + fetch metadata aside).
4. The guardrails actually bite: a wrong `kind`, a skill missing its invocation,
   an invocation whose payload does not match its `kind`, and a remote MCP
   transport without an endpoint are all rejected.

Skips cleanly when jsonschema is unavailable (e.g. outside the Nix devShell);
`scripts/validate_task_contract.py` has the same optional dependency.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import contract_schema as cs
import pytest
from contract_schema import jsonschema

_SCHEMA_FILE = "agent-skills-manifest.schema.json"
_SERVICES = ("pfactory", "aifactory", "tfactory", "cfactory")

# Metadata the aggregator adds when folding a service manifest into the fleet
# document; everything else must survive the fold byte-for-byte.
_FOLD_ONLY_KEYS = ("manifest_url", "fetched_at", "reachable")


def _example(name: str) -> dict[str, Any]:
    return cs.example("agent-skills", name, suffix=".index.json")


def _validator() -> Any:
    return cs.validator_for(cs.schema(_SCHEMA_FILE))


def _errors(doc: dict[str, Any]) -> list[str]:
    return cs.error_messages(cs.schema(_SCHEMA_FILE), doc)


def test_schema_is_valid_draft_2020_12() -> None:
    jsonschema.Draft202012Validator.check_schema(cs.schema(_SCHEMA_FILE))


@pytest.mark.parametrize("name", _SERVICES)
def test_service_examples_validate(name: str) -> None:
    doc = _example(name)
    assert doc["kind"] == "service"
    assert doc["service"]["name"] == name
    assert _errors(doc) == []


def test_fleet_example_validates() -> None:
    doc = _example("fleet")
    assert doc["kind"] == "fleet"
    assert [s["service"]["name"] for s in doc["services"]] == list(_SERVICES)
    assert _errors(doc) == []


def test_manifest_is_declared_readable_without_auth() -> None:
    """RFC-0019 section 3.4: agents enumerate before they authenticate."""
    for name in _SERVICES:
        assert _example(name)["auth"]["manifest"] == "none", name


@pytest.mark.parametrize("name", _SERVICES)
def test_fleet_aggregate_is_not_stale(name: str) -> None:
    """Each fleet entry must equal the service manifest it aggregates."""
    entry = next(s for s in _example("fleet")["services"] if s["service"]["name"] == name)
    folded = {k: v for k, v in entry.items() if k not in _FOLD_ONLY_KEYS}
    origin = {k: v for k, v in _example(name).items() if k not in ("schema_version", "kind")}
    assert folded == origin, (
        f"fleet.index.json is stale for {name}: regenerate the entry from {name}.index.json"
    )


def test_unavailable_sibling_is_accepted_beside_the_fetched_ones() -> None:
    """A service the aggregator has never reached is announced, not omitted."""
    doc = deepcopy(_example("fleet"))
    dropped = next(s for s in doc["services"] if s["service"]["name"] == "tfactory")
    doc["services"] = [s for s in doc["services"] if s["service"]["name"] != "tfactory"]
    doc["unavailable"] = [
        {
            "name": "tfactory",
            "title": "TFactory",
            "manifest_url": dropped["manifest_url"],
            "reason": "unreachable",
            "checked_at": "2026-07-25T09:05:00Z",
        }
    ]
    assert _errors(doc) == []


def test_unavailable_entry_needs_a_name_and_a_manifest_url() -> None:
    doc = deepcopy(_example("fleet"))
    doc["unavailable"] = [{"reason": "unreachable"}]
    assert _errors(doc) != []


def test_unavailable_entry_may_not_smuggle_extra_fields() -> None:
    """The thin shape is the point: no invented body, no leaked internals."""
    doc = deepcopy(_example("fleet"))
    doc["unavailable"] = [
        {
            "name": "tfactory",
            "manifest_url": "https://tfactory.example.com/.well-known/agent-skills/index.json",
            "upstream_token": "nope",
        }
    ]
    assert _errors(doc) != []


def test_a_body_less_service_entry_is_still_rejected() -> None:
    """`unavailable[]` is the ONLY place a manifest-less service may appear -
    `services[]` stays strictly conformant so consumers need no defensive checks."""
    doc = deepcopy(_example("fleet"))
    doc["services"].append({"name": "tfactory", "manifest_url": "/x", "reachable": False})
    assert _errors(doc) != []


def test_unknown_kind_is_rejected() -> None:
    doc = deepcopy(_example("aifactory"))
    doc["kind"] = "partner"
    assert _errors(doc) != []


def test_skill_without_invocation_is_rejected() -> None:
    doc = deepcopy(_example("aifactory"))
    del doc["skills"][0]["invocation"]
    assert any("invocation" in m for m in _errors(doc))


def test_invocation_payload_must_match_its_kind() -> None:
    """A `rest` invocation carrying a slash command is not a valid REST call."""
    doc = deepcopy(_example("aifactory"))
    doc["skills"][0]["invocation"] = {"kind": "rest", "command": "/handover"}
    assert _errors(doc) != []


def test_remote_mcp_transport_requires_an_endpoint() -> None:
    doc = deepcopy(_example("aifactory"))
    del doc["mcp"]["endpoint"]
    assert any("endpoint" in m for m in _errors(doc))
    # ...while a stdio server legitimately has none.
    doc["mcp"]["transport"] = "stdio"
    assert _errors(doc) == []


def test_unknown_top_level_field_is_rejected() -> None:
    """`unevaluatedProperties: false` must survive the kind-dispatching allOf."""
    doc = deepcopy(_example("cfactory"))
    doc["secrets"] = {"token": "nope"}
    assert _errors(doc) != []
