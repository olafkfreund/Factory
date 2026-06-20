#!/usr/bin/env python3
"""Self-test for the canonical catalog validator (scripts/validate_catalog.py).

Behaviour-locking tests for the consolidated single source of truth shared by
the Factory hub and the per-product `product-catalogs/*/scripts/` shims. The
module under test is `scripts/validate_catalog.py`. They
build tiny throwaway catalogs in a tmp dir so they exercise the real logic
without depending on the live catalog-info.yaml files.

Skips cleanly when PyYAML is unavailable (e.g. outside the Nix devShell).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The canonical validator lives in <repo>/scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

pytest.importorskip("yaml")

import validate_catalog as vc

_MIN_CATALOG = """\
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: widget
spec:
  owner: team-a
  providesApis:
    - widget-api
  consumesApis:
    - factory-completion-events
---
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
  name: widget-api
spec:
  owner: team-a
  type: openapi
  definition:
    $text: ./openapi.yaml
"""

_OPENAPI = """\
openapi: "3.0.0"
info:
  title: Widget
  version: "1.0.0"
paths: {}
"""


def _write(root: Path, catalog: str, *, openapi: str | None = _OPENAPI) -> None:
    (root / "catalog-info.yaml").write_text(catalog)
    if openapi is not None:
        (root / "openapi.yaml").write_text(openapi)


def test_valid_catalog_passes(tmp_path: Path) -> None:
    _write(tmp_path, _MIN_CATALOG)
    assert vc.validate(tmp_path) == 0


def test_cross_repo_api_is_accepted(tmp_path: Path) -> None:
    # `factory-completion-events` is not defined locally but must be accepted as
    # a known cross-repo entity (the superset behaviour from the product copies).
    _write(tmp_path, _MIN_CATALOG)
    errors: list[str] = []
    vc._check_catalog(tmp_path, errors)
    assert errors == []


def test_unknown_api_reference_fails(tmp_path: Path) -> None:
    catalog = _MIN_CATALOG.replace("factory-completion-events", "does-not-exist")
    _write(tmp_path, catalog)
    assert vc.validate(tmp_path) == 1


def test_missing_owner_fails(tmp_path: Path) -> None:
    catalog = _MIN_CATALOG.replace("  owner: team-a\n  providesApis:", "  providesApis:")
    _write(tmp_path, catalog)
    assert vc.validate(tmp_path) == 1


def test_missing_openapi_target_fails(tmp_path: Path) -> None:
    _write(tmp_path, _MIN_CATALOG, openapi=None)
    assert vc.validate(tmp_path) == 1


def test_non_openapi_3_fails(tmp_path: Path) -> None:
    _write(tmp_path, _MIN_CATALOG, openapi='openapi: "2.0"\ninfo: {}\n')
    assert vc.validate(tmp_path) == 1


def test_mkdocs_optional_when_absent(tmp_path: Path) -> None:
    # No mkdocs.yml present: TechDocs check is skipped, catalog still validates.
    _write(tmp_path, _MIN_CATALOG)
    assert not (tmp_path / "mkdocs.yml").exists()
    assert vc.validate(tmp_path) == 0


def test_mkdocs_missing_nav_target_fails(tmp_path: Path) -> None:
    _write(tmp_path, _MIN_CATALOG)
    (tmp_path / "mkdocs.yml").write_text("docs_dir: docs\nnav:\n  - Home: index.md\n")
    (tmp_path / "docs").mkdir()
    # index.md intentionally absent -> failure.
    assert vc.validate(tmp_path) == 1


def test_mkdocs_present_and_valid_passes(tmp_path: Path) -> None:
    _write(tmp_path, _MIN_CATALOG)
    (tmp_path / "mkdocs.yml").write_text("docs_dir: docs\nnav:\n  - Home: index.md\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text("# Home\n")
    assert vc.validate(tmp_path) == 0


def test_real_product_catalogs_validate() -> None:
    # End-to-end against the actual checked-in product catalogs (regression lock).
    repo_root = Path(__file__).resolve().parents[1]
    products = sorted((repo_root / "product-catalogs").glob("*/catalog-info.yaml"))
    assert products, "expected product catalogs to exist"
    for catalog in products:
        assert vc.validate(catalog.parent) == 0, f"{catalog.parent.name} failed"
