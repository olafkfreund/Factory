#!/usr/bin/env python3
"""Validate this product repo's Backstage catalog + TechDocs wiring.

Drop-in validator for a Factory-family product repo (PFactory · AIFactory ·
TFactory · CFactory). No network, no Backstage install required.

Checks:
  * catalog-info.yaml parses and every entity has the required envelope
    (apiVersion / kind / metadata.name / spec.owner).
  * providesApis / consumesApis reference an API defined in THIS file, or a
    documented cross-repo entity (the shared `factory-completion-events` contract
    and the sibling product `*-api` entities, all owned by other repos and
    resolved globally by Backstage).
  * Every API entity's `$text` target exists and parses for its declared type:
    openapi → OpenAPI 3.x · asyncapi → AsyncAPI 2.x/3.x · mcp → non-empty markdown.
  * If mkdocs.yml is present, its nav targets all exist under the docs dir.

Run via `catalog-validate` in the Nix devShell, or `python scripts/validate-catalog.py`.
Exits non-zero on any failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    sys.exit("PyYAML not available — run inside the Nix devShell (`nix develop`).")

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []

# Cross-repo entities owned by the Factory program repo / sibling products.
# Backstage resolves these globally; this validator must not flag them as missing.
EXTERNAL_APIS = {
    "factory-completion-events",
    "pfactory-api",
    "aifactory-api",
    "tfactory-api",
    "cfactory-api",
}


def err(msg: str) -> None:
    errors.append(msg)


def load_catalog() -> list[dict]:
    path = ROOT / "catalog-info.yaml"
    docs = [d for d in yaml.safe_load_all(path.read_text()) if d]
    api_names = {d["metadata"]["name"] for d in docs if d.get("kind") == "API"}
    known_apis = api_names | EXTERNAL_APIS

    for d in docs:
        for key in ("apiVersion", "kind", "metadata", "spec"):
            if key not in d:
                err(f"catalog entity missing '{key}': {d!r:.80}")
        meta, spec = d.get("metadata", {}), d.get("spec", {})
        if "name" not in meta:
            err("catalog entity missing metadata.name")
        if "owner" not in spec:
            err(f"{meta.get('name', '?')}: spec.owner is required")

        for rel in ("providesApis", "consumesApis"):
            for ref in spec.get(rel, []):
                if ref not in known_apis:
                    err(f"{meta.get('name')}: {rel} -> '{ref}' not defined here "
                        f"and not a known cross-repo API")

        if d.get("kind") == "API":
            api_type = spec.get("type", "")
            definition = spec.get("definition")
            if isinstance(definition, dict) and "$text" in definition:
                target = (ROOT / definition["$text"]).resolve()
                if not target.exists():
                    err(f"{meta['name']}: $text -> {definition['$text']} missing")
                elif api_type == "openapi":
                    api_doc = yaml.safe_load(target.read_text())
                    if not str(api_doc.get("openapi", "")).startswith("3"):
                        err(f"{target.name}: not an OpenAPI 3.x document")
                elif api_type == "asyncapi":
                    api_doc = yaml.safe_load(target.read_text())
                    if not str(api_doc.get("asyncapi", "")).startswith(("2", "3")):
                        err(f"{target.name}: not an AsyncAPI 2.x/3.x document")
                elif api_type == "mcp":
                    if not target.read_text().strip():
                        err(f"{target.name}: empty MCP definition")
                # other types: existence of the $text target is sufficient
            elif not definition:
                err(f"{meta['name']}: API spec.definition is required")
    return docs


def check_mkdocs() -> None:
    mk_path = ROOT / "mkdocs.yml"
    if not mk_path.exists():
        return  # TechDocs is optional for a product repo
    mk = yaml.safe_load(mk_path.read_text())
    docs_dir = ROOT / mk.get("docs_dir", "docs")
    if not docs_dir.is_dir():
        err(f"mkdocs docs_dir '{mk.get('docs_dir')}' does not exist")
        return

    def walk(nav) -> None:
        if isinstance(nav, str):
            if nav.endswith(".md") and not (docs_dir / nav).exists():
                err(f"mkdocs nav -> {nav} missing under {docs_dir.name}/")
        elif isinstance(nav, list):
            for item in nav:
                walk(item)
        elif isinstance(nav, dict):
            for v in nav.values():
                walk(v)

    walk(mk.get("nav", []))


def main() -> int:
    docs = load_catalog()
    check_mkdocs()

    if errors:
        print("✗ catalog validation failed:")
        for e in errors:
            print(f"   - {e}")
        return 1

    kinds = ", ".join(f"{d['kind']}:{d['metadata']['name']}" for d in docs)
    print(f"✓ catalog-info.yaml: {len(docs)} entities ({kinds})")
    n_api = sum(
        1 for d in docs
        if d.get("kind") == "API"
        and isinstance(d.get("spec", {}).get("definition"), dict)
        and "$text" in d["spec"]["definition"]
    )
    print(f"✓ {n_api} API definition(s) resolve and parse for their type"
          if n_api else "• no API entity with a $text definition")
    print("✓ mkdocs.yml nav targets all exist" if (ROOT / "mkdocs.yml").exists()
          else "• no mkdocs.yml — TechDocs check skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
