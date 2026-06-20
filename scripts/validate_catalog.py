#!/usr/bin/env python3
"""Canonical offline validator for a Backstage catalog + TechDocs wiring.

Single source of truth for the Factory hub and every Factory-family product repo
(PFactory / AIFactory / TFactory / CFactory). The hub `scripts/validate-catalog.py`
and the per-product `product-catalogs/*/scripts/validate-catalog.py` are thin
shims that import :func:`validate` from this module with their own catalog root.

No network, no Backstage install required.

Checks:
  * catalog-info.yaml parses and every entity has the required envelope
    (apiVersion / kind / metadata.name / spec.owner).
  * providesApis / consumesApis reference an API defined in the same catalog, or
    a documented cross-repo entity (the shared `factory-completion-events`
    contract and the sibling product `*-api` entities, owned by other repos and
    resolved globally by Backstage).
  * Every API entity's `$text` target exists and parses for its declared type:
    openapi -> OpenAPI 3.x; asyncapi -> AsyncAPI 2.x/3.x; mcp -> non-empty
    markdown. Other declared types only require the `$text` target to exist.
  * If mkdocs.yml is present, its nav targets all exist under the docs dir.
    (TechDocs is optional for a product repo; the hub always ships mkdocs.yml.)

Run via `catalog-validate` in the Nix devShell, or directly:
    python scripts/validate_catalog.py [--root <catalog dir>]
Exits non-zero on any failure.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    sys.exit("PyYAML not available - run inside the Nix devShell (`nix develop`).")

# Cross-repo entities owned by the Factory program repo / sibling products.
# Backstage resolves these globally; this validator must not flag them as
# missing. They are harmless for the hub catalog, which defines them itself.
EXTERNAL_APIS = frozenset(
    {
        "factory-completion-events",
        "pfactory-api",
        "aifactory-api",
        "tfactory-api",
        "cfactory-api",
    }
)


def _check_catalog(root: Path, errors: list[str]) -> list[dict]:
    path = root / "catalog-info.yaml"
    docs = [d for d in yaml.safe_load_all(path.read_text()) if d]
    api_names = {d["metadata"]["name"] for d in docs if d.get("kind") == "API"}
    known_apis = api_names | EXTERNAL_APIS

    for d in docs:
        for key in ("apiVersion", "kind", "metadata", "spec"):
            if key not in d:
                errors.append(f"catalog entity missing '{key}': {d!r:.80}")
        meta, spec = d.get("metadata", {}), d.get("spec", {})
        if "name" not in meta:
            errors.append("catalog entity missing metadata.name")
        if "owner" not in spec:
            errors.append(f"{meta.get('name', '?')}: spec.owner is required")

        for rel in ("providesApis", "consumesApis"):
            for ref in spec.get(rel, []):
                if ref not in known_apis:
                    errors.append(
                        f"{meta.get('name')}: {rel} -> '{ref}' not defined here "
                        f"and not a known cross-repo API"
                    )

        if d.get("kind") == "API":
            _check_api_definition(root, meta, spec, errors)
    return docs


def _check_api_definition(root: Path, meta: dict, spec: dict, errors: list[str]) -> None:
    api_type = spec.get("type", "")
    definition = spec.get("definition")
    if not (isinstance(definition, dict) and "$text" in definition):
        if not definition:
            errors.append(f"{meta['name']}: API spec.definition is required")
        return

    target = (root / definition["$text"]).resolve()
    if not target.exists():
        errors.append(f"{meta['name']}: $text -> {definition['$text']} missing")
        return

    if api_type == "openapi":
        api_doc = yaml.safe_load(target.read_text())
        if not str(api_doc.get("openapi", "")).startswith("3"):
            errors.append(f"{target.name}: not an OpenAPI 3.x document")
    elif api_type == "asyncapi":
        api_doc = yaml.safe_load(target.read_text())
        if not str(api_doc.get("asyncapi", "")).startswith(("2", "3")):
            errors.append(f"{target.name}: not an AsyncAPI 2.x/3.x document")
    elif api_type == "mcp":
        if not target.read_text().strip():
            errors.append(f"{target.name}: empty MCP definition")
    # other types: existence of the $text target is sufficient


def _check_mkdocs(root: Path, errors: list[str]) -> None:
    mk_path = root / "mkdocs.yml"
    if not mk_path.exists():
        return  # TechDocs is optional for a product repo
    mk = yaml.safe_load(mk_path.read_text())
    docs_dir = root / mk.get("docs_dir", "docs")
    if not docs_dir.is_dir():
        errors.append(f"mkdocs docs_dir '{mk.get('docs_dir')}' does not exist")
        return

    def walk(nav: object) -> None:
        if isinstance(nav, str):
            if nav.endswith(".md") and not (docs_dir / nav).exists():
                errors.append(f"mkdocs nav -> {nav} missing under {docs_dir.name}/")
        elif isinstance(nav, list):
            for item in nav:
                walk(item)
        elif isinstance(nav, dict):
            for v in nav.values():
                walk(v)

    walk(mk.get("nav", []))


def validate(root: Path) -> int:
    """Validate the catalog rooted at *root*. Return 0 on success, 1 on failure."""
    errors: list[str] = []
    docs = _check_catalog(root, errors)
    _check_mkdocs(root, errors)

    if errors:
        print("X catalog validation failed:")  # noqa: T201
        for e in errors:
            print(f"   - {e}")  # noqa: T201
        return 1

    kinds = ", ".join(f"{d['kind']}:{d['metadata']['name']}" for d in docs)
    print(f"OK catalog-info.yaml: {len(docs)} entities ({kinds})")  # noqa: T201
    n_api = sum(
        1
        for d in docs
        if d.get("kind") == "API"
        and isinstance(d.get("spec", {}).get("definition"), dict)
        and "$text" in d["spec"]["definition"]
    )
    print(  # noqa: T201
        f"OK {n_api} API definition(s) resolve and parse for their type"
        if n_api
        else "- no API entity with a $text definition"
    )
    print(  # noqa: T201
        "OK mkdocs.yml nav targets all exist"
        if (root / "mkdocs.yml").exists()
        else "- no mkdocs.yml - TechDocs check skipped"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="catalog directory holding catalog-info.yaml (default: current dir)",
    )
    args = parser.parse_args(argv)
    root = (args.root or Path.cwd()).resolve()
    return validate(root)


if __name__ == "__main__":
    raise SystemExit(main())
