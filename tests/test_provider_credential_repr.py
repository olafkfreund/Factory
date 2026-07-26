"""Guard: no credential-bearing provider field may render in ``repr()``.

Factory#372. ``shared/factory-github/providers/gitlab_provider.py`` declared
``_token: str | None = None`` on a ``@dataclass``, so the generated ``__repr__``
rendered the GitLab PAT verbatim::

    GitLabProvider(_base_url='https://gitlab.com', _token='glpat-SUPERSECRET123')

A dataclass ``__repr__`` is not a debug-only surface: it is what a traceback
frame prints for a local, what ``logger.debug(f"{provider}")`` writes, and what
an error-reporting payload serialises. A reprable credential field therefore
puts a live token into logs, crash reports and third-party error sinks.

This file carries two guards:

* :func:`test_no_credential_field_is_reprable` is the fleet-wide one. It parses
  every module under ``shared/factory-github/providers/`` with :mod:`ast` -- no
  imports, no third-party dependencies -- and fails if any dataclass field whose
  name looks like a credential lacks ``repr=False``. A provider added tomorrow is
  covered automatically; nobody has to remember to extend this test.
* :func:`test_live_providers_do_not_leak_credentials` is the behavioural proof:
  it constructs the real providers with a fake token and asserts the token is
  absent from ``repr()`` and ``str()``, while the auth header is still built.

To reintroduce the bug is to make the first test red -- that is the point.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROVIDERS_DIR = _REPO_ROOT / "shared" / "factory-github" / "providers"

# A field is credential-bearing when any underscore-separated segment of its name
# is one of these. Segment matching (not substring) keeps `_project_dir` and
# `path` out while still catching `_pat`, `_token`, `client_secret`, `api_key`.
# Deliberately fail-closed: a false positive costs one `repr=False` on a field
# that did not need it, a false negative costs a credential in the logs.
_CREDENTIAL_SEGMENTS = frozenset(
    {
        "apikey",
        "auth",
        "credential",
        "credentials",
        "key",
        "keys",
        "passwd",
        "password",
        "pat",
        "pats",
        "secret",
        "secrets",
        "token",
        "tokens",
    }
)


def _is_credential_name(name: str) -> bool:
    return bool(_CREDENTIAL_SEGMENTS & set(name.lower().strip("_").split("_")))


def _is_dataclass(node: ast.ClassDef) -> bool:
    """True when the class carries an ``@dataclass`` / ``@dataclass(...)``."""
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name == "dataclass":
            return True
    return False


def _repr_is_disabled(default: ast.expr | None) -> bool:
    """True when the field default is ``field(..., repr=False)``."""
    if not isinstance(default, ast.Call):
        return False
    func = default.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name != "field":
        return False
    return any(
        kw.arg == "repr" and isinstance(kw.value, ast.Constant) and kw.value.value is False
        for kw in default.keywords
    )


def _provider_modules() -> list[Path]:
    return sorted(p for p in _PROVIDERS_DIR.glob("*.py"))


def test_providers_dir_is_present() -> None:
    """Fail loudly rather than vacuously passing if the tree moves."""
    assert _provider_modules(), f"no provider modules found under {_PROVIDERS_DIR}"


def test_no_credential_field_is_reprable() -> None:
    """Every credential-named dataclass field must set ``repr=False``."""
    offenders: list[str] = []

    for module in _provider_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_dataclass(node):
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
                    continue
                name = stmt.target.id
                if _is_credential_name(name) and not _repr_is_disabled(stmt.value):
                    offenders.append(
                        f"{module.name}:{stmt.lineno} {node.name}.{name} "
                        f"-- credential-bearing field renders in __repr__; "
                        f"use `field(default=..., repr=False)`"
                    )

    assert not offenders, "credential-bearing fields reachable via repr():\n  " + "\n  ".join(
        offenders
    )


def test_live_providers_do_not_leak_credentials() -> None:
    """Construct the real providers and prove the secret is absent from repr/str."""
    pytest.importorskip("httpx", reason="provider modules import httpx at module scope")
    # The canonical tree lives under a hyphenated directory, so it cannot be a
    # package path: import it via sys.path, which forces these imports to be
    # function-local (hence the PLC0415 waivers).
    sys.path.insert(0, str(_REPO_ROOT / "shared" / "factory-github"))
    try:
        from providers.azure_devops_provider import (  # type: ignore[import-not-found]  # noqa: PLC0415
            AzureDevOpsProvider,
        )
        from providers.github_provider import (  # type: ignore[import-not-found]  # noqa: PLC0415
            GitHubProvider,
        )
        from providers.gitlab_provider import (  # type: ignore[import-not-found]  # noqa: PLC0415
            GitLabProvider,
        )
    finally:
        sys.path.pop(0)

    secret = "glpat-SUPERSECRET123"  # noqa: S105 - fake, this is the leak probe
    gitlab = GitLabProvider(_repo="group/repo", _token=secret)
    assert secret not in repr(gitlab)
    assert secret not in str(gitlab)
    # repr=False hides the field from rendering only -- the value must still be
    # usable, or the "fix" would have broken authentication.
    assert gitlab._headers["PRIVATE-TOKEN"] == secret

    pat = "azdo-SUPERSECRET456"
    azure = AzureDevOpsProvider(_repo="repo", _pat=pat)
    assert pat not in repr(azure)
    assert pat not in str(azure)
    assert azure._headers["Authorization"].startswith("Basic ")

    # GitHubProvider holds no credential of its own (the gh CLI owns auth); this
    # asserts it stays that way rather than that something is hidden.
    github = GitHubProvider(_repo="owner/repo")
    assert not [f for f in github.__dataclass_fields__ if _is_credential_name(f)]
