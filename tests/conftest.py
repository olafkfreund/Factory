#!/usr/bin/env python3
"""Put the hub's ``scripts/`` on ``sys.path`` for every test in this directory.

pytest imports ``conftest.py`` before collecting, so test modules can import a
gate directly (``import check_factory_github_drift as gate``) instead of each
repeating the same nine-line bootstrap.

Extracted 2026-07-28: that bootstrap was copy-pasted into four test files and
tripped the jscpd clone budget (Factory#403). Doing it once here removes the
duplication rather than obfuscating it, which is what the budget exists to push
toward.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = str(_REPO_ROOT / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
