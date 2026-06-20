#!/usr/bin/env python3
"""Validate this product repo's Backstage catalog + TechDocs wiring.

Thin shim over the canonical validator that lives in the Factory hub at
``scripts/validate_catalog.py`` (the single source of truth shared by the hub and
every Factory-family product repo: PFactory / AIFactory / TFactory / CFactory).
It validates the catalog rooted at this product directory (this file lives in
``<product>/scripts/``, so the catalog is one level up).

Within the Factory hub mono-repo the canonical module is importable directly.
When a product repo is checked out standalone, vendor ``validate_catalog.py``
next to this shim (or onto ``PYTHONPATH``) so the import still resolves.

Run via ``catalog-validate`` in the Nix devShell, or directly:
    python scripts/validate-catalog.py
Exits non-zero on any failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
# Prefer a vendored copy next to this shim; fall back to the Factory hub's
# scripts/ dir when running inside the Factory mono-repo.
for _candidate in (_HERE.parent, _HERE.parents[3] / "scripts"):
    if (_candidate / "validate_catalog.py").exists():
        sys.path.insert(0, str(_candidate))
        break

from validate_catalog import validate  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(validate(_HERE.parents[1]))
