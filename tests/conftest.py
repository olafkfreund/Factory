#!/usr/bin/env python3
"""Put the hub's ``scripts/`` and ``shared/factory-github/`` on ``sys.path``.

pytest imports ``conftest.py`` before collecting, so test modules can import a
gate directly (``import check_factory_github_drift as gate``) instead of each
repeating the same nine-line bootstrap.

Extracted 2026-07-28: that bootstrap was copy-pasted into four test files and
tripped the jscpd clone budget (Factory#403). Doing it once here removes the
duplication rather than obfuscating it, which is what the budget exists to push
toward.

Extended 2026-08-15 (Factory#721) with ``shared/factory-github``, for the same
reason and after the same signal: a second test of the vendored provider layer
would have re-pasted the bootstrap and the budget caught it again.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT / "scripts", _REPO_ROOT / "shared/factory-github"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
