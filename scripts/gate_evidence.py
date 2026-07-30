#!/usr/bin/env python3
"""The fragment a byte-comparison gate's verdict was derived from.

Factory#504. A gate that reports a verdict without the thing it read is a claim
nobody can falsify, and the direction that costs most is the confident PASS: a
comparison that matches for the wrong reason prints nothing, so nothing gets
investigated. For a byte-exact gate the "raw fragment" is the file content, and
its citable form is a digest plus a length — anyone can re-run ``sha256sum`` and
check the claim in one command.

One function, in one place, because the three hub drift gates
(``check_verification_core_drift``, ``check_factory_github_drift``,
``check_factory_ui_drift``) all need exactly this and three copies is what the
clone budget in ``scripts/check_jscpd_budget.py`` exists to stop.

Import-safe for the consumers: every service repo runs those gates out of a full
hub checkout (``python factory-hub-main/scripts/check_*.py``), so this sibling
resolves on ``sys.path`` with no workflow change and no pin bump.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def digest(path: Path) -> str:
    """A short, re-derivable citation of the bytes at *path*.

    Truncated to 12 hex characters: this is a human-readable citation printed
    next to a verdict, not the comparison itself. The gates compare full byte
    strings; nothing decides anything on this value.
    """
    if not path.is_file():
        return "absent"
    data = path.read_bytes()
    return f"sha256:{sha256(data).hexdigest()[:12]} {len(data)}B"
