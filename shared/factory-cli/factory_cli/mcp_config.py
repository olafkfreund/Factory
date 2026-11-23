"""Implementation of `factory mcp-config claude|codex|agy [--write] [--force]`."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from factory_cli.config import RuntimeContext
from factory_cli.submit import EXIT_OK, EXIT_PRECONDITION

AgentName = Literal["claude", "codex", "agy"]
AGENTS: tuple[AgentName, ...] = ("claude", "codex", "agy")

_CODEX_BLOCK = '[mcp_servers.factory]\ncommand = "factory"\nargs = ["mcp"]\n'
_TOML_HEADER_RE = re.compile(r"^\s*(?:\[\[\s*([^\[\]]+?)\s*\]\]|\[\s*([^\[\]]+?)\s*\])\s*(?:#.*)?$")
_AGY_DIR_PARTS = (".gemini", "config", "mcp_config.json")
_MIN_TABLE_PARTS = 2


@dataclass(frozen=True)
class McpConfigOutcome:
    """Result of `factory mcp-config`."""

    exit_code: int
    text: str
    path: Path | None = None


@dataclass(frozen=True)
class _FileSnapshot:
    content_bytes: bytes
    text: str
    mtime_ns: int
    size: int
    sha256: str
    mode: int


def render_snippet(agent: AgentName) -> str:
    """Render the secret-free MCP configuration snippet for *agent*."""
    if agent == "codex":
        return _CODEX_BLOCK
    payload = {"mcpServers": {"factory": {"command": "factory", "args": ["mcp"]}}}
    return json.dumps(payload, indent=2) + "\n"


def default_agent_config_path(
    agent: AgentName,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> Path:
    """Return the target configuration file path for *agent*."""
    work_dir = cwd or Path.cwd()
    home_dir = (home or Path.home()).expanduser()
    if agent == "claude":
        return work_dir / ".mcp.json"
    if agent == "codex":
        return home_dir / ".codex" / "config.toml"
    return home_dir.joinpath(*_AGY_DIR_PARTS)


def _is_factory_toml_table(header_inner: str) -> bool:
    parts = [part.strip().strip("\"'") for part in header_inner.split(".")]
    return len(parts) >= _MIN_TABLE_PARTS and parts[0] == "mcp_servers" and parts[1] == "factory"


def _update_pending_comments(pending_comments: list[str], line: str) -> None:
    stripped = line.strip()
    if stripped.startswith("#"):
        pending_comments.append(line)
    elif not stripped:
        if pending_comments:
            pending_comments.append(line)
    else:
        pending_comments.clear()


def _rewrite_factory_toml_sections(existing_text: str) -> str:
    lines = existing_text.splitlines(keepends=True)
    out_lines: list[str] = []
    pending_comments: list[str] = []
    skipping = False
    inserted = False

    for line in lines:
        match = _TOML_HEADER_RE.match(line)
        if match:
            header_inner = (match.group(1) or match.group(2) or "").strip()
            if _is_factory_toml_table(header_inner):
                pending_comments.clear()
                if not inserted:
                    if out_lines and not out_lines[-1].endswith("\n"):
                        out_lines[-1] = out_lines[-1] + "\n"
                    out_lines.append(_CODEX_BLOCK)
                    inserted = True
                skipping = True
                continue
            if skipping:
                skipping = False
                if out_lines and not out_lines[-1].endswith("\n\n"):
                    out_lines.append("\n")
                out_lines.extend(pending_comments)
                pending_comments.clear()

        if skipping:
            _update_pending_comments(pending_comments, line)
            continue

        out_lines.append(line)

    if not inserted:
        if out_lines and not out_lines[-1].endswith("\n"):
            out_lines.append("\n")
        out_lines.append(_CODEX_BLOCK)

    return "".join(out_lines)


def _strip_factory_from_parsed_toml(doc: dict[str, Any]) -> dict[str, Any]:
    cleaned = copy.deepcopy(doc)
    servers = cleaned.get("mcp_servers")
    if isinstance(servers, dict):
        servers.pop("factory", None)
        if not servers:
            cleaned.pop("mcp_servers", None)
    return cleaned


def replace_or_append_codex_toml(existing_text: str, *, force: bool) -> str:
    """Insert or replace `[mcp_servers.factory]` and subtables in *existing_text*."""
    parsed = tomllib.loads(existing_text) if existing_text.strip() else {}
    mcp_servers = parsed.get("mcp_servers")
    has_existing = isinstance(mcp_servers, dict) and "factory" in mcp_servers

    if has_existing and not force:
        raise ValueError(
            "mcp_servers.factory already exists in config.toml (pass --force to replace)"
        )

    if not has_existing:
        sep = "" if not existing_text or existing_text.endswith("\n") else "\n"
        prefix = f"{existing_text}{sep}\n" if existing_text.strip() else ""
        candidate = f"{prefix}{_CODEX_BLOCK}"
    else:
        candidate = _rewrite_factory_toml_sections(existing_text)

    validated = tomllib.loads(candidate)
    factory_entry = validated.get("mcp_servers", {}).get("factory")
    if factory_entry != {"command": "factory", "args": ["mcp"]}:
        raise ValueError("cannot safely replace inline mcp_servers.factory table in TOML")

    if _strip_factory_from_parsed_toml(parsed) != _strip_factory_from_parsed_toml(validated):
        raise ValueError("TOML rewrite altered configuration outside mcp_servers.factory")

    return candidate


def _merge_json_config(existing_text: str, *, force: bool) -> str:
    data: dict[str, Any] = {}
    if existing_text.strip():
        loaded = json.loads(existing_text)
        if not isinstance(loaded, dict):
            raise ValueError("existing JSON config root must be an object")
        data = loaded
    servers = data.get("mcpServers")
    if servers is None:
        servers = {}
        data["mcpServers"] = servers
    elif not isinstance(servers, dict):
        raise ValueError("mcpServers in JSON config must be an object")

    if "factory" in servers and not force:
        raise ValueError("mcpServers.factory already exists (pass --force to replace)")

    servers["factory"] = {"command": "factory", "args": ["mcp"]}
    return json.dumps(data, indent=2) + "\n"


def _reject_if_symlink(path: Path, *, label: str) -> None:
    if path.is_symlink():
        raise ValueError(f"refusing to touch symlink {label}: {path}")


def _read_target_once(target: Path) -> _FileSnapshot | None:
    """Read *target* at most once without following symlinks and record its fingerprint."""
    _reject_if_symlink(target, label="target")
    try:
        lstat_res = os.lstat(target)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(lstat_res.st_mode):
        raise ValueError(f"refusing to touch symlink target: {target}")
    if not stat.S_ISREG(lstat_res.st_mode):
        raise ValueError(f"target is not a regular file: {target}")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError(f"target is not a regular file: {target}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw_bytes = b"".join(chunks)
    finally:
        os.close(fd)

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"cannot decode {target} as UTF-8: {exc}") from exc

    return _FileSnapshot(
        content_bytes=raw_bytes,
        text=text,
        mtime_ns=st.st_mtime_ns,
        size=st.st_size,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        mode=st.st_mode & 0o777,
    )


def _verify_snapshot_unchanged(target: Path, snapshot: _FileSnapshot | None) -> None:
    """Refuse if *target* appeared, disappeared, became a symlink, or changed since *snapshot*."""
    _reject_if_symlink(target, label="target")
    try:
        st_now = os.lstat(target)
    except FileNotFoundError as exc:
        if snapshot is not None:
            raise ValueError(f"target file {target} changed concurrently (deleted)") from exc
        return

    if stat.S_ISLNK(st_now.st_mode):
        raise ValueError(f"refusing to touch symlink target: {target}")
    if snapshot is None:
        raise ValueError(f"target file {target} changed concurrently (created)")

    if st_now.st_mtime_ns != snapshot.mtime_ns or st_now.st_size != snapshot.size:
        raise ValueError(f"target file {target} changed concurrently")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags)
    try:
        current_bytes = b""
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        current_bytes = b"".join(chunks)
    finally:
        os.close(fd)

    if (
        len(current_bytes) != snapshot.size
        or hashlib.sha256(current_bytes).hexdigest() != snapshot.sha256
    ):
        raise ValueError(f"target file {target} changed concurrently")


def _atomic_write_bytes(
    dest: Path,
    payload: bytes,
    *,
    mode: int,
    label: str,
    before_replace: Any = None,
) -> None:
    _reject_if_symlink(dest, label=label)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.name}.",
        suffix=".tmp",
        dir=dest.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(payload)
        tmp_path.chmod(mode)
        _reject_if_symlink(dest, label=label)
        if callable(before_replace):
            before_replace()
        tmp_path.replace(dest)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _write_from_snapshot(
    target: Path,
    snapshot: _FileSnapshot | None,
    new_text: str,
    *,
    before_commit_hook: Any = None,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    bak_path = target.with_name(f"{target.name}.bak")
    _reject_if_symlink(target, label="target")
    _reject_if_symlink(bak_path, label="backup")

    if callable(before_commit_hook):
        before_commit_hook()

    _verify_snapshot_unchanged(target, snapshot)

    if snapshot is not None:
        _atomic_write_bytes(
            bak_path,
            snapshot.content_bytes,
            mode=0o600,
            label="backup",
            before_replace=lambda: _verify_snapshot_unchanged(target, snapshot),
        )

    target_mode = snapshot.mode if snapshot is not None else 0o600
    _atomic_write_bytes(
        target,
        new_text.encode("utf-8"),
        mode=target_mode,
        label="target",
        before_replace=lambda: _verify_snapshot_unchanged(target, snapshot),
    )


def run_mcp_config(
    agent: AgentName,
    *,
    write: bool = False,
    force: bool = False,
    target_path: Path | None = None,
    ctx: RuntimeContext | None = None,
    _before_commit_hook: Any = None,
) -> McpConfigOutcome:
    """Print or write the secret-free MCP configuration entry for *agent*.

    Does not read or resolve any portal keys.
    """
    if not write:
        return McpConfigOutcome(exit_code=EXIT_OK, text=render_snippet(agent))

    rt = ctx or RuntimeContext()
    path = target_path or default_agent_config_path(agent, cwd=rt.cwd, home=rt.home)
    bak_path = path.with_name(f"{path.name}.bak")

    try:
        _reject_if_symlink(path, label="target")
        _reject_if_symlink(bak_path, label="backup")
        snapshot = _read_target_once(path)
        existing_text = snapshot.text if snapshot is not None else ""
        if agent == "codex":
            new_text = replace_or_append_codex_toml(existing_text, force=force)
        else:
            new_text = _merge_json_config(existing_text, force=force)
        _write_from_snapshot(
            path,
            snapshot,
            new_text,
            before_commit_hook=_before_commit_hook,
        )
    except (ValueError, OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        return McpConfigOutcome(
            exit_code=EXIT_PRECONDITION,
            text=f"error: {exc}",
            path=path,
        )

    return McpConfigOutcome(
        exit_code=EXIT_OK,
        text=f"wrote factory MCP entry to {path}",
        path=path,
    )
