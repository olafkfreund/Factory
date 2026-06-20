#!/usr/bin/env python3
"""RFC-0015 §4 D3 extension-registry loader (reference core).

A pure, dependency-free library that loads the hub extension manifest
(``apis/extension-registry.json``) and validates each entry's ``category`` and
``effect`` against the fixed enums, so the pipeline is discoverable, toggleable,
and auditable from one place. Mirrors the pure + self-test style of
``scripts/cost_router_core.py`` (load + ``_check`` self-tests, no external
harness).

The registry describes every Factory stage, gate, connector, and runtime with:

  - ``category`` in {intake, plan, review, gate, runtime, connector, observe}
  - ``effect``   in {read-only, read-write}
  - ``enabled``  — operator-gating state (RFC-0014: a gated runtime is
    ``enabled=false`` until an operator opts in)
  - ``owner_service`` — which service owns the extension

Run directly to execute the self-tests: ``python3 scripts/extension_registry.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast

# Fixed vocabularies (RFC-0015 §4 D3). An entry with an unknown category/effect is
# a registry error — the manifest is the audit surface, so it must not carry
# uncategorizable rows.
CATEGORIES = ("intake", "plan", "review", "gate", "runtime", "connector", "observe")
EFFECTS = ("read-only", "read-write")

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "apis" / "extension-registry.json"


# Loose by design (total=False): this is the JSON I/O boundary, so unknown keys
# are ignored downstream and every declared key is optional.
class Extension(TypedDict, total=False):
    """One extension-registry row (RFC-0015 §4 D3)."""

    name: str
    category: str
    effect: str
    enabled: bool
    description: str
    owner_service: str


def load_registry(path: str | Path = REGISTRY_PATH) -> list[Extension]:
    """Load the hub extension registry and return its ``extensions`` list.

    Accepts either the full manifest (with a top-level ``extensions`` array) or a
    bare list, so callers may pass a slimmed test fixture.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("extensions", []) if isinstance(data, dict) else data
    out: list[Extension] = []
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                # JSON gives an untyped dict at this I/O boundary; the row is a
                # loose Extension (total=False, unknown keys ignored downstream).
                out.append(cast("Extension", entry))
    return out


def validate_entry(entry: Extension) -> list[str]:
    """Return a list of validation errors for one extension entry (empty => valid).

    Checks the required name plus the ``category``/``effect`` enum membership. A
    missing/unknown value is an error, not a silent pass.
    """
    errors: list[str] = []
    name = entry.get("name")
    if not name:
        errors.append("entry missing 'name'")
    label = name or "<unnamed>"
    category = entry.get("category")
    if category not in CATEGORIES:
        errors.append(f"{label}: invalid category {category!r} (expected one of {CATEGORIES})")
    effect = entry.get("effect")
    if effect not in EFFECTS:
        errors.append(f"{label}: invalid effect {effect!r} (expected one of {EFFECTS})")
    return errors


def validate_registry(extensions: list[Extension]) -> list[str]:
    """Validate every entry; returns the flattened error list (empty => all valid).

    Also flags duplicate names — the registry is keyed by name for discovery, so a
    duplicate would shadow an extension in any name-indexed view.
    """
    errors: list[str] = []
    seen: set[str] = set()
    for entry in extensions:
        errors.extend(validate_entry(entry))
        name = entry.get("name")
        if name:
            if name in seen:
                errors.append(f"{name}: duplicate name")
            seen.add(name)
    return errors


def by_category(extensions: list[Extension], category: str) -> list[Extension]:
    """All extensions in one category (e.g. the runtimes, the gates)."""
    return [e for e in extensions if e.get("category") == category]


def enabled_only(extensions: list[Extension]) -> list[Extension]:
    """The extensions an operator has turned on (gated-off entries excluded)."""
    return [e for e in extensions if e.get("enabled") is True]


# --------------------------------------------------------------------------- #
# Self-tests (run: python3 scripts/extension_registry.py)
# --------------------------------------------------------------------------- #
def _check(ok: bool, detail: str) -> None:
    # Self-tests use a raising checker rather than `assert` so the module stays
    # ruff-clean (S101) for the new-file ratchet, and stays meaningful under -O.
    if not ok:
        raise AssertionError(detail)


def _fixture() -> list[Extension]:
    return [
        {"name": "intake", "category": "intake", "effect": "read-only", "enabled": True},
        {"name": "claude", "category": "runtime", "effect": "read-write", "enabled": True},
        {"name": "codex", "category": "runtime", "effect": "read-write", "enabled": False},
        {"name": "val-gate", "category": "gate", "effect": "read-only", "enabled": True},
    ]


def _test_validate_ok() -> None:
    _check(not validate_registry(_fixture()), "clean fixture must validate")
    _check(not validate_entry(_fixture()[0]), "single clean entry must validate")


def _test_validate_rejects() -> None:
    bad_cat: Extension = {"name": "x", "category": "bogus", "effect": "read-only"}
    _check(bool(validate_entry(bad_cat)), "unknown category must be rejected")
    bad_eff: Extension = {"name": "y", "category": "gate", "effect": "read"}
    _check(bool(validate_entry(bad_eff)), "unknown effect must be rejected")
    no_name: Extension = {"category": "gate", "effect": "read-only"}
    _check(any("name" in e for e in validate_entry(no_name)), "missing name must be rejected")
    dup: Extension = {"name": "claude", "category": "runtime", "effect": "read-write"}
    dupes = [*_fixture(), dup]
    found_dupe = any("duplicate" in e for e in validate_registry(dupes))
    _check(found_dupe, "duplicate name must be flagged")


def _test_filters() -> None:
    fx = _fixture()
    expected_runtimes = 2
    expected_enabled = 3
    runtimes = by_category(fx, "runtime")
    _check(len(runtimes) == expected_runtimes, f"two runtimes in fixture, got {len(runtimes)}")
    on = enabled_only(fx)
    _check(len(on) == expected_enabled, f"three enabled in fixture, got {len(on)}")
    gates = by_category(fx, "gate")
    _check(all(e.get("category") == "gate" for e in gates), "by_category filters")


def _test_real_registry() -> None:
    # The shipped hub manifest must itself be valid and non-empty.
    exts = load_registry()
    _check(len(exts) > 0, "shipped registry must be non-empty")
    errors = validate_registry(exts)
    _check(errors == [], f"shipped registry must validate, got {errors}")
    _check(len(by_category(exts, "runtime")) > 0, "shipped registry must declare runtimes")


def _test() -> None:
    _test_validate_ok()
    _test_validate_rejects()
    _test_filters()
    _test_real_registry()
    print("extension_registry self-tests: 4 groups passed")  # noqa: T201  # CLI self-test report sink


if __name__ == "__main__":
    _test()
