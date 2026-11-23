"""Git worktree inspection, blob framing, and approval-commit verification."""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import subprocess
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from factory_cli.transport import redact_url_userinfo


class _YamlModule(Protocol):
    YAMLError: type[Exception]

    def safe_load(self, stream: str) -> Any: ...


_yaml = cast(_YamlModule, importlib.import_module("yaml"))

StageName = Literal["intent", "spec", "plan"]
STAGES: tuple[StageName, ...] = ("intent", "spec", "plan")

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SYMREF_HEAD_RE = re.compile(r"^ref:\s+refs/heads/(\S+)\s+HEAD$")
_MAX_PATH_LEN = 512
_MIN_REPO_SEGMENTS = 2

_GIT_GLOBAL_ARGS: tuple[str, ...] = (
    "--no-replace-objects",
    "--literal-pathspecs",
    "-c",
    "log.showSignature=false",
)


class PreconditionError(ValueError):
    """Local git or artifact precondition failure (exit 2)."""


@dataclass(frozen=True)
class ApprovedArtifact:
    """Verified artifact for one stage ready to send to PFactory."""

    stage: StageName
    path: str
    content: str
    blob_sha: str
    approve_commit_sha: str
    approve_commit_author: str

    def to_payload(self) -> dict[str, str]:
        return {
            "stage": self.stage,
            "path": self.path,
            "content": self.content,
            "blob_sha": self.blob_sha,
            "approve_commit_sha": self.approve_commit_sha,
            "approve_commit_author": self.approve_commit_author,
        }


@dataclass(frozen=True)
class RepoIdentity:
    """Resolved git repository identity for a submission."""

    root: Path
    provider: str
    repo: str
    base_ref: str
    branch: str
    head_sha: str


def git_blob_sha1(raw_bytes: bytes) -> str:
    """Compute the SHA-1 git blob object id for *raw_bytes*."""
    header = f"blob {len(raw_bytes)}\0".encode("ascii")
    digest = hashlib.sha1(header + raw_bytes, usedforsecurity=False)
    return digest.hexdigest()


def parse_slug(arg: str) -> str:
    """Accept either `<slug>` or `plan/<slug>.md` (or `intent/` / `spec/`)."""
    cleaned = arg.strip()
    if not cleaned:
        raise PreconditionError("slug is required")
    for prefix in ("plan/", "spec/", "intent/"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    if cleaned.endswith(".md"):
        cleaned = cleaned[:-3]
    if not cleaned or "/" in cleaned or ".." in cleaned:
        raise PreconditionError(f"invalid artifact slug: {arg!r}")
    return cleaned


def parse_frontmatter_status(text: str) -> str | None:
    """Return the YAML frontmatter `status` field, or None if missing/malformed."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end_idx: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return None
    yaml_text = "\n".join(lines[1:end_idx])
    try:
        parsed = _yaml.safe_load(yaml_text)
    except _yaml.YAMLError:
        return None
    if not isinstance(parsed, dict):
        return None
    status = parsed.get("status")
    return str(status).strip() if status is not None else None


def _git_env() -> dict[str, str]:
    return {
        **os.environ,
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_LITERAL_PATHSPECS": "1",
    }


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["git", *_GIT_GLOBAL_ARGS, *args],  # noqa: S607
        cwd=cwd,
        env=_git_env(),
        capture_output=True,
        text=True,
        check=False,
    )


def _run_git_bytes(cwd: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603
        ["git", *_GIT_GLOBAL_ARGS, *args],  # noqa: S607
        cwd=cwd,
        env=_git_env(),
        capture_output=True,
        check=False,
    )


def find_repo_root(cwd: Path) -> Path:
    proc = _run_git(cwd, "rev-parse", "--show-toplevel")
    if proc.returncode != 0 or not proc.stdout.strip():
        raise PreconditionError(f"not a git worktree: {cwd}")
    return Path(proc.stdout.strip())


def check_sha1_repo(root: Path) -> None:
    proc = _run_git(root, "rev-parse", "--show-object-format")
    if proc.returncode == 0:
        fmt = proc.stdout.strip().lower()
        if fmt and fmt != "sha1":
            raise PreconditionError(f"object format {fmt!r} is not supported in release 1")


def resolve_pinned_head_sha(root: Path) -> str:
    """Resolve and validate the current HEAD commit as a 40-char SHA-1."""
    head_proc = _run_git(
        root,
        "rev-parse",
        "--verify",
        "--quiet",
        "--end-of-options",
        "HEAD^{commit}",
    )
    if head_proc.returncode != 0 or not _SHA1_RE.match(head_proc.stdout.strip()):
        raise PreconditionError("cannot resolve HEAD SHA-1 commit")
    return head_proc.stdout.strip()


def normalize_remote_url(remote_url: str) -> tuple[str, str]:
    """Normalize a git remote URL to `(provider, owner/repo)`."""
    raw = remote_url.strip()
    if not raw:
        raise PreconditionError("origin remote URL is empty")

    host = ""
    path = ""
    if "://" in raw:
        parsed = urllib.parse.urlsplit(raw)
        host = (parsed.hostname or "").lower()
        path = parsed.path
    elif "@" in raw and ":" in raw:
        user_host, path = raw.split(":", 1)
        host = user_host.rsplit("@", 1)[-1].lower()
    else:
        parts = raw.strip("/").split("/")
        if len(parts) >= _MIN_REPO_SEGMENTS and "." in parts[0]:
            host = parts[0].lower()
            path = "/".join(parts[1:])
        else:
            host = "github.com"
            path = raw

    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]

    if "gitlab" in host:
        provider = "gitlab"
    elif host in {"dev.azure.com", "ssh.dev.azure.com", "vs-ssh.visualstudio.com"} or host.endswith(
        (".dev.azure.com", ".visualstudio.com")
    ):
        provider = "azure_devops"
        segments = [seg for seg in path.split("/") if seg]
        if "_git" in segments:
            git_idx = segments.index("_git")
            org_parts = [s for s in segments[:git_idx] if s != "DefaultCollection"]
            repo_parts = segments[git_idx + 1 :]
            path = "/".join([*org_parts, *repo_parts])
    else:
        provider = "github"

    segments = [seg for seg in path.split("/") if seg]
    if len(segments) < _MIN_REPO_SEGMENTS or ".." in segments:
        safe_url = redact_url_userinfo(raw)
        raise PreconditionError(f"cannot extract owner/repo from origin URL: {safe_url!r}")
    return provider, "/".join(segments)


def resolve_default_base_ref(root: Path) -> str:
    """Resolve the remote default branch via origin/HEAD or `git ls-remote --symref`."""
    proc = _run_git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if proc.returncode == 0 and proc.stdout.strip():
        ref = proc.stdout.strip()
        if ref.startswith("origin/"):
            return ref[len("origin/") :]
        return ref

    ls_proc = _run_git(root, "ls-remote", "--symref", "origin", "HEAD")
    if ls_proc.returncode == 0 and ls_proc.stdout:
        for line in ls_proc.stdout.splitlines():
            match = _SYMREF_HEAD_RE.match(line.strip())
            if match:
                return match.group(1)

    raise PreconditionError(
        "cannot determine remote default branch (set refs/remotes/origin/HEAD or pass --base)"
    )


def resolve_repo_identity(
    cwd: Path,
    *,
    base_ref: str | None = None,
    require_base: bool = True,
) -> RepoIdentity:
    """Resolve repository root, provider, owner/repo, branch, base_ref, and pinned HEAD SHA."""
    root = find_repo_root(cwd)
    check_sha1_repo(root)
    head_sha = resolve_pinned_head_sha(root)

    branch_proc = _run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""
    if not branch:
        raise PreconditionError("detached HEAD: check out a branch before submitting")

    remote_proc = _run_git(root, "remote", "get-url", "origin")
    if remote_proc.returncode != 0 or not remote_proc.stdout.strip():
        raise PreconditionError("git remote 'origin' is not configured")
    provider, repo = normalize_remote_url(remote_proc.stdout.strip())

    if require_base:
        resolved_base = (base_ref or "").strip() or resolve_default_base_ref(root)
    else:
        resolved_base = (base_ref or "").strip()

    return RepoIdentity(
        root=root,
        provider=provider,
        repo=repo,
        base_ref=resolved_base,
        branch=branch,
        head_sha=head_sha,
    )


def resolve_branch_sha(cwd: Path, branch: str) -> str:
    """Return the commit SHA for *branch* (local or `origin/<branch>`) in *cwd*."""
    clean = branch.strip()
    if not clean:
        raise PreconditionError("unknown branch: ''")
    root = find_repo_root(cwd)
    for candidate in (clean, f"origin/{clean}"):
        proc = _run_git(
            root,
            "rev-parse",
            "--verify",
            "--quiet",
            "--end-of-options",
            f"{candidate}^{{commit}}",
        )
        if proc.returncode == 0 and _SHA1_RE.match(proc.stdout.strip()):
            return proc.stdout.strip()
    raise PreconditionError(f"unknown branch: {clean!r}")


def remote_branch_warning(identity: RepoIdentity) -> str | None:
    """Warn when HEAD differs from the known origin branch tip."""
    proc = _run_git(
        identity.root, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{identity.branch}"
    )
    if proc.returncode != 0 or proc.stdout.strip() != identity.head_sha:
        return f"warning: HEAD is not on origin/{identity.branch}; push before submitting"
    return None


def _sanitize_author(raw: str) -> str:
    cleaned = _CONTROL_RE.sub("", raw).strip()
    if not cleaned or not cleaned.isprintable():
        cleaned = "Unknown <unknown@localhost>"
    return cleaned[:200]


def _status_at_commit(root: Path, commit: str, rel_path: str) -> str | None:
    proc = _run_git_bytes(root, "show", "--end-of-options", f"{commit}:{rel_path}")
    if proc.returncode != 0:
        return None
    try:
        text = proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return parse_frontmatter_status(text)


def _find_approval_commit(
    root: Path,
    rel_path: str,
    head_sha: str,
    head_blob_sha: str,
    stage: StageName,
) -> tuple[str, str]:
    """Find the newest ancestor of *head_sha* changing `draft` -> `approved` with same blob."""
    log_proc = _run_git(
        root,
        "log",
        "--format=%H%x00%an <%ae>",
        "--end-of-options",
        head_sha,
        "--",
        rel_path,
    )
    if log_proc.returncode != 0 or not log_proc.stdout.strip():
        raise PreconditionError(f"{rel_path} is not committed in HEAD")

    entries: list[tuple[str, str]] = []
    for line in log_proc.stdout.splitlines():
        if not line.strip():
            continue
        sha, _, author = line.partition("\x00")
        entries.append((sha.strip(), _sanitize_author(author)))

    for commit_sha, author in entries:
        blob_proc = _run_git(
            root,
            "rev-parse",
            "--verify",
            "--quiet",
            "--end-of-options",
            f"{commit_sha}:{rel_path}",
        )
        if blob_proc.returncode != 0:
            continue
        if blob_proc.stdout.strip() != head_blob_sha:
            raise PreconditionError(f"re-approve {stage}: {rel_path} was modified after approval")
        curr_status = _status_at_commit(root, commit_sha, rel_path)
        if curr_status != "approved":
            break

        parent_proc = _run_git(
            root,
            "rev-parse",
            "--verify",
            "--quiet",
            "--end-of-options",
            f"{commit_sha}^",
        )
        parent_sha = parent_proc.stdout.strip() if parent_proc.returncode == 0 else ""
        parent_status = _status_at_commit(root, parent_sha, rel_path) if parent_sha else None
        if parent_status == "draft":
            if not _SHA1_RE.match(commit_sha):
                raise PreconditionError(f"invalid commit SHA for {rel_path}: {commit_sha!r}")
            return commit_sha, author

    raise PreconditionError(
        f"missing approval commit for {stage} ({rel_path}): "
        "requires a commit changing status from draft to approved"
    )


def verify_and_load_artifacts(
    root: Path,
    slug: str,
    *,
    head_sha: str | None = None,
) -> tuple[ApprovedArtifact, ...]:
    """Verify all three artifact stages in *root* at *head_sha* for *slug*."""
    check_sha1_repo(root)
    pinned_head = (
        head_sha if (head_sha and _SHA1_RE.match(head_sha)) else resolve_pinned_head_sha(root)
    )
    artifacts: list[ApprovedArtifact] = []

    for stage in STAGES:
        rel_path = f"{stage}/{slug}.md"
        if len(rel_path) > _MAX_PATH_LEN or ".." in Path(rel_path).parts:
            raise PreconditionError(f"invalid artifact path: {rel_path}")
        full_path = root / rel_path
        if not full_path.is_file():
            raise PreconditionError(f"missing artifact file: {rel_path}")

        try:
            working_bytes = full_path.read_bytes()
            working_text = working_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise PreconditionError(f"cannot read {rel_path} as UTF-8: {exc}") from exc

        head_blob_proc = _run_git(
            root,
            "rev-parse",
            "--verify",
            "--quiet",
            "--end-of-options",
            f"{pinned_head}:{rel_path}",
        )
        if head_blob_proc.returncode != 0 or not head_blob_proc.stdout.strip():
            raise PreconditionError(f"uncommitted artifact file: {rel_path}")
        head_blob_sha = head_blob_proc.stdout.strip()
        if not _SHA1_RE.match(head_blob_sha):
            raise PreconditionError(
                f"non-SHA-1 blob id for {rel_path} (not supported in release 1)"
            )

        working_blob_sha = git_blob_sha1(working_bytes)
        if working_blob_sha != head_blob_sha:
            raise PreconditionError(
                f"working copy of {rel_path} differs from HEAD (commit or revert changes first)"
            )

        status = parse_frontmatter_status(working_text)
        if status != "approved":
            raise PreconditionError(
                f"{rel_path} frontmatter status is {status!r} (expected 'approved')"
            )

        approve_sha, approve_author = _find_approval_commit(
            root,
            rel_path,
            pinned_head,
            head_blob_sha,
            stage,
        )
        artifacts.append(
            ApprovedArtifact(
                stage=stage,
                path=rel_path,
                content=working_text,
                blob_sha=working_blob_sha,
                approve_commit_sha=approve_sha,
                approve_commit_author=approve_author,
            )
        )

    return tuple(artifacts)
