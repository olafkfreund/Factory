"""Implementation of `factory test` (TFactory spec ingest over `/api/mcp-stdio/specs/ingest`)."""

from __future__ import annotations

import re
import secrets as stdlib_secrets
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Literal

from factory_cli._vendor.factory_common.client_errors import InputRejectedError
from factory_cli.config import (
    RuntimeContext,
    collect_known_secrets,
    resolve_portal_key,
    resolve_portal_url,
)
from factory_cli.gitartifacts import (
    PreconditionError,
    find_repo_root,
    parse_slug,
    resolve_branch_sha,
    resolve_repo_identity,
)
from factory_cli.submit import EXIT_OK, EXIT_PRECONDITION, EXIT_REJECTED, EXIT_UNKNOWN
from factory_cli.transport import (
    PortalTransport,
    TransportResponse,
    extract_safe_detail,
    redact_structure,
    redact_text,
)

_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
_AC_PREFIX_RE = re.compile(r"^(?:\*\*AC#?\d+:?\*\*|AC#?\d+:)\s*", re.IGNORECASE)
_SLUG_SAFE_RE = re.compile(r"[^a-z0-9-]+")
_MAX_RUN_ID_LEN = 64
_VERIFICATION_HEADING_LEVEL = 2

_HTTP_OK = int(HTTPStatus.OK)
_HTTP_NOT_FOUND = int(HTTPStatus.NOT_FOUND)
_HTTP_SERVER_ERR = int(HTTPStatus.INTERNAL_SERVER_ERROR)


@dataclass(frozen=True)
class TestOutcome:
    """Result of a `factory test` invocation."""

    exit_code: int
    outcome: Literal["ok", "rejected", "unknown"]
    payload: dict[str, Any]
    lines: tuple[str, ...]


def _strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "\n".join(lines[idx + 1 :])
    return text


def _collect_verification_lines(body: str, *, require_heading: bool) -> list[str]:
    if not require_heading:
        return body.splitlines()
    section_lines: list[str] = []
    in_verification = False
    for line in body.splitlines():
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip().rstrip("#").strip().lower()
            if not in_verification:
                if level == _VERIFICATION_HEADING_LEVEL and title == "verification":
                    in_verification = True
                continue
            if level <= _VERIFICATION_HEADING_LEVEL:
                break
            section_lines.append(line)
            continue
        if in_verification:
            section_lines.append(line)
    return section_lines


def extract_verification_bullets(text: str, *, require_verification_heading: bool) -> list[str]:
    """Extract bullet criteria from `## Verification` (or from the whole file if not required)."""
    body = _strip_frontmatter(text)
    section_lines = _collect_verification_lines(body, require_heading=require_verification_heading)

    bullets: list[str] = []
    base_indent: int | None = None
    for line in section_lines:
        if _HEADING_RE.match(line):
            base_indent = None
            continue
        match = _BULLET_RE.match(line)
        if not match:
            # A wrapped line continues the current bullet; dropping it changes the criterion.
            if bullets and line.strip() and line[:1].isspace():
                bullets[-1] = f"{bullets[-1]} {line.strip()}"
            continue
        indent = len(match.group(1).expandtabs(2))
        content = _AC_PREFIX_RE.sub("", match.group(2).strip()).rstrip(":").strip()
        if not content:
            continue
        if base_indent is None or indent <= base_indent:
            base_indent = indent
            bullets.append(content)
        elif bullets:
            bullets[-1] = f"{bullets[-1]}; {content}"

    return [b for b in bullets if b]


def format_acceptance_criteria_markdown(title: str, criteria: list[str]) -> str:
    """Render criteria as `## Acceptance Criteria` with `- AC1: ...`."""
    lines = [f"# {title}", "", "## Acceptance Criteria", ""]
    for idx, item in enumerate(criteria, start=1):
        lines.append(f"- AC{idx}: {item}")
    return "\n".join(lines) + "\n"


def build_run_id(stem: str, head_sha: str, *, rand_hex: str | None = None) -> str:
    """Build `<slug|file-stem>-<short sha>-<6 random hex>` in `[a-z0-9-]`, max 64 chars."""
    clean_stem = _SLUG_SAFE_RE.sub("-", stem.lower()).strip("-") or "spec"
    short_sha = _SLUG_SAFE_RE.sub("", head_sha.lower())[:7] or "0000000"
    suffix_rand = (rand_hex or stdlib_secrets.token_hex(3)).lower()[:6]
    suffix = f"-{short_sha}-{suffix_rand}"
    max_stem_len = _MAX_RUN_ID_LEN - len(suffix)
    trimmed_stem = clean_stem[:max_stem_len].rstrip("-") or "spec"
    return f"{trimmed_stem}{suffix}"


def _qualify_repo(provider: str, repo: str) -> str:
    return repo if provider == "github" else f"{provider}:{repo}"


def _rejected_test(
    detail: str,
    *,
    exit_code: int = EXIT_REJECTED,
    secrets: tuple[str, ...] = (),
) -> TestOutcome:
    safe_detail = redact_text(detail, secrets)
    return TestOutcome(
        exit_code=exit_code,
        outcome="rejected",
        payload=redact_structure({"outcome": "rejected", "detail": safe_detail}, secrets),
        lines=(f"error: {safe_detail}",),
    )


def _load_criteria(
    root: Path,
    work_dir: Path,
    *,
    spec_slug: str | None,
    criteria_file: str | None,
) -> tuple[str, list[str]]:
    if bool(spec_slug) == bool(criteria_file):
        raise PreconditionError("pass exactly one of --spec or --criteria")
    if spec_slug:
        slug = parse_slug(spec_slug)
        source_path = root / "spec" / f"{slug}.md"
        if not source_path.is_file():
            raise PreconditionError(f"missing spec file: spec/{slug}.md")
        raw_text = source_path.read_text(encoding="utf-8")
        criteria = extract_verification_bullets(raw_text, require_verification_heading=True)
        stem = slug
    else:
        raw_file = criteria_file or ""
        cand = Path(raw_file)
        source_path = cand if cand.is_absolute() else (work_dir / cand)
        if not source_path.is_file():
            raise PreconditionError(f"missing criteria file: {raw_file}")
        raw_text = source_path.read_text(encoding="utf-8")
        criteria = extract_verification_bullets(raw_text, require_verification_heading=False)
        stem = source_path.stem

    if not criteria:
        raise PreconditionError("no acceptance criteria bullets found")
    return stem, criteria


def _evaluate_test_response(
    resp: TransportResponse,
    *,
    project_id: str,
    spec_id: str,
    local_sha: str,
    secrets: tuple[str, ...],
) -> TestOutcome:
    if resp.status == _HTTP_NOT_FOUND:
        return _rejected_test("project not found", exit_code=EXIT_REJECTED, secrets=secrets)

    if (
        resp.status == 0
        or resp.status >= _HTTP_SERVER_ERR
        or int(HTTPStatus.MULTIPLE_CHOICES) <= resp.status < int(HTTPStatus.BAD_REQUEST)
    ):
        detail = resp.network_error or extract_safe_detail(resp.data, resp.raw_text, secrets)
        if resp.after_send:
            safe_detail = redact_text(detail, secrets)
            return TestOutcome(
                exit_code=EXIT_UNKNOWN,
                outcome="unknown",
                payload=redact_structure(
                    {
                        "outcome": "unknown",
                        "spec_id": spec_id,
                        "tf_id": f"tf:{project_id}/{spec_id}",
                        "detail": safe_detail,
                    },
                    secrets,
                ),
                lines=(
                    f"outcome unknown: {safe_detail}",
                    f"tf_id: tf:{project_id}/{spec_id}",
                    f"check with: factory status tf:{project_id}/{spec_id}",
                ),
            )
        return _rejected_test(detail, exit_code=EXIT_REJECTED, secrets=secrets)

    if resp.status != _HTTP_OK or not resp.is_json or not isinstance(resp.data, dict):
        detail = resp.network_error or extract_safe_detail(resp.data, resp.raw_text, secrets)
        return _rejected_test(detail, exit_code=EXIT_REJECTED, secrets=secrets)

    data = resp.data
    workspace_project_id = str(
        data.get("workspace_project_id") or data.get("project_id") or project_id
    )
    returned_spec_id = str(data.get("spec_id") or data.get("task_id") or spec_id)
    checked_out_sha = str(data.get("source_sha") or "")
    planner_scheduled = bool(data.get("planner_scheduled", True))
    planner_reason = data.get("planner_reason")

    lines = [
        f"tf_id: tf:{workspace_project_id}/{returned_spec_id}",
        f"workspace_project_id: {workspace_project_id}",
        f"spec_id: {returned_spec_id}",
        f"branch_head_sha: {local_sha}",
        f"tfactory_source_sha: {checked_out_sha or 'none'}",
    ]
    sha_mismatch = bool(checked_out_sha and checked_out_sha != local_sha)
    if sha_mismatch:
        lines.append(
            f"warning: branch head SHA ({local_sha}) differs from "
            f"TFactory checked-out SHA ({checked_out_sha})"
        )
    if not planner_scheduled:
        lines.append(f"planner_scheduled: false (reason: {planner_reason or 'unknown'})")

    payload: dict[str, Any] = redact_structure(
        {
            "outcome": "ok",
            "tf_id": f"tf:{workspace_project_id}/{returned_spec_id}",
            "workspace_project_id": workspace_project_id,
            "spec_id": returned_spec_id,
            "branch_head_sha": local_sha,
            "tfactory_source_sha": checked_out_sha or None,
            "sha_mismatch": sha_mismatch,
            "planner_scheduled": planner_scheduled,
            "planner_reason": planner_reason if not planner_scheduled else None,
        },
        secrets,
    )
    return TestOutcome(exit_code=EXIT_OK, outcome="ok", payload=payload, lines=tuple(lines))


def run_test(  # noqa: PLR0913
    project_id: str,
    branch: str,
    *,
    spec_slug: str | None = None,
    criteria_file: str | None = None,
    pr_number: int | None = None,
    ctx: RuntimeContext | None = None,
) -> TestOutcome:
    """Execute `factory test` against TFactory's scoped ingest endpoint."""
    rt = ctx or RuntimeContext()
    secrets = collect_known_secrets(env=rt.env, home=rt.home, portals=("tfactory",))
    work_dir = rt.cwd or Path.cwd()

    try:
        clean_proj = project_id.strip()
        clean_branch = branch.strip()
        if not clean_proj:
            raise PreconditionError("--project is required")
        if not clean_branch:
            raise PreconditionError("--branch is required")
        root = find_repo_root(work_dir)
        identity = resolve_repo_identity(work_dir, require_base=False)
        local_sha = resolve_branch_sha(work_dir, clean_branch)
        stem, criteria = _load_criteria(
            root, work_dir, spec_slug=spec_slug, criteria_file=criteria_file
        )
        tf_key = resolve_portal_key("tfactory", env=rt.env, home=rt.home)
        if tf_key is None:
            raise PreconditionError(
                "TFactory key not configured (set $TFACTORY_MCP_KEY or ~/.tfactory/.mcp-key)"
            )
        tf_url = resolve_portal_url(
            "tfactory",
            env=rt.env,
            home=rt.home,
            config_path=rt.config_path,
        )
    except (PreconditionError, ValueError) as exc:
        if isinstance(exc, InputRejectedError):
            return _rejected_test(str(exc), exit_code=EXIT_REJECTED, secrets=secrets)
        return _rejected_test(str(exc), exit_code=EXIT_PRECONDITION, secrets=secrets)

    try:
        transport = PortalTransport(tf_url, token=tf_key.value, secrets=secrets)
        spec_id = build_run_id(stem, local_sha)
        resp = transport.request(
            "POST",
            "/api/mcp-stdio/specs/ingest",
            body={
                "project_id": clean_proj,
                "spec_id": spec_id,
                "spec_text": format_acceptance_criteria_markdown(stem, criteria),
                "source_branch": clean_branch,
                "repo": _qualify_repo(identity.provider, identity.repo),
                "pr_number": pr_number,
                "no_register": True,
            },
        )
    except InputRejectedError as exc:
        return _rejected_test(str(exc), exit_code=EXIT_PRECONDITION, secrets=secrets)
    return _evaluate_test_response(
        resp,
        project_id=clean_proj,
        spec_id=spec_id,
        local_sha=local_sha,
        secrets=secrets,
    )
