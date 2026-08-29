"""Shared helpers for the nix_provisioner test modules.

Extracted because `_flake` and `_has_attr` were copied between
test_nix_provisioner_jest.py and test_nix_provisioner_language.py, which the
jscpd clone budget caught as net-new duplication (the budget only ratchets
DOWN, so a paste here fails every subsequent PR until it is removed).

`_has_attr` matters more than its size suggests: matching a bare attr name is a
substring trap in this file's subject matter. `pkgs.python` matches the
legitimate `pkgs.python313`, and `pkgs.dotnet` matches `pkgs.dotnet-sdk`. One
correct implementation beats two that drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from nix_provisioner import generate_flake


def flake_for(**env: object) -> str:
    """Render a flake from a manifest, defaulting the provisioning block."""
    env.setdefault("provisioning", {"method": "nix", "generated": True})
    rendered: str = generate_flake(env)
    return rendered


def has_attr(flake: str, attr: str) -> bool:
    """Word-boundary attr match.

    A plain `"pkgs.python" in flake` matches the legitimate `pkgs.python313`,
    and `"pkgs.dotnet"` matches `pkgs.dotnet-sdk`. Both mistakes were made on
    this component this week, in both directions -- a false pass and a false
    fail. `[\\w-]` excludes the digits AND the hyphen, so `pkgs.dotnet` does not
    match `pkgs.dotnet-sdk` while `pkgs.dotnet-sdk` still matches itself.
    """
    return re.search(rf"pkgs\.{re.escape(attr)}(?![\w-])", flake) is not None
