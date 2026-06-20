#!/usr/bin/env python3
"""Validate the Factory hub Backstage catalog + TechDocs wiring.

Thin shim over the canonical validator in ``scripts/validate_catalog.py`` (the
single source of truth shared by the hub and every Factory-family product repo).
It validates the catalog rooted at the repository root (this file lives in
``scripts/``, so the catalog is one level up).

Run via ``catalog-validate`` in the Nix devShell, or directly:
    python scripts/validate-catalog.py
Exits non-zero on any failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_catalog import validate

if __name__ == "__main__":
    raise SystemExit(validate(Path(__file__).resolve().parents[1]))
