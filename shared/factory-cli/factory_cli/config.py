"""Portal URL and API key resolution for the Factory CLI."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PortalName = Literal["pfactory", "aifactory", "tfactory", "cfactory"]

PORTAL_NAMES: tuple[PortalName, ...] = (
    "pfactory",
    "aifactory",
    "tfactory",
    "cfactory",
)

DEFAULT_URLS: dict[PortalName, str] = {
    "pfactory": "https://pfactory.freundcloud.org.uk",
    "aifactory": "https://aifactory.freundcloud.org.uk",
    "tfactory": "https://tfactory.freundcloud.org.uk",
    "cfactory": "https://cfactory-mcp.freundcloud.org.uk",
}

URL_ENV_VARS: dict[PortalName, str] = {
    "pfactory": "PFACTORY_API_URL",
    "aifactory": "AIFACTORY_API_URL",
    "tfactory": "TFACTORY_API_URL",
    "cfactory": "CFACTORY_API_URL",
}

DEFAULT_CONFIG_REL_PATH = Path(".config") / "factory" / "config.toml"


@dataclass(frozen=True)
class RuntimeContext:
    """Optional runtime overrides for working directory, environment, and paths."""

    cwd: Path | None = None
    env: dict[str, str] | None = None
    home: Path | None = None
    config_path: Path | None = None


@dataclass(frozen=True)
class ResolvedKey:
    """Resolved portal key and non-secret metadata about its source."""

    portal: PortalName
    value: str
    source: str
    kind: Literal["acw", "legacy"]


def _resolve_config_path(config_path: Path | None = None, home: Path | None = None) -> Path:
    if config_path is not None:
        raw = str(config_path)
        if raw.startswith("~/") and home is not None:
            return home.expanduser() / raw[2:]
        return config_path.expanduser()
    home_dir = (home or Path.home()).expanduser()
    return home_dir / DEFAULT_CONFIG_REL_PATH


def _read_config_urls(
    config_path: Path | None = None,
    *,
    home: Path | None = None,
) -> dict[str, str]:
    path = _resolve_config_path(config_path, home)
    if not path.is_file():
        return {}
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot read config at {path}: {exc}") from exc
    portals = raw.get("portals")
    if not isinstance(portals, dict):
        return {}
    urls: dict[str, str] = {}
    for name, entry in portals.items():
        if isinstance(entry, dict) and isinstance(entry.get("url"), str):
            urls[str(name).lower()] = entry["url"].strip().rstrip("/")
    return urls


def resolve_portal_url(
    portal: PortalName,
    *,
    env: dict[str, str] | None = None,
    home: Path | None = None,
    config_path: Path | None = None,
) -> str:
    """Return the configured base URL for *portal*."""
    environ = os.environ if env is None else env
    env_var = URL_ENV_VARS[portal]
    env_val = environ.get(env_var, "").strip()
    if env_val:
        return env_val.rstrip("/")
    config_urls = _read_config_urls(config_path, home=home)
    cfg_url = config_urls.get(portal)
    if cfg_url:
        return cfg_url
    return DEFAULT_URLS[portal]


def _key_kind(value: str) -> Literal["acw", "legacy"]:
    return "acw" if value.startswith("acw_") else "legacy"


def _read_key_file(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _resolve_override_path(raw: str, home_dir: Path) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute() and raw.startswith("~/"):
        return home_dir / raw[2:]
    return candidate


def _lazy_candidate_sources(
    portal: PortalName, environ: Mapping[str, str], home_dir: Path
) -> list[tuple[str, Callable[[], str]]]:
    if portal == "cfactory":
        return [
            ("$CFACTORY_API_KEY", lambda: environ.get("CFACTORY_API_KEY", "").strip()),
            (
                "~/.cfactory/.mcp-key",
                lambda: _read_key_file(home_dir / ".cfactory" / ".mcp-key"),
            ),
            (
                "~/.cfactory/.token",
                lambda: _read_key_file(home_dir / ".cfactory" / ".token"),
            ),
        ]

    upper = portal.upper()
    mcp_var = f"{upper}_MCP_KEY"
    tok_var = f"{upper}_API_TOKEN_FILE"

    def _read_override() -> str:
        tok_override = environ.get(tok_var, "").strip()
        if not tok_override:
            return ""
        return _read_key_file(_resolve_override_path(tok_override, home_dir))

    return [
        (f"${mcp_var}", lambda: environ.get(mcp_var, "").strip()),
        (
            f"~/.{portal}/.mcp-key",
            lambda: _read_key_file(home_dir / f".{portal}" / ".mcp-key"),
        ),
        (f"${tok_var}", _read_override),
        (
            f"~/.{portal}/.token",
            lambda: _read_key_file(home_dir / f".{portal}" / ".token"),
        ),
    ]


def resolve_portal_key(
    portal: PortalName,
    *,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> ResolvedKey | None:
    """Resolve the API key for *portal* in canonical precedence order.

    Stops at the first usable source without touching lower-priority files.
    Never echoes the key value in errors or source names.
    """
    environ: Mapping[str, str] = os.environ if env is None else env
    home_dir = (home or Path.home()).expanduser()
    for source_name, loader in _lazy_candidate_sources(portal, environ, home_dir):
        value = loader()
        if value:
            return ResolvedKey(portal, value, source_name, _key_kind(value))
    return None


def collect_known_secrets(
    *,
    env: dict[str, str] | None = None,
    home: Path | None = None,
    portals: tuple[PortalName, ...] = PORTAL_NAMES,
) -> tuple[str, ...]:
    """Gather loaded portal key values for defensive output redaction."""
    values: list[str] = []
    for portal in portals:
        resolved = resolve_portal_key(portal, env=env, home=home)
        if resolved and resolved.value and resolved.value not in values:
            values.append(resolved.value)
    return tuple(values)
