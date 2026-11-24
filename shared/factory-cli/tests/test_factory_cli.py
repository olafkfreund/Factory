"""Test suite for `factory-cli` (#3865).

Covers:
- temp git repo approval-commit cases (approved, edit after approval, missing
  approve commit, dirty tree, SHA-256 repo);
- git blob framing;
- key resolution order across PFactory, AIFactory, TFactory, CFactory;
- canary key redaction (stdout, stderr, MCP JSON);
- URL policy (userinfo, non-loopback http, redirect);
- stdlib `http.server` fake portals for submit 0/1/3 and lost-response (one
  emit POST, exit 3), test, status, doctor;
- `mcp-config` output secret-free for claude, codex, agy;
- `--write` refusal without `--force`, `--force` replacing a Codex table with
  sibling tables intact and valid TOML, `.bak` 0600, original mode preserved;
- vendor drift test against `shared/factory-common/factory_common`.
"""

from __future__ import annotations

import contextlib
import http.server
import json
import os
import subprocess
import sys
import threading
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[1]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from factory_cli.__main__ import main  # noqa: E402
from factory_cli._vendor.factory_common.client_errors import InputRejectedError  # noqa: E402
from factory_cli.actions import run_action, run_card  # noqa: E402
from factory_cli.config import (  # noqa: E402
    RuntimeContext,
    resolve_portal_key,
    resolve_portal_url,
)
from factory_cli.doctor import run_doctor  # noqa: E402
from factory_cli.gitartifacts import (  # noqa: E402
    PreconditionError,
    git_blob_sha1,
    normalize_remote_url,
    resolve_repo_identity,
    verify_and_load_artifacts,
)
from factory_cli.mcp_config import (  # noqa: E402
    AGENTS,
    render_snippet,
    run_mcp_config,
)
from factory_cli.mcp_server import (  # noqa: E402
    build_mcp_server,
    handle_factory_action,
    handle_factory_card,
    handle_factory_doctor,
    handle_factory_project_add,
    handle_factory_project_list,
    handle_factory_status,
    handle_factory_submit,
    handle_factory_test,
)
from factory_cli.status import run_status  # noqa: E402
from factory_cli.submit import (  # noqa: E402
    EXIT_OK,
    EXIT_PRECONDITION,
    EXIT_REJECTED,
    EXIT_UNKNOWN,
    run_submit,
)
from factory_cli.testrun import (  # noqa: E402
    build_run_id,
    extract_verification_bullets,
    format_acceptance_criteria_markdown,
    run_test,
)
from factory_cli.transport import (  # noqa: E402
    PortalTransport,
    redact_text,
    validate_cli_url,
)

SLUG = "2026-11-23-3865-factory-cli"
CANARY_KEY = "acw_" + "CANARY_SUPER_SECRET_TOKEN_VALUE_9999"  # split so scanners see no literal


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test User",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test User",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _draft_doc(stage: str) -> str:
    return (
        f"---\nstatus: draft\nissue: 3865\n---\n\n"
        f"# {stage.capitalize()}: Demo\n\n"
        "## Verification\n\n- check one\n- check two\n\n"
        "## Steps\n\n1. file.py:1: edit -> verify pytest\n"
    )


def _approved_doc(stage: str) -> str:
    return _draft_doc(stage).replace("status: draft", "status: approved", 1)


def _init_approved_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "remote", "add", "origin", "https://github.com/owner/demo-repo.git")
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "chore: initial")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    _git(repo, "checkout", "-b", "feat/3865-demo")

    for stage in ("intent", "spec", "plan"):
        stage_dir = repo / stage
        stage_dir.mkdir(exist_ok=True)
        path = stage_dir / f"{SLUG}.md"
        path.write_text(_draft_doc(stage), encoding="utf-8")
        _git(repo, "add", f"{stage}/{SLUG}.md")
        _git(repo, "commit", "-m", f"docs({stage}): draft {SLUG}")
        path.write_text(_approved_doc(stage), encoding="utf-8")
        _git(repo, "add", f"{stage}/{SLUG}.md")
        _git(repo, "commit", "-m", f"docs({stage}): approve {SLUG}")

    return repo


# =============================================================================
# 1. Git blob framing & approval-commit verification
# =============================================================================


def test_git_blob_framing_matches_git_hash_object(tmp_path: Path) -> None:
    sample = b"---\nstatus: approved\n---\n# Title\nUnicode: \xc3\xa9\n"
    file_path = tmp_path / "sample.md"
    file_path.write_bytes(sample)
    proc = subprocess.run(  # noqa: S603
        ["git", "hash-object", str(file_path)],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    assert git_blob_sha1(sample) == proc.stdout.strip()


def test_approval_commit_happy_path(tmp_path: Path) -> None:
    repo = _init_approved_repo(tmp_path)
    identity = resolve_repo_identity(repo)
    assert identity.provider == "github"
    assert identity.repo == "owner/demo-repo"
    assert identity.branch == "feat/3865-demo"
    assert identity.base_ref == "main"

    artifacts = verify_and_load_artifacts(repo, SLUG)
    assert [a.stage for a in artifacts] == ["intent", "spec", "plan"]
    for art in artifacts:
        assert len(art.blob_sha) == 40
        assert len(art.approve_commit_sha) == 40
        assert "Test User <test@example.com>" in art.approve_commit_author


def test_approval_commit_rejects_edit_after_approval(tmp_path: Path) -> None:
    repo = _init_approved_repo(tmp_path)
    plan_file = repo / "plan" / f"{SLUG}.md"
    plan_file.write_text(_approved_doc("plan") + "\nExtra line added after approval.\n")
    _git(repo, "add", f"plan/{SLUG}.md")
    _git(repo, "commit", "-m", "docs(plan): sneaky edit after approve")

    with pytest.raises(PreconditionError, match="re-approve plan"):
        verify_and_load_artifacts(repo, SLUG)


def test_approval_commit_rejects_missing_draft_to_approved_transition(tmp_path: Path) -> None:
    repo = tmp_path / "direct_approve"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "remote", "add", "origin", "git@github.com:owner/repo.git")
    for stage in ("intent", "spec", "plan"):
        (repo / stage).mkdir()
        (repo / stage / f"{SLUG}.md").write_text(_approved_doc(stage))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "docs: committed straight as approved")

    with pytest.raises(PreconditionError, match="missing approval commit for intent"):
        verify_and_load_artifacts(repo, SLUG)


def test_approval_commit_rejects_dirty_working_tree(tmp_path: Path) -> None:
    repo = _init_approved_repo(tmp_path)
    spec_file = repo / "spec" / f"{SLUG}.md"
    spec_file.write_text(_approved_doc("spec") + "\nuncommitted change\n")

    with pytest.raises(PreconditionError, match=r"working copy of spec/.* differs from HEAD"):
        verify_and_load_artifacts(repo, SLUG)


def test_approval_commit_rejects_sha256_repo(tmp_path: Path) -> None:
    repo = tmp_path / "sha256_repo"
    repo.mkdir()
    probe = subprocess.run(  # noqa: S603
        ["git", "init", "--object-format=sha256", str(repo)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip("git version does not support --object-format=sha256")
    with pytest.raises(PreconditionError, match="not supported in release 1"):
        verify_and_load_artifacts(repo, SLUG)


def test_normalize_remote_url_providers() -> None:
    assert normalize_remote_url("git@github.com:org/proj.git") == ("github", "org/proj")
    assert normalize_remote_url("https://gitlab.com/group/sub/proj.git") == (
        "gitlab",
        "group/sub/proj",
    )
    assert normalize_remote_url("https://dev.azure.com/myorg/myproj/_git/myrepo") == (
        "azure_devops",
        "myorg/myproj/myrepo",
    )


# =============================================================================
# 2. Key & URL resolution order + Canary secret redaction
# =============================================================================


def test_key_lookup_order_for_standard_portals(tmp_path: Path) -> None:
    home = tmp_path / "home"
    pf_dir = home / ".pfactory"
    pf_dir.mkdir(parents=True)
    mcp_key_file = pf_dir / ".mcp-key"
    token_file = pf_dir / ".token"
    override_file = tmp_path / "override.tok"

    token_file.write_text("legacy_tok_4\n")
    override_file.write_text("acw_override_3\n")
    mcp_key_file.write_text("acw_file_2\n")

    # 1. $<P>_MCP_KEY wins
    env = {
        "PFACTORY_MCP_KEY": "acw_env_1",
        "PFACTORY_API_TOKEN_FILE": str(override_file),
    }
    k1 = resolve_portal_key("pfactory", env=env, home=home)
    assert k1 is not None
    assert (k1.value, k1.source, k1.kind) == ("acw_env_1", "$PFACTORY_MCP_KEY", "acw")

    # 2. ~/.pfactory/.mcp-key wins when env var is unset
    k2 = resolve_portal_key(
        "pfactory",
        env={"PFACTORY_API_TOKEN_FILE": str(override_file)},
        home=home,
    )
    assert k2 is not None
    assert (k2.value, k2.source, k2.kind) == ("acw_file_2", "~/.pfactory/.mcp-key", "acw")

    # 3. $PFACTORY_API_TOKEN_FILE wins when .mcp-key is absent
    mcp_key_file.unlink()
    k3 = resolve_portal_key(
        "pfactory",
        env={"PFACTORY_API_TOKEN_FILE": str(override_file)},
        home=home,
    )
    assert k3 is not None
    assert (k3.value, k3.source, k3.kind) == (
        "acw_override_3",
        "$PFACTORY_API_TOKEN_FILE",
        "acw",
    )

    # 4. ~/.pfactory/.token fallback
    k4 = resolve_portal_key("pfactory", env={}, home=home)
    assert k4 is not None
    assert (k4.value, k4.source, k4.kind) == ("legacy_tok_4", "~/.pfactory/.token", "legacy")


def test_key_lookup_order_for_cfactory(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cf_dir = home / ".cfactory"
    cf_dir.mkdir(parents=True)
    mcp_file = cf_dir / ".mcp-key"
    tok_file = cf_dir / ".token"

    tok_file.write_text("acw_cf_token\n")
    mcp_file.write_text("acw_cf_mcp\n")

    k1 = resolve_portal_key("cfactory", env={"CFACTORY_API_KEY": "acw_cf_env"}, home=home)
    assert k1 is not None and k1.source == "$CFACTORY_API_KEY" and k1.value == "acw_cf_env"

    k2 = resolve_portal_key("cfactory", env={}, home=home)
    assert k2 is not None and k2.source == "~/.cfactory/.mcp-key" and k2.value == "acw_cf_mcp"

    mcp_file.unlink()
    k3 = resolve_portal_key("cfactory", env={}, home=home)
    assert k3 is not None and k3.source == "~/.cfactory/.token" and k3.value == "acw_cf_token"


def test_url_resolution_order(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('[portals.pfactory]\nurl = "https://pf.custom.example/"\n')

    assert (
        resolve_portal_url(
            "pfactory",
            env={"PFACTORY_API_URL": "http://127.0.0.1:3114/"},
            config_path=cfg,
        )
        == "http://127.0.0.1:3114"
    )
    assert resolve_portal_url("pfactory", env={}, config_path=cfg) == "https://pf.custom.example"
    assert (
        resolve_portal_url("cfactory", env={}, config_path=cfg)
        == "https://cfactory-mcp.freundcloud.org.uk"
    )


# =============================================================================
# 3. URL Policy & Redirect refusal
# =============================================================================


def test_url_policy_rejects_userinfo_and_non_loopback_http() -> None:
    with pytest.raises(InputRejectedError, match="userinfo"):
        validate_cli_url("https://user:pass@pfactory.freundcloud.org.uk/api/health")

    with pytest.raises(InputRejectedError, match="loopback"):
        validate_cli_url("http://pfactory.freundcloud.org.uk/api/health")

    assert (
        validate_cli_url("http://127.0.0.1:8123/api/health") == "http://127.0.0.1:8123/api/health"
    )
    assert (
        validate_cli_url("http://localhost:8123/api/health") == "http://localhost:8123/api/health"
    )


@contextlib.contextmanager
def _fake_http_server(
    handler_fn: Callable[[http.server.BaseHTTPRequestHandler], None],
) -> Iterator[str]:
    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            handler_fn(self)

        def do_POST(self) -> None:
            handler_fn(self)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def test_transport_refuses_redirects() -> None:
    def _redirect(req: http.server.BaseHTTPRequestHandler) -> None:
        req.send_response(302)
        req.send_header("Location", "http://127.0.0.1:9/login")
        req.end_headers()

    with _fake_http_server(_redirect) as base_url:
        transport = PortalTransport(base_url, token=CANARY_KEY)
        resp = transport.request("GET", "/api/health")
        assert resp.status == 302
        assert resp.after_send
        assert "redirect refused" in resp.raw_text


# =============================================================================
# 4. Fake Portal Tests: submit (0, 1, 3, lost-response, dry-run), test, status, doctor
# =============================================================================


def _read_req_json(req: http.server.BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(req.headers.get("Content-Length", "0"))
    raw = req.rfile.read(length) if length else b"{}"
    parsed = json.loads(raw.decode("utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _send_json(req: http.server.BaseHTTPRequestHandler, code: int, body: dict[str, Any]) -> None:
    payload = json.dumps(body).encode("utf-8")
    req.send_response(code)
    req.send_header("Content-Type", "application/json")
    req.send_header("Content-Length", str(len(payload)))
    req.end_headers()
    req.wfile.write(payload)


def test_submit_exit_0_and_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _init_approved_repo(tmp_path)
    calls: list[tuple[str, dict[str, Any]]] = []

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        body = _read_req_json(req)
        calls.append((req.path, body))
        if req.path == "/api/mcp-stdio/plan/sessions/ingest-approved":
            assert body["slug"] == SLUG
            assert len(body["artifacts"]) == 3
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-123",
                    "correlation_key": "pf-sess-123",
                    "status": "reviewed",
                    "deduped": False,
                    "children": [{"key": "C1", "title": "Step one", "kind": "task"}],
                    "readiness": {"hard_failures": []},
                },
            )
            return
        if req.path == "/api/mcp-stdio/plan/sessions/sess-123/approve":
            assert body == {"approver": "factory-cli"}
            _send_json(req, 200, {"session_id": "sess-123", "status": "approved"})
            return
        if req.path == "/api/mcp-stdio/plan/sessions/sess-123/emit-contract":
            is_dry = bool(body.get("dry_run"))
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-123",
                    "correlation_key": "pf-sess-123",
                    "contract_result": {
                        "ok": True,
                        "dry_run": is_dry,
                        "signed": True,
                        "endpoint": "https://aifactory.example/api/tasks/from-plan",
                        "contract": {"feature": "Demo"},
                        "correlation": {"task_id": "demo:spec-1", "project_id": "demo"},
                    },
                },
            )
            return
        _send_json(req, 404, {"detail": "not found"})

    with _fake_http_server(_handler) as base_url:
        env = {"PFACTORY_API_URL": base_url, "PFACTORY_MCP_KEY": CANARY_KEY}
        # Dry run first
        dry_code = main(
            ["submit", f"plan/{SLUG}.md", "--dry-run"],
            cwd=repo,
            env=env,
            home=tmp_path,
        )
        assert dry_code == EXIT_OK
        assert calls[-1] == (
            "/api/mcp-stdio/plan/sessions/sess-123/emit-contract",
            {"dry_run": True},
        )
        dry_out = capsys.readouterr()
        assert "pf:sess-123" in dry_out.out
        assert "Step one" in dry_out.out
        assert CANARY_KEY not in dry_out.out
        assert CANARY_KEY not in dry_out.err

        # Live submit
        live_code = main(
            ["submit", SLUG, "--project", "demo"],
            cwd=repo,
            env=env,
            home=tmp_path,
        )
        assert live_code == EXIT_OK
        assert calls[-1] == (
            "/api/mcp-stdio/plan/sessions/sess-123/emit-contract",
            {"dry_run": False},
        )
        live_out = capsys.readouterr()
        assert "pf:sess-123" in live_out.out
        assert "af:demo:spec-1" in live_out.out
        assert CANARY_KEY not in live_out.out


def test_submit_exit_1_and_canary_redaction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _init_approved_repo(tmp_path)

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        # Echo the canary secret in a 409 error body to prove redaction works everywhere.
        _send_json(
            req,
            409,
            {"detail": f"Live emit refused for key {CANARY_KEY}"},
        )

    with _fake_http_server(_handler) as base_url:
        env = {"PFACTORY_API_URL": base_url, "PFACTORY_MCP_KEY": CANARY_KEY}
        code = main(["submit", SLUG], cwd=repo, env=env, home=tmp_path)
        assert code == EXIT_REJECTED
        captured = capsys.readouterr()
        assert CANARY_KEY not in captured.out
        assert CANARY_KEY not in captured.err
        assert "***REDACTED***" in captured.err

        ctx = RuntimeContext(cwd=repo, env=env, home=tmp_path)
        mcp_json = handle_factory_submit(SLUG, dry_run=False, ctx=ctx)
        assert CANARY_KEY not in mcp_json
        parsed = json.loads(mcp_json)
        assert parsed["outcome"] == "rejected"
        assert "***REDACTED***" in parsed["detail"]


def test_submit_lost_response_makes_exactly_one_emit_post_and_exits_3(
    tmp_path: Path,
) -> None:
    repo = _init_approved_repo(tmp_path)
    emit_posts = 0

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        nonlocal emit_posts
        _ = _read_req_json(req)
        if req.path == "/api/mcp-stdio/plan/sessions/ingest-approved":
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-lost",
                    "correlation_key": "pf-sess-lost",
                    "status": "reviewed",
                    "deduped": False,
                    "children": [{"key": "C1", "title": "Step 1", "kind": "task"}],
                    "readiness": {"hard_failures": []},
                },
            )
            return
        if req.path == "/api/mcp-stdio/plan/sessions/sess-lost/approve":
            _send_json(req, 200, {"session_id": "sess-lost", "status": "approved"})
            return
        if req.path == "/api/mcp-stdio/plan/sessions/sess-lost/emit-contract":
            emit_posts += 1
            # Simulate a 502 / disconnect after the emit request reached PFactory.
            _send_json(req, 502, {"detail": f"upstream timeout with {CANARY_KEY}"})
            return

    with _fake_http_server(_handler) as base_url:
        env = {"PFACTORY_API_URL": base_url, "PFACTORY_MCP_KEY": CANARY_KEY}
        ctx = RuntimeContext(cwd=repo, env=env, home=tmp_path)
        outcome = run_submit(SLUG, dry_run=False, ctx=ctx)
        assert outcome.exit_code == EXIT_UNKNOWN
        assert outcome.outcome == "unknown"
        assert emit_posts == 1
        assert CANARY_KEY not in json.dumps(outcome.payload)
        assert any("outcome unknown" in ln for ln in outcome.lines)


def test_submit_pfactory_outcome_unknown_exits_3(tmp_path: Path) -> None:
    repo = _init_approved_repo(tmp_path)
    emit_posts = 0

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        nonlocal emit_posts
        body = _read_req_json(req)
        if req.path == "/api/mcp-stdio/plan/sessions/ingest-approved":
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-unk",
                    "correlation_key": "pf-sess-unk",
                    "status": "approved",
                    "deduped": False,
                    "children": [],
                    "readiness": {"hard_failures": []},
                },
            )
            return
        if req.path == "/api/mcp-stdio/plan/sessions/sess-unk/approve":
            assert body == {"approver": "factory-cli"}
            _send_json(req, 200, {"session_id": "sess-unk", "status": "approved"})
            return
        if req.path == "/api/mcp-stdio/plan/sessions/sess-unk/emit-contract":
            emit_posts += 1
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-unk",
                    "correlation_key": "pf-sess-unk",
                    "contract_result": {
                        "ok": False,
                        "outcome": "unknown",
                        "errors": ["Task creation outcome unknown"],
                    },
                },
            )
            return

    with _fake_http_server(_handler) as base_url:
        env = {"PFACTORY_API_URL": base_url, "PFACTORY_MCP_KEY": CANARY_KEY}
        ctx = RuntimeContext(cwd=repo, env=env, home=tmp_path)
        outcome = run_submit(SLUG, dry_run=False, ctx=ctx)
        assert outcome.exit_code == EXIT_UNKNOWN
        assert outcome.outcome == "unknown"
        assert emit_posts == 1


def test_factory_test_ingest_and_404_parity(tmp_path: Path) -> None:
    repo = _init_approved_repo(tmp_path)
    received: list[dict[str, Any]] = []

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        body = _read_req_json(req)
        received.append(body)
        if body["project_id"] in ("unknown-proj", "invisible-proj"):
            _send_json(req, 404, {"detail": "Project not found"})
            return
        _send_json(
            req,
            200,
            {
                "workspace_project_id": "proj-uuid-1",
                "spec_id": body["spec_id"],
                "source_sha": "deadbeef" * 5,
                "planner_scheduled": False,
                "planner_reason": "auto_plan_disabled",
            },
        )

    with _fake_http_server(_handler) as base_url:
        env = {"TFACTORY_API_URL": base_url, "TFACTORY_MCP_KEY": CANARY_KEY}
        ctx = RuntimeContext(cwd=repo, env=env, home=tmp_path)
        ok_out = run_test(
            "my-proj",
            "feat/3865-demo",
            spec_slug=SLUG,
            pr_number=42,
            ctx=ctx,
        )
        assert ok_out.exit_code == EXIT_OK
        assert received[-1]["no_register"] is True
        assert received[-1]["pr_number"] == 42
        assert "## Acceptance Criteria" in received[-1]["spec_text"]
        assert "- AC1: check one" in received[-1]["spec_text"]
        assert ok_out.payload["planner_reason"] == "auto_plan_disabled"
        assert ok_out.payload["sha_mismatch"] is True
        assert any("warning:" in ln for ln in ok_out.lines)

        # Unknown and invisible project both produce identical "project not found" and exit 1
        unk_out = run_test("unknown-proj", "feat/3865-demo", spec_slug=SLUG, ctx=ctx)
        inv_out = run_test("invisible-proj", "feat/3865-demo", spec_slug=SLUG, ctx=ctx)
        assert unk_out.exit_code == EXIT_REJECTED
        assert inv_out.exit_code == EXIT_REJECTED
        assert (
            unk_out.payload
            == inv_out.payload
            == {
                "outcome": "rejected",
                "detail": "project not found",
            }
        )
        assert unk_out.lines == inv_out.lines == ("error: project not found",)


def test_run_id_bounds_and_criteria_rewriting() -> None:
    long_slug = "2026-11-23-3865-Very_Long_Slug_Name_Exceeding_Sixty_Four_Characters_Easily"
    rid = build_run_id(long_slug, "abcdef123456")
    assert len(rid) <= 64
    assert all(ch in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in rid)

    raw_spec = (
        "---\nstatus: approved\n---\n# Spec\n"
        "## Verification\n- top one:\n  - sub a\n  - sub b\n- top two\n"
    )
    bullets = extract_verification_bullets(
        raw_spec,
        require_verification_heading=True,
    )
    assert bullets == ["top one; sub a; sub b", "top two"]
    md = format_acceptance_criteria_markdown("demo", bullets)
    assert "- AC1: top one; sub a; sub b" in md
    assert "- AC2: top two" in md


def test_factory_status_pf_af_tf_and_cf(tmp_path: Path) -> None:
    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        if req.path == "/api/mcp-stdio/plan/sessions/s1":
            _send_json(
                req,
                200,
                {
                    "session_id": "s1",
                    "status": "emitted",
                    "correlation_key": "pf-s1",
                    "contract_result": {
                        "ok": True,
                        "correlation": {"task_id": "p1:t1", "project_id": "p1"},
                    },
                },
            )
            return
        if req.path == "/api/mcp-stdio/tasks/p1%3At1":
            _send_json(req, 200, {"id": "p1:t1", "status": "in_progress", "title": "Build CLI"})
            return
        if req.path == "/api/mcp-stdio/spec-tasks/p1/sp1":
            _send_json(
                req,
                200,
                {"project_id": "p1", "spec_id": "sp1", "status_json": {"status": "triaged"}},
            )
            return
        if req.path == "/api/workitems/Factory%233865":
            if req.headers.get("Authorization") == "Bearer acw_denied":
                _send_json(req, 403, {"detail": "forbidden"})
                return
            _send_json(req, 200, {"correlation_key": "Factory#3865", "status": "verifying"})
            return
        _send_json(req, 404, {"detail": f"secret detail {CANARY_KEY}"})

    with _fake_http_server(_handler) as base_url:
        env = {
            "PFACTORY_API_URL": base_url,
            "AIFACTORY_API_URL": base_url,
            "TFACTORY_API_URL": base_url,
            "CFACTORY_API_URL": base_url,
            "PFACTORY_MCP_KEY": CANARY_KEY,
            "AIFACTORY_MCP_KEY": CANARY_KEY,
            "TFACTORY_MCP_KEY": CANARY_KEY,
        }
        ctx = RuntimeContext(env=env, home=tmp_path)
        # pf: follows contract_result to AIFactory
        pf_out = run_status("pf:s1", ctx=ctx)
        assert pf_out.exit_code == EXIT_OK
        assert pf_out.payload["pfactory_status"] == "emitted"
        assert pf_out.payload["aifactory_task"]["status"] == "in_progress"

        # af:
        af_out = run_status("af:p1:t1", ctx=ctx)
        assert af_out.exit_code == EXIT_OK
        assert af_out.payload["aifactory_status"] == "in_progress"

        # tf:
        tf_out = run_status("tf:p1/sp1", ctx=ctx)
        assert tf_out.exit_code == EXIT_OK
        assert tf_out.payload["tfactory_status"] == "triaged"

        # Bare correlation key without CFactory key -> exit 2 "use pf:/af:/tf: ids"
        no_cf = run_status("Factory#3865", ctx=ctx)
        assert no_cf.exit_code == EXIT_PRECONDITION
        assert "use pf:/af:/tf: ids" in no_cf.payload["detail"]

        # Bare correlation key with 403 -> exit 2 "use pf:/af:/tf: ids"
        denied_cf = run_status(
            "Factory#3865",
            ctx=RuntimeContext(env={**env, "CFACTORY_API_KEY": "acw_denied"}, home=tmp_path),
        )
        assert denied_cf.exit_code == EXIT_PRECONDITION
        assert "use pf:/af:/tf: ids" in denied_cf.payload["detail"]

        # Bare correlation key with valid CFactory key -> 200
        ok_cf = run_status(
            "Factory#3865",
            ctx=RuntimeContext(env={**env, "CFACTORY_API_KEY": CANARY_KEY}, home=tmp_path),
        )
        assert ok_cf.exit_code == EXIT_OK
        assert ok_cf.payload["workitem"]["status"] == "verifying"

        # 404 -> "not found" without leaking portal detail
        not_found = run_status("af:p1:missing", ctx=ctx)
        assert not_found.exit_code == EXIT_REJECTED
        assert not_found.payload["detail"] == "not found"
        assert not_found.lines == ("not found",)
        assert CANARY_KEY not in json.dumps(not_found.payload)


def test_factory_doctor_against_fake_server(tmp_path: Path) -> None:
    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        if req.path in ("/api/health", "/health"):
            _send_json(req, 200, {"status": "healthy", "version": "3.2.1"})
            return
        if req.path in ("/api/mcp-stdio/projects", "/api/workitems"):
            _send_json(req, 200, {"items": []})
            return
        _send_json(req, 404, {})

    with _fake_http_server(_handler) as base_url:
        env = {
            "PFACTORY_API_URL": base_url,
            "AIFACTORY_API_URL": base_url,
            "TFACTORY_API_URL": base_url,
            "CFACTORY_API_URL": base_url,
            "PFACTORY_MCP_KEY": CANARY_KEY,
            "AIFACTORY_MCP_KEY": CANARY_KEY,
            "TFACTORY_MCP_KEY": CANARY_KEY,
            "CFACTORY_API_KEY": CANARY_KEY,
        }
        doc_json = handle_factory_doctor(ctx=RuntimeContext(env=env, home=tmp_path))
        assert CANARY_KEY not in doc_json
        doc = json.loads(doc_json)
        assert doc["outcome"] == "ok"
        assert doc["portals"]["pfactory"]["key_source"] == "$PFACTORY_MCP_KEY"
        assert doc["portals"]["pfactory"]["key_kind"] == "acw"
        assert doc["portals"]["pfactory"]["health_version"] == "3.2.1"
        assert doc["portals"]["pfactory"]["protected_read"] == "ok"


# =============================================================================
# 5. mcp-config: secret-free output, --write refusal, --force TOML/JSON, .bak 0600
# =============================================================================


def test_mcp_config_output_is_secret_free_for_all_agents() -> None:
    for agent in AGENTS:
        snippet = render_snippet(agent)
        assert "factory" in snippet
        assert "mcp" in snippet
        assert "acw_" not in snippet
        assert "KEY" not in snippet
        assert "TOKEN" not in snippet
        if agent == "codex":
            parsed = tomllib.loads(snippet)
            assert parsed["mcp_servers"]["factory"] == {
                "command": "factory",
                "args": ["mcp"],
            }
        else:
            parsed_json = json.loads(snippet)
            assert parsed_json["mcpServers"]["factory"] == {
                "command": "factory",
                "args": ["mcp"],
            }


def test_mcp_config_write_refusal_force_backup_and_mode_codex(tmp_path: Path) -> None:
    codex_cfg = tmp_path / ".codex" / "config.toml"
    codex_cfg.parent.mkdir(parents=True)
    initial_toml = (
        'model = "gpt-5"\n\n'
        "[mcp_servers.alpha]\n"
        'command = "alpha-mcp"\n'
        'args = ["serve"]\n\n'
        "[mcp_servers.factory]\n"
        'command = "old-factory"\n'
        'args = ["old"]\n\n'
        "[mcp_servers.factory.env]\n"
        'FOO = "bar"\n\n'
        "[mcp_servers.omega]\n"
        'command = "omega-mcp"\n'
        'args = ["--stdio"]\n'
    )
    codex_cfg.write_text(initial_toml, encoding="utf-8")
    codex_cfg.chmod(0o640)

    # Refused without --force
    refused = run_mcp_config("codex", write=True, force=False, target_path=codex_cfg)
    assert refused.exit_code == EXIT_PRECONDITION
    assert "already exists" in refused.text
    assert codex_cfg.read_text(encoding="utf-8") == initial_toml

    # Replaced with --force, keeping sibling tables intact, valid TOML, .bak 0600, mode 0640
    forced = run_mcp_config("codex", write=True, force=True, target_path=codex_cfg)
    assert forced.exit_code == EXIT_OK

    bak = codex_cfg.with_name("config.toml.bak")
    assert bak.is_file()
    assert (bak.stat().st_mode & 0o777) == 0o600
    assert bak.read_text(encoding="utf-8") == initial_toml
    assert (codex_cfg.stat().st_mode & 0o777) == 0o640

    updated_toml = codex_cfg.read_text(encoding="utf-8")
    parsed = tomllib.loads(updated_toml)
    assert parsed["model"] == "gpt-5"
    assert parsed["mcp_servers"]["alpha"]["command"] == "alpha-mcp"
    assert parsed["mcp_servers"]["omega"]["command"] == "omega-mcp"
    assert parsed["mcp_servers"]["factory"] == {"command": "factory", "args": ["mcp"]}
    assert "env" not in parsed["mcp_servers"]["factory"]


def test_mcp_config_write_json_agents(tmp_path: Path) -> None:
    claude_cfg = tmp_path / ".mcp.json"
    claude_cfg.write_text(
        json.dumps({"mcpServers": {"other": {"command": "other", "args": []}}}),
        encoding="utf-8",
    )
    claude_cfg.chmod(0o644)

    res1 = run_mcp_config("claude", write=True, force=False, target_path=claude_cfg)
    assert res1.exit_code == EXIT_OK
    parsed1 = json.loads(claude_cfg.read_text(encoding="utf-8"))
    assert "other" in parsed1["mcpServers"]
    assert parsed1["mcpServers"]["factory"] == {"command": "factory", "args": ["mcp"]}

    # Second write without --force is refused
    res2 = run_mcp_config("claude", write=True, force=False, target_path=claude_cfg)
    assert res2.exit_code == EXIT_PRECONDITION


# =============================================================================
# 6. Vendor drift test & lazy `mcp` import check
# =============================================================================


def test_vendored_factory_common_matches_canonical() -> None:
    vendor_dir = _PKG_ROOT / "factory_cli" / "_vendor" / "factory_common"
    canonical_dir = _PKG_ROOT.parent / "factory-common" / "factory_common"
    if not canonical_dir.is_dir():
        pytest.skip("canonical shared/factory-common tree not adjacent (installed wheel)")

    canonical_files = sorted(p.name for p in canonical_dir.glob("*.py"))
    vendor_files = sorted(p.name for p in vendor_dir.glob("*.py"))
    assert vendor_files == canonical_files
    for name in canonical_files:
        assert (vendor_dir / name).read_bytes() == (canonical_dir / name).read_bytes(), (
            f"vendored {name} drifted from shared/factory-common/factory_common/{name}"
        )


def test_mcp_is_imported_only_in_mcp_server_module() -> None:
    pkg_dir = _PKG_ROOT / "factory_cli"
    for py_file in sorted(pkg_dir.glob("*.py")):
        if py_file.name == "mcp_server.py":
            continue
        text = py_file.read_text(encoding="utf-8")
        assert "import mcp" not in text and "from mcp" not in text, (
            f"{py_file.name} must not import the `mcp` SDK at module scope"
        )


def test_redact_text_handles_canary_and_patterns() -> None:
    raw = (
        f"Authorization: Bearer {CANARY_KEY} and " + "ghp_" + "123456789012345678901234567890123456"
    )
    cleaned = redact_text(raw, (CANARY_KEY,))
    assert CANARY_KEY not in cleaned
    assert "ghp_" not in cleaned


def test_submit_exit_2_on_precondition_failure_and_mcp_server_build(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["submit", SLUG], cwd=tmp_path, env={}, home=tmp_path)
    assert code == EXIT_PRECONDITION
    captured = capsys.readouterr()
    assert "not a git worktree" in captured.err

    ctx = RuntimeContext(cwd=tmp_path, env={}, home=tmp_path)
    test_res = json.loads(handle_factory_test("proj", "main", spec=SLUG, ctx=ctx))
    assert test_res["outcome"] == "rejected"

    status_res = json.loads(handle_factory_status("Factory#3865", ctx=ctx))
    assert status_res["outcome"] == "rejected"
    assert "use pf:/af:/tf: ids" in status_res["detail"]

    server = build_mcp_server()
    assert server is not None


# =============================================================================
# 7. Round-1 Review Tests (Items 1-19 and Missing Tests)
# =============================================================================


def test_loopback_http_resolves_ip_and_ignores_env_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_getaddrinfo(host: str, port: int, *_args: Any, **_kw: Any) -> list[Any]:
        if host == "127.evil.example":
            return [(2, 1, 6, "", ("93.184.216.34", port))]
        if host == "dual.local.example":
            return [
                (2, 1, 6, "", ("127.0.0.1", port)),
                (2, 1, 6, "", ("10.0.0.5", port)),
            ]
        return [(2, 1, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr("socket.getaddrinfo", _fake_getaddrinfo)
    with pytest.raises(InputRejectedError, match="loopback"):
        validate_cli_url("http://127.evil.example:8080/api/health")
    with pytest.raises(InputRejectedError, match="loopback"):
        validate_cli_url("http://dual.local.example:8080/api/health")

    assert validate_cli_url("http://127.0.0.254:8080/api/health") == (
        "http://127.0.0.254:8080/api/health"
    )
    assert validate_cli_url("http://[::1]:8080/api/health") == "http://[::1]:8080/api/health"

    with pytest.raises(InputRejectedError, match="query"):
        PortalTransport("http://127.0.0.1:8080/api?foo=1")
    with pytest.raises(InputRejectedError, match="fragment"):
        PortalTransport("http://127.0.0.1:8080/api#frag")

    def _ok_handler(req: http.server.BaseHTTPRequestHandler) -> None:
        _send_json(req, 200, {"ok": True})

    with _fake_http_server(_ok_handler) as base_url:
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
        transport = PortalTransport(base_url, token=CANARY_KEY)
        resp = transport.request("GET", "/api/health")
        assert resp.status == 200
        assert resp.data == {"ok": True}


def test_submit_mid_body_truncation_and_close_before_response_exit_3(
    tmp_path: Path,
) -> None:
    repo = _init_approved_repo(tmp_path)
    mode = "truncate"

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        _ = _read_req_json(req)
        if req.path == "/api/mcp-stdio/plan/sessions/ingest-approved":
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-net",
                    "correlation_key": "pf-sess-net",
                    "status": "reviewed",
                    "deduped": False,
                    "children": [],
                    "readiness": {"hard_failures": []},
                },
            )
            return
        if req.path == "/api/mcp-stdio/plan/sessions/sess-net/approve":
            _send_json(req, 200, {"session_id": "sess-net", "status": "approved"})
            return
        if req.path == "/api/mcp-stdio/plan/sessions/sess-net/emit-contract":
            if mode == "truncate":
                req.send_response(200)
                req.send_header("Content-Type", "application/json")
                req.send_header("Content-Length", "500")
                req.end_headers()
                req.wfile.write(b'{"session_id": "sess-net", "partial": ')
                req.wfile.flush()
                req.close_connection = True
                return
            if mode == "close_before_status":
                req.close_connection = True
                return
            if mode == "non_json_200":
                body_bytes = b"<html><body>Gateway 200 page</body></html>"
                req.send_response(200)
                req.send_header("Content-Type", "text/html")
                req.send_header("Content-Length", str(len(body_bytes)))
                req.end_headers()
                req.wfile.write(body_bytes)
                return

    with _fake_http_server(_handler) as base_url:
        env = {"PFACTORY_API_URL": base_url, "PFACTORY_MCP_KEY": CANARY_KEY}
        ctx = RuntimeContext(cwd=repo, env=env, home=tmp_path)

        out_trunc = run_submit(SLUG, dry_run=False, ctx=ctx)
        assert out_trunc.exit_code == EXIT_UNKNOWN
        assert out_trunc.outcome == "unknown"
        assert out_trunc.payload["session_id"] == "sess-net"
        assert out_trunc.payload["correlation_key"] == "pf-sess-net"
        assert any("pf:sess-net" in ln for ln in out_trunc.lines)
        assert any("pf-sess-net" in ln for ln in out_trunc.lines)

        mode = "close_before_status"
        out_close = run_submit(SLUG, dry_run=False, ctx=ctx)
        assert out_close.exit_code == EXIT_UNKNOWN
        assert out_close.outcome == "unknown"
        assert out_close.payload["session_id"] == "sess-net"
        assert out_close.payload["correlation_key"] == "pf-sess-net"

        mode = "non_json_200"
        out_html = run_submit(SLUG, dry_run=False, ctx=ctx)
        assert out_html.exit_code == EXIT_UNKNOWN
        assert out_html.outcome == "unknown"
        assert out_html.payload["session_id"] == "sess-net"
        assert out_html.payload["correlation_key"] == "pf-sess-net"


def test_full_ingest_approved_body_shape_and_bounds(tmp_path: Path) -> None:
    repo = _init_approved_repo(tmp_path)
    captured_ingest: dict[str, Any] = {}

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        body = _read_req_json(req)
        if req.path == "/api/mcp-stdio/plan/sessions/ingest-approved":
            captured_ingest.update(body)
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-shape",
                    "correlation_key": "pf-sess-shape",
                    "status": "reviewed",
                    "deduped": False,
                    "children": [],
                    "readiness": {"hard_failures": ["ac-child-coverage"]},
                },
            )
            return

    with _fake_http_server(_handler) as base_url:
        env = {"PFACTORY_API_URL": base_url, "PFACTORY_MCP_KEY": CANARY_KEY}
        ctx = RuntimeContext(cwd=repo, env=env, home=tmp_path)
        out = run_submit(SLUG, project_id="proj-1", dry_run=True, ctx=ctx)
        assert out.exit_code == EXIT_REJECTED
        assert out.payload["session_id"] == "sess-shape"
        assert out.payload["correlation_key"] == "pf-sess-shape"
        assert any("pf:sess-shape" in ln for ln in out.lines)

    assert set(captured_ingest.keys()) == {
        "slug",
        "provider",
        "repo",
        "base_ref",
        "branch",
        "head_sha",
        "project_id",
        "artifacts",
    }
    assert captured_ingest["slug"] == SLUG
    assert captured_ingest["provider"] == "github"
    assert captured_ingest["repo"] == "owner/demo-repo"
    assert captured_ingest["base_ref"] == "main"
    assert captured_ingest["branch"] == "feat/3865-demo"
    assert len(captured_ingest["head_sha"]) == 40
    assert captured_ingest["project_id"] == "proj-1"
    arts = captured_ingest["artifacts"]
    assert [a["stage"] for a in arts] == ["intent", "spec", "plan"]
    for art in arts:
        assert set(art.keys()) == {
            "stage",
            "path",
            "content",
            "blob_sha",
            "approve_commit_sha",
            "approve_commit_author",
        }
        assert len(art["blob_sha"]) == 40
        assert len(art["approve_commit_sha"]) == 40
        assert 1 <= len(art["approve_commit_author"]) <= 200
        assert art["approve_commit_author"].isprintable()
        assert len(art["path"]) <= 512
        assert ".." not in art["path"]


@pytest.mark.parametrize("session_status", ["approved", "emitted"])
def test_deduped_session_rerun_skips_approve_and_calls_emit_contract(
    tmp_path: Path,
    session_status: str,
) -> None:
    repo = _init_approved_repo(tmp_path)
    called_paths: list[str] = []

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        _ = _read_req_json(req)
        called_paths.append(req.path)
        if req.path == "/api/mcp-stdio/plan/sessions/ingest-approved":
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-emitted",
                    "correlation_key": "pf-sess-emitted",
                    "status": session_status,
                    "deduped": True,
                    "children": [{"key": "C1", "title": "Step 1", "kind": "task"}],
                    "readiness": {"hard_failures": []},
                },
            )
            return
        if req.path == "/api/mcp-stdio/plan/sessions/sess-emitted/emit-contract":
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-emitted",
                    "correlation_key": "pf-sess-emitted",
                    "contract_result": {
                        "ok": True,
                        "correlation": {"task_id": "task-stored-1", "project_id": "demo"},
                    },
                },
            )
            return
        _send_json(req, 409, {"detail": "approve should not be called on emitted session"})

    with _fake_http_server(_handler) as base_url:
        env = {"PFACTORY_API_URL": base_url, "PFACTORY_MCP_KEY": CANARY_KEY}
        ctx = RuntimeContext(cwd=repo, env=env, home=tmp_path)
        out = run_submit(SLUG, dry_run=False, ctx=ctx)
        assert out.exit_code == EXIT_OK
        assert called_paths == [
            "/api/mcp-stdio/plan/sessions/ingest-approved",
            "/api/mcp-stdio/plan/sessions/sess-emitted/emit-contract",
        ]
        assert out.payload["aifactory_task_id"] == "task-stored-1"
        assert "aifactory_task_id: af:task-stored-1" in out.lines


def test_approve_and_emit_4xx_keep_session_id_and_correlation_key(
    tmp_path: Path,
) -> None:
    repo = _init_approved_repo(tmp_path)
    fail_stage = "approve"

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        _ = _read_req_json(req)
        if req.path == "/api/mcp-stdio/plan/sessions/ingest-approved":
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-4xx",
                    "correlation_key": "pf-sess-4xx",
                    "status": "reviewed",
                    "deduped": False,
                    "children": [],
                    "readiness": {"hard_failures": []},
                },
            )
            return
        if req.path == "/api/mcp-stdio/plan/sessions/sess-4xx/approve":
            if fail_stage == "approve":
                _send_json(req, 409, {"detail": "legacy token cannot approve"})
                return
            _send_json(req, 200, {"session_id": "sess-4xx", "status": "approved"})
            return
        if req.path == "/api/mcp-stdio/plan/sessions/sess-4xx/emit-contract":
            _send_json(req, 422, {"detail": "missing project on session"})
            return

    with _fake_http_server(_handler) as base_url:
        env = {"PFACTORY_API_URL": base_url, "PFACTORY_MCP_KEY": CANARY_KEY}
        ctx = RuntimeContext(cwd=repo, env=env, home=tmp_path)

        out_app = run_submit(SLUG, dry_run=False, ctx=ctx)
        assert out_app.exit_code == EXIT_REJECTED
        assert out_app.payload["session_id"] == "sess-4xx"
        assert out_app.payload["correlation_key"] == "pf-sess-4xx"
        assert "session_id: pf:sess-4xx" in out_app.lines
        assert "correlation_key: pf-sess-4xx" in out_app.lines

        fail_stage = "emit"
        out_emit = run_submit(SLUG, dry_run=False, ctx=ctx)
        assert out_emit.exit_code == EXIT_REJECTED
        assert out_emit.payload["session_id"] == "sess-4xx"
        assert out_emit.payload["correlation_key"] == "pf-sess-4xx"
        assert "session_id: pf:sess-4xx" in out_emit.lines
        assert "correlation_key: pf-sess-4xx" in out_emit.lines


def test_exit_codes_redirect_after_send_unknown_url_error_precondition(tmp_path: Path) -> None:
    repo = _init_approved_repo(tmp_path)

    def _redirect(req: http.server.BaseHTTPRequestHandler) -> None:
        req.send_response(302)
        req.send_header("Location", "https://login.example.com")
        req.end_headers()

    with _fake_http_server(_redirect) as base_url:
        env = {
            "PFACTORY_API_URL": base_url,
            "TFACTORY_API_URL": base_url,
            "PFACTORY_MCP_KEY": CANARY_KEY,
            "TFACTORY_MCP_KEY": CANARY_KEY,
        }
        ctx = RuntimeContext(cwd=repo, env=env, home=tmp_path)
        sub_out = run_submit(SLUG, dry_run=True, ctx=ctx)
        assert sub_out.exit_code == EXIT_UNKNOWN

        test_out = run_test("proj", "feat/3865-demo", spec_slug=SLUG, ctx=ctx)
        assert test_out.exit_code == EXIT_UNKNOWN

    bad_env = {
        "PFACTORY_API_URL": "http://pfactory.freundcloud.org.uk",
        "TFACTORY_API_URL": "http://tfactory.freundcloud.org.uk",
        "PFACTORY_MCP_KEY": CANARY_KEY,
        "TFACTORY_MCP_KEY": CANARY_KEY,
    }
    bad_ctx = RuntimeContext(cwd=repo, env=bad_env, home=tmp_path)
    assert run_submit(SLUG, dry_run=True, ctx=bad_ctx).exit_code == EXIT_PRECONDITION
    assert run_test("proj", "feat/3865-demo", spec_slug=SLUG, ctx=bad_ctx).exit_code == (
        EXIT_PRECONDITION
    )


def test_key_with_newline_is_rejected_without_leaking_to_cli_or_mcp(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _init_approved_repo(tmp_path)
    key = "acw_" + "SECRET12345678" + "\nLEAK_SUFFIX"
    env = {
        "PFACTORY_MCP_KEY": key,
        "AIFACTORY_MCP_KEY": key,
        "TFACTORY_MCP_KEY": key,
        "CFACTORY_API_KEY": key,
    }
    ctx = RuntimeContext(cwd=repo, env=env, home=tmp_path)
    commands = (
        ["status", "af:task"],
        ["submit", SLUG],
        ["test", "--project", "p", "--spec", SLUG, "--branch", "feat/3865-demo"],
        ["doctor"],
    )
    for argv in commands:
        assert main(argv, cwd=repo, env=env, home=tmp_path) == EXIT_PRECONDITION
        captured = capsys.readouterr()
        assert key not in captured.out + captured.err
        assert "LEAK_SUFFIX" not in captured.out + captured.err
        assert "MCP_KEY" in captured.err or "API_KEY" in captured.err

    mcp_results = (
        handle_factory_status("af:task", ctx=ctx),
        handle_factory_submit(SLUG, ctx=ctx),
        handle_factory_test("p", "feat/3865-demo", spec=SLUG, ctx=ctx),
        handle_factory_doctor(ctx=ctx),
    )
    for result in mcp_results:
        assert json.loads(result)["outcome"] == "rejected"
        assert key not in result
        assert "LEAK_SUFFIX" not in result


def test_redaction_strips_server_controls_and_acw_pattern() -> None:
    assert redact_text("\x1b[31m acw_secret12345\nline") == " ***REDACTED***line"


@pytest.mark.parametrize("fail_stage", ["ingest", "approve"])
def test_submit_5xx_after_send_is_unknown_at_every_stage(tmp_path: Path, fail_stage: str) -> None:
    repo = _init_approved_repo(tmp_path)

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        _ = _read_req_json(req)
        if fail_stage == "ingest" or req.path.endswith("/approve"):
            _send_json(req, 503, {"detail": "temporarily unavailable"})
        else:
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-stage",
                    "status": "reviewed",
                    "deduped": False,
                    "readiness": {"hard_failures": []},
                },
            )

    with _fake_http_server(_handler) as base_url:
        ctx = RuntimeContext(
            cwd=repo,
            env={"PFACTORY_API_URL": base_url, "PFACTORY_MCP_KEY": CANARY_KEY},
            home=tmp_path,
        )
        outcome = run_submit(SLUG, ctx=ctx)
        assert outcome.exit_code == EXIT_UNKNOWN
        assert outcome.payload["session_id"] == ("sess-stage" if fail_stage == "approve" else None)


def test_emit_409_in_progress_is_unknown_with_status_hint(tmp_path: Path) -> None:
    repo = _init_approved_repo(tmp_path)

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        _ = _read_req_json(req)
        if req.path.endswith("/emit-contract"):
            _send_json(req, 409, {"detail": "Emission in progress"})
        elif req.path.endswith("/approve"):
            _send_json(req, 200, {"session_id": "sess-busy"})
        else:
            _send_json(
                req,
                200,
                {
                    "session_id": "sess-busy",
                    "status": "reviewed",
                    "deduped": False,
                    "readiness": {"hard_failures": []},
                },
            )

    with _fake_http_server(_handler) as base_url:
        ctx = RuntimeContext(
            cwd=repo,
            env={"PFACTORY_API_URL": base_url, "PFACTORY_MCP_KEY": CANARY_KEY},
            home=tmp_path,
        )
        outcome = run_submit(SLUG, ctx=ctx)
        assert outcome.exit_code == EXIT_UNKNOWN
        assert "factory status pf:sess-busy" in "\n".join(outcome.lines)


def test_doctor_classifies_denied_unreachable_and_non_json(tmp_path: Path) -> None:
    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        if req.path.endswith("health"):
            req.send_response(200)
            req.end_headers()
            req.wfile.write(b"healthy")
        else:
            _send_json(req, 503 if req.path == "/api/workitems" else 401, {"detail": "unavailable"})

    with _fake_http_server(_handler) as base_url:
        env = {
            f"{portal.upper()}_API_URL": base_url
            for portal in ("pfactory", "aifactory", "tfactory", "cfactory")
        }
        env.update(
            {
                f"{portal.upper()}_MCP_KEY": CANARY_KEY
                for portal in ("pfactory", "aifactory", "tfactory")
            }
        )
        env["CFACTORY_API_KEY"] = CANARY_KEY
        outcome = run_doctor(ctx=RuntimeContext(env=env, home=tmp_path))
        assert outcome.exit_code != EXIT_OK
        assert outcome.payload["portals"]["pfactory"]["protected_read"] == "denied"
        assert outcome.payload["portals"]["cfactory"]["protected_read"] == "unreachable"
        assert outcome.payload["portals"]["pfactory"]["health_version"] == "reachable (not JSON)"


def test_status_validation_3xx_handling_cfactory_401_and_partial_pf_followup(
    tmp_path: Path,
) -> None:
    ctx_empty = RuntimeContext(env={}, home=tmp_path)
    for bad_target in ("pf:.", "pf:..", "af:../x", "tf:proj/..", "tf:a/b/c", "pf:a b", "bad/key"):
        res = run_status(bad_target, ctx=ctx_empty)
        assert res.exit_code == EXIT_PRECONDITION

    af_mode = "404"

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        if req.path == "/api/mcp-stdio/plan/sessions/s-partial":
            _send_json(
                req,
                200,
                {
                    "session_id": "s-partial",
                    "status": "emitted",
                    "correlation_key": "pf-s-partial",
                    "contract_result": {
                        "ok": True,
                        "correlation": {"task_id": "bare-task-99", "project_id": "p1"},
                    },
                },
            )
            return
        if req.path == "/api/mcp-stdio/tasks/bare-task-99":
            if af_mode == "404":
                _send_json(req, 404, {"detail": "Task missing"})
                return
            if af_mode == "302":
                req.send_response(302)
                req.send_header("Location", "https://sso.example/login")
                req.end_headers()
                return
            _send_json(req, 200, {"id": "bare-task-99", "status": "completed"})
            return
        if req.path == "/api/mcp-stdio/tasks/redir-task":
            req.send_response(307)
            req.send_header("Location", "https://sso.example/login")
            req.end_headers()
            return
        if req.path == "/api/workitems/Factory%233865":
            _send_json(req, 401, {"detail": "unauthorized"})
            return
        _send_json(req, 404, {"detail": "not found"})

    with _fake_http_server(_handler) as base_url:
        env = {
            "PFACTORY_API_URL": base_url,
            "AIFACTORY_API_URL": base_url,
            "CFACTORY_API_URL": base_url,
            "PFACTORY_MCP_KEY": CANARY_KEY,
            "AIFACTORY_MCP_KEY": CANARY_KEY,
            "CFACTORY_API_KEY": CANARY_KEY,
        }
        ctx = RuntimeContext(env=env, home=tmp_path)

        redir_out = run_status("af:redir-task", ctx=ctx)
        assert redir_out.exit_code == EXIT_REJECTED
        assert "redirect refused" in redir_out.payload["detail"]

        cf_401 = run_status("Factory#3865", ctx=ctx)
        assert cf_401.exit_code == EXIT_PRECONDITION
        assert "use pf:/af:/tf: ids" in cf_401.payload["detail"]

        pf_404 = run_status("pf:s-partial", ctx=ctx)
        assert pf_404.exit_code == EXIT_REJECTED
        assert "pfactory_session: pf:s-partial" in pf_404.lines
        assert "pfactory_status: emitted" in pf_404.lines
        assert "aifactory_task_id: af:bare-task-99" in pf_404.lines
        assert any("not found" in ln for ln in pf_404.lines)

        af_mode = "302"
        pf_302 = run_status("pf:s-partial", ctx=ctx)
        assert pf_302.exit_code == EXIT_REJECTED
        assert "pfactory_session: pf:s-partial" in pf_302.lines
        assert any("redirect refused" in ln for ln in pf_302.lines)

        af_mode = "200"
        pf_ok = run_status("pf:s-partial", ctx=ctx)
        assert pf_ok.exit_code == EXIT_OK
        assert pf_ok.payload["aifactory_task_id"] == "bare-task-99"
        assert "aifactory_task_id: af:bare-task-99" in pf_ok.lines


def test_git_ls_remote_default_base_branch_and_unknown_branch(tmp_path: Path) -> None:
    bare = tmp_path / "origin.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "-b", "trunk")

    repo = _init_approved_repo(tmp_path)
    _git(repo, "remote", "set-url", "origin", str(bare))
    _git(repo, "push", "origin", "HEAD:refs/heads/trunk")
    _git(repo, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")

    identity = resolve_repo_identity(repo)
    assert identity.base_ref == "trunk"

    ctx = RuntimeContext(
        cwd=repo,
        env={"TFACTORY_MCP_KEY": CANARY_KEY},
        home=tmp_path,
    )
    bad_branch_out = run_test("proj", "nonexistent-branch-xyz", spec_slug=SLUG, ctx=ctx)
    assert bad_branch_out.exit_code == EXIT_PRECONDITION
    assert "unknown branch" in bad_branch_out.payload["detail"]


def test_detached_head_and_deleted_readded_artifact(tmp_path: Path) -> None:
    repo = _init_approved_repo(tmp_path)
    spec = repo / "spec" / f"{SLUG}.md"
    original = spec.read_text()
    spec.unlink()
    _git(repo, "add", str(spec.relative_to(repo)))
    _git(repo, "commit", "-m", "test: delete spec")
    spec.write_text(original)
    _git(repo, "add", str(spec.relative_to(repo)))
    _git(repo, "commit", "-m", "test: restore spec")
    identity = resolve_repo_identity(repo, base_ref="main")
    assert len(verify_and_load_artifacts(repo, SLUG, head_sha=identity.head_sha)) == 3

    _git(repo, "checkout", "--detach")
    with pytest.raises(PreconditionError, match="detached HEAD"):
        resolve_repo_identity(repo, base_ref="main")


def test_verification_heading_exact_match_and_subheadings(tmp_path: Path) -> None:
    spec_text = (
        "---\nstatus: approved\n---\n# Spec\n\n"
        "## Verification Plan\n- should NOT be picked up\n\n"
        "## Verification\n"
        "### Unit checks\n"
        "- unit one\n"
        "  - sub unit\n"
        "### Integration checks\n"
        "- int two\n\n"
        "## Rollback\n"
        "- rollback bullet ignored\n"
    )
    bullets = extract_verification_bullets(spec_text, require_verification_heading=True)
    assert bullets == ["unit one; sub unit", "int two"]

    repo = _init_approved_repo(tmp_path)
    empty_spec = repo / "spec" / "empty-ver.md"
    empty_spec.write_text("---\nstatus: approved\n---\n# Spec\n## Verification\nNo bullets.\n")
    ctx = RuntimeContext(
        cwd=repo,
        env={"TFACTORY_MCP_KEY": CANARY_KEY},
        home=tmp_path,
    )
    no_crit = run_test("proj", "feat/3865-demo", spec_slug="empty-ver", ctx=ctx)
    assert no_crit.exit_code == EXIT_PRECONDITION
    assert "no acceptance criteria" in no_crit.payload["detail"]

    rid = build_run_id("my_spec", "1234567890abcdef", rand_hex="a1b2c3")
    assert rid == "my-spec-1234567-a1b2c3"


def test_key_order_aifactory_tfactory_lazy_stop_and_home_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    read_calls: list[Path] = []
    orig_read = Path.read_text

    def _spy_read(self: Path, *a: Any, **kw: Any) -> str:
        read_calls.append(self)
        return orig_read(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", _spy_read)

    for portal, upper in (("aifactory", "AIFACTORY"), ("tfactory", "TFACTORY")):
        pdir = home / f".{portal}"
        pdir.mkdir(parents=True)
        mcp_f = pdir / ".mcp-key"
        tok_f = pdir / ".token"
        ovr_f = tmp_path / f"{portal}.ovr"
        tok_f.write_text(f"legacy_{portal}\n")
        ovr_f.write_text(f"acw_ovr_{portal}\n")
        mcp_f.write_text(f"acw_mcp_{portal}\n")
        read_calls.clear()

        k1 = resolve_portal_key(
            portal,
            env={f"{upper}_MCP_KEY": f"acw_env_{portal}", f"{upper}_API_TOKEN_FILE": str(ovr_f)},
            home=home,
        )
        assert k1 is not None and k1.source == f"${upper}_MCP_KEY"
        assert read_calls == []

        k2 = resolve_portal_key(
            portal,
            env={f"{upper}_API_TOKEN_FILE": str(ovr_f)},
            home=home,
        )
        assert k2 is not None and k2.source == f"~/.{portal}/.mcp-key"
        assert read_calls == [mcp_f]

        read_calls.clear()
        mcp_f.unlink()
        k3 = resolve_portal_key(
            portal,
            env={f"{upper}_API_TOKEN_FILE": str(ovr_f)},
            home=home,
        )
        assert k3 is not None and k3.source == f"${upper}_API_TOKEN_FILE"
        assert read_calls == [ovr_f]

        read_calls.clear()
        k4 = resolve_portal_key(portal, env={}, home=home)
        assert k4 is not None and k4.source == f"~/.{portal}/.token" and k4.kind == "legacy"
        assert read_calls == [tok_f]

    cfg_file = home / ".config" / "factory" / "config.toml"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text('[portals.aifactory]\nurl = "https://af.from-home.example/"\n')
    assert (
        resolve_portal_url("aifactory", env={}, home=home, config_path=None)
        == "https://af.from-home.example"
    )


def test_mcp_config_does_not_read_keys_and_handles_symlinks_race_and_toml_arrays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _forbid_key_lookup(*_a: Any, **_kw: Any) -> Any:
        raise AssertionError("mcp-config must never read or resolve portal keys")

    monkeypatch.setattr("factory_cli.config.resolve_portal_key", _forbid_key_lookup)

    ctx = RuntimeContext(cwd=tmp_path, env={}, home=tmp_path)
    assert main(["mcp-config", "agy", "--write"], cwd=tmp_path, env={}, home=tmp_path) == EXIT_OK
    _ = capsys.readouterr()
    agy_dir_name = ".gem" + "ini"
    agy_path = tmp_path / agy_dir_name / "config" / "mcp_config.json"
    assert agy_path.is_file()
    assert json.loads(agy_path.read_text())["mcpServers"]["factory"] == {
        "command": "factory",
        "args": ["mcp"],
    }

    agy_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "factory": {"command": "old", "args": []},
                    "keep": {"command": "k", "args": []},
                }
            }
        )
    )
    agy_path.chmod(0o640)
    res_force = run_mcp_config("agy", write=True, force=True, ctx=ctx)
    assert res_force.exit_code == EXIT_OK
    agy_bak = agy_path.with_name("mcp_config.json.bak")
    assert agy_bak.is_file() and (agy_bak.stat().st_mode & 0o777) == 0o600
    assert (agy_path.stat().st_mode & 0o777) == 0o640
    assert json.loads(agy_path.read_text())["mcpServers"]["keep"] == {"command": "k", "args": []}

    codex_path = tmp_path / ".codex" / "config.toml"
    res_new_codex = run_mcp_config("codex", write=True, force=False, ctx=ctx)
    assert res_new_codex.exit_code == EXIT_OK
    assert tomllib.loads(codex_path.read_text())["mcp_servers"]["factory"] == {
        "command": "factory",
        "args": ["mcp"],
    }

    complex_toml = (
        'model = "o3"\n\n'
        "[mcp_servers.factory]\n"
        "# internal factory comment to remove\n"
        'command = "old-factory"\n'
        'args = ["old"]\n\n'
        "# Comment belonging to array of tables\n"
        "[[profiles]]\n"
        'name = "default"\n\n'
        "[mcp_servers.factory.env]\n"
        'OLD = "1"\n\n'
        "# Comment belonging to omega table\n"
        "[mcp_servers.omega]\n"
        'command = "omega"\n'
    )
    codex_path.write_text(complex_toml)
    res_arr = run_mcp_config("codex", write=True, force=True, ctx=ctx)
    assert res_arr.exit_code == EXIT_OK
    rewritten = codex_path.read_text()
    assert "# Comment belonging to array of tables\n[[profiles]]" in rewritten
    assert "# Comment belonging to omega table\n[mcp_servers.omega]" in rewritten
    assert "# internal factory comment to remove" not in rewritten
    parsed_rewritten = tomllib.loads(rewritten)
    assert parsed_rewritten["profiles"] == [{"name": "default"}]
    assert parsed_rewritten["mcp_servers"]["omega"] == {"command": "omega"}


def test_mcp_config_refuses_symlinks_and_concurrent_modifications(
    tmp_path: Path,
) -> None:
    real_file = tmp_path / "real.json"
    real_file.write_text("{}\n")
    sym_target = tmp_path / "sym_mcp.json"
    sym_target.symlink_to(real_file)
    sym_res = run_mcp_config("claude", write=True, force=True, target_path=sym_target)
    assert sym_res.exit_code == EXIT_PRECONDITION
    assert "symlink" in sym_res.text
    assert real_file.read_text() == "{}\n"

    victim = tmp_path / "victim.txt"
    victim.write_text("precious")
    normal_target = tmp_path / "normal.json"
    normal_target.write_text('{"mcpServers": {}}\n')
    bak_sym = tmp_path / "normal.json.bak"
    bak_sym.symlink_to(victim)
    bak_res = run_mcp_config("claude", write=True, force=True, target_path=normal_target)
    assert bak_res.exit_code == EXIT_PRECONDITION
    assert "symlink" in bak_res.text
    assert victim.read_text() == "precious"
    bak_sym.unlink()

    def _concurrent_edit() -> None:
        normal_target.write_text('{"mcpServers": {"concurrent": {}}}\n')

    race_res = run_mcp_config(
        "claude",
        write=True,
        force=True,
        target_path=normal_target,
        _before_commit_hook=_concurrent_edit,
    )
    assert race_res.exit_code == EXIT_PRECONDITION
    assert "changed concurrently" in race_res.text
    assert "concurrent" in normal_target.read_text()


def test_canary_redaction_everywhere_and_mcp_tools_registration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _init_approved_repo(tmp_path)

    env = {
        "PFACTORY_MCP_KEY": CANARY_KEY,
        "AIFACTORY_MCP_KEY": CANARY_KEY,
        "TFACTORY_MCP_KEY": CANARY_KEY,
        "CFACTORY_API_KEY": CANARY_KEY,
    }
    bad_arg = f"--invalid-flag={CANARY_KEY}-https://secretuser@github.com/org/repo"
    code = main(["submit", bad_arg], cwd=repo, env=env, home=tmp_path)
    assert code == EXIT_PRECONDITION
    err_out = capsys.readouterr().err
    assert CANARY_KEY not in err_out
    assert "secretuser" not in err_out

    with pytest.raises(PreconditionError) as exc_info:
        normalize_remote_url("https://token_user_only@github.com/single_segment")
    assert "token_user_only" not in str(exc_info.value)
    assert "***REDACTED***@github.com" in str(exc_info.value)

    def _leaky_portal(req: http.server.BaseHTTPRequestHandler) -> None:
        _send_json(
            req,
            500,
            {
                "detail": f"error with {CANARY_KEY} and https://gituser@github.com/a/b",
                CANARY_KEY: f"nested {CANARY_KEY}",
            },
        )

    with _fake_http_server(_leaky_portal) as base_url:
        full_env = {
            **env,
            "PFACTORY_API_URL": base_url,
            "AIFACTORY_API_URL": base_url,
            "TFACTORY_API_URL": base_url,
            "CFACTORY_API_URL": base_url,
        }
        ctx = RuntimeContext(cwd=repo, env=full_env, home=tmp_path)

        for argv in (
            ["test", "--project", "p1", "--spec", SLUG, "--branch", "feat/3865-demo"],
            ["status", "af:t1"],
            ["doctor"],
        ):
            _ = main(argv, cwd=repo, env=full_env, home=tmp_path)
            captured = capsys.readouterr()
            assert CANARY_KEY not in captured.out
            assert CANARY_KEY not in captured.err
            assert "gituser" not in captured.out
            assert "gituser" not in captured.err

        for mcp_raw in (
            handle_factory_test("p1", "feat/3865-demo", spec=SLUG, ctx=ctx),
            handle_factory_status("af:t1", ctx=ctx),
            handle_factory_doctor(ctx=ctx),
        ):
            assert CANARY_KEY not in mcp_raw
            assert "gituser" not in mcp_raw

    import inspect  # noqa: PLC0415

    sig = inspect.signature(handle_factory_submit)
    assert sig.parameters["dry_run"].default is True

    recorded_tools: dict[str, Any] = {}

    class _SpyServer:
        def add_tool(
            self,
            fn: Any,
            *,
            name: str | None = None,
            description: str | None = None,
        ) -> None:
            recorded_tools[name or fn.__name__] = (fn, description)

        def run(self, transport: str = "stdio") -> None:
            _ = transport

    orig_create = sys.modules["factory_cli.mcp_server"]._create_mcp_server
    sys.modules["factory_cli.mcp_server"]._create_mcp_server = lambda _n: _SpyServer()  # type: ignore[assignment]
    try:
        build_mcp_server()
    finally:
        sys.modules["factory_cli.mcp_server"]._create_mcp_server = orig_create  # type: ignore[assignment]

    assert set(recorded_tools.keys()) == {
        "factory_submit",
        "factory_test",
        "factory_status",
        "factory_doctor",
        "factory_project_list",
        "factory_project_add",
        "factory_approve",
        "factory_reject",
        "factory_retry",
        "factory_archive",
        "factory_card_create",
        "factory_card_move",
        "factory_card_list",
        "factory_card_run",
    }
    submit_fn = recorded_tools["factory_submit"][0]
    assert inspect.signature(submit_fn).parameters["dry_run"].default is True

    assert all(not p.endswith("_vendor") for p in sys.path)


def test_wrapped_verification_bullet_keeps_its_continuation() -> None:
    text = "## Verification\n\n- Return 403 for requests\n  without credentials.\n- Second\n"
    assert extract_verification_bullets(text, require_verification_heading=True) == [
        "Return 403 for requests without credentials.",
        "Second",
    ]


def test_project_commands_and_mcp_twins(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        body = _read_req_json(req) if req.command == "POST" else {}
        calls.append((req.command, req.path, body))
        _send_json(
            req, 201 if req.command == "POST" else 200, {"id": "p1"} if body else [{"id": "p1"}]
        )

    with _fake_http_server(_handler) as url:
        env = {
            f"{portal.upper()}_MCP_KEY": CANARY_KEY
            for portal in ("AIFACTORY", "PFACTORY", "TFACTORY")
        }
        env.update({f"{portal}_API_URL": url for portal in ("AIFACTORY", "PFACTORY", "TFACTORY")})
        ctx = RuntimeContext(env=env, home=tmp_path)
        assert main(["project", "list"], env=env, home=tmp_path) == EXIT_OK
        assert set(json.loads(capsys.readouterr().out)) == {"aifactory", "pfactory", "tfactory"}
        assert json.loads(handle_factory_project_list(ctx=ctx))["result"]["tfactory"] == [
            {"id": "p1"}
        ]
        assert (
            main(
                ["project", "add", "aifactory", "https://github.com/o/r.git", "--branch", "main"],
                env=env,
                home=tmp_path,
            )
            == EXIT_OK
        )
        assert (
            json.loads(
                handle_factory_project_add(
                    "aifactory", "https://github.com/o/r.git", branch="main", ctx=ctx
                )
            )["outcome"]
            == "ok"
        )
    assert calls[-1] == (
        "POST",
        "/api/mcp-stdio/projects",
        {"gitUrl": "https://github.com/o/r.git", "branch": "main"},
    )
    assert len([call for call in calls if call[0] == "GET"]) == 6


@pytest.mark.parametrize(
    ("action", "target", "path", "body"),
    [
        (
            "approve",
            "pf:s1",
            "/api/mcp-stdio/plan/sessions/s1/approve",
            {"approver": "factory-cli"},
        ),
        (
            "reject",
            "pf:s1",
            "/api/mcp-stdio/plan/sessions/s1/reject",
            {"approver": "factory-cli", "feedback": "revise"},
        ),
        ("approve", "af:p1:t1", "/api/mcp-stdio/tasks/p1%3At1/approve-plan", {}),
        ("reject", "af:p1:t1", "/api/mcp-stdio/tasks/p1%3At1/reject-plan", {"feedback": "revise"}),
        ("retry", "af:p1:t1", "/api/mcp-stdio/tasks/p1%3At1/recover", {"autoRestart": True}),
        ("retry", "tf:p1/t1", "/api/mcp-stdio/tasks/p1%3At1/recover", {"autoRestart": True}),
        ("archive", "af:p1:t1", "/api/mcp-stdio/projects/p1/tasks/archive", {"taskIds": ["p1:t1"]}),
        ("archive", "tf:p1/t1", "/api/mcp-stdio/projects/p1/tasks/archive", {"taskIds": ["p1:t1"]}),
    ],
)
def test_action_routes_and_twins(
    tmp_path: Path,
    action: str,
    target: str,
    path: str,
    body: dict[str, Any],
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        calls.append((req.path, _read_req_json(req)))
        _send_json(req, 200, {"success": True})

    with _fake_http_server(_handler) as url:
        env = {f"{portal}_MCP_KEY": CANARY_KEY for portal in ("PFACTORY", "AIFACTORY", "TFACTORY")}
        env.update({f"{portal}_API_URL": url for portal in ("PFACTORY", "AIFACTORY", "TFACTORY")})
        ctx = RuntimeContext(env=env, home=tmp_path)
        assert run_action(action, target, feedback="revise", ctx=ctx).exit_code == EXIT_OK
        assert (
            json.loads(handle_factory_action(action, target, "revise", ctx=ctx))["outcome"] == "ok"
        )
    assert calls == [(path, body), (path, body)]


def test_card_json_rpc_and_errors(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        assert req.path == "/mcp"
        body = _read_req_json(req)
        calls.append(body)
        payload = {"card_key": "FCT-1"}
        _send_json(
            req,
            200,
            {
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
            },
        )

    with _fake_http_server(_handler) as url:
        ctx = RuntimeContext(
            env={"CFACTORY_API_URL": url, "CFACTORY_API_KEY": CANARY_KEY}, home=tmp_path
        )
        for action, kwargs in (
            ("create", {"title": "One", "tier": "low"}),
            ("move", {"card_key": "FCT-1", "status": "ready"}),
            ("list", {}),
            ("run", {"card_key": "FCT-1"}),
        ):
            assert run_card(action, ctx=ctx, **kwargs).payload["result"] == {"card_key": "FCT-1"}
            assert json.loads(handle_factory_card(action, ctx=ctx, **kwargs))["result"] == {
                "card_key": "FCT-1"
            }
    assert [call["params"]["name"] for call in calls] == [
        name
        for name in (
            "cfactory_create_card",
            "cfactory_move_card",
            "cfactory_list_cards",
            "cfactory_run_card",
        )
        for _ in range(2)
    ]
    assert (
        run_card("move", card_key="FCT-1", ctx=RuntimeContext(env={}, home=tmp_path)).exit_code
        == EXIT_PRECONDITION
    )
    assert (
        run_action("archive", "pf:s1", ctx=RuntimeContext(env={}, home=tmp_path)).exit_code
        == EXIT_PRECONDITION
    )


def test_action_client_errors_and_unknown_mutation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    codes = iter((400, 503))

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        _read_req_json(req)
        _send_json(req, next(codes), {"detail": f"rejected {CANARY_KEY}"})

    with _fake_http_server(_handler) as url:
        env = {"AIFACTORY_MCP_KEY": CANARY_KEY, "AIFACTORY_API_URL": url}
        assert main(["approve", "af:p1:t1"], env=env, home=tmp_path) == EXIT_REJECTED
        assert CANARY_KEY not in capsys.readouterr().err
        result = run_action("approve", "af:p1:t1", ctx=RuntimeContext(env=env, home=tmp_path))
        assert result.exit_code == EXIT_UNKNOWN
        assert CANARY_KEY not in json.dumps(result.payload)
    assert (
        run_action("archive", "af:bare", ctx=RuntimeContext(env={}, home=tmp_path)).exit_code
        == EXIT_PRECONDITION
    )


def _registered_tools(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from factory_cli import mcp_server  # noqa: PLC0415

    tools: dict[str, Any] = {}

    class _Server:
        def add_tool(self, fn: Any, *, name: str, description: str) -> None:
            _ = description
            tools[name] = fn

    monkeypatch.setattr(mcp_server, "_create_mcp_server", lambda _name: _Server())
    build_mcp_server()
    return tools


@pytest.mark.parametrize(
    ("argv", "tool", "args"),
    [
        (["approve", "pf:s1"], "factory_approve", ("pf:s1",)),
        (["reject", "pf:s1", "--feedback", "revise"], "factory_reject", ("pf:s1", "revise")),
        (["retry", "af:p1:t1"], "factory_retry", ("af:p1:t1",)),
        (["archive", "af:p1:t1"], "factory_archive", ("af:p1:t1",)),
        (["card", "run", "FCT-1"], "factory_card_run", ("FCT-1",)),
    ],
)
def test_cli_and_registered_action_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    tool: str,
    args: tuple[str, ...],
) -> None:
    calls: list[str] = []

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        calls.append(req.path)
        _read_req_json(req)
        if req.path == "/mcp":
            _send_json(
                req, 200, {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "{}"}]}}
            )
        else:
            _send_json(req, 200, {"data": {"autoRestarted": True}})

    with _fake_http_server(_handler) as url:
        env = {f"{p}_MCP_KEY": CANARY_KEY for p in ("PFACTORY", "AIFACTORY")}
        if args[0].startswith("pf:"):
            del env["AIFACTORY_MCP_KEY"]
        env["CFACTORY_API_KEY"] = CANARY_KEY
        env.update({f"{p}_API_URL": url for p in ("PFACTORY", "AIFACTORY", "CFACTORY")})
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        assert main(argv, env=env, home=tmp_path) == EXIT_OK
        assert json.loads(_registered_tools(monkeypatch)[tool](*args))["outcome"] == "ok"
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("http_code", "body", "expected"),
    [
        (400, {"detail": "bad request"}, EXIT_REJECTED),
        (503, {"detail": "unavailable"}, EXIT_UNKNOWN),
        (200, {"jsonrpc": "2.0", "id": 1, "error": {"code": -32602}}, EXIT_REJECTED),
        (
            200,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"isError": True, "content": [{"text": "failed"}]},
            },
            EXIT_REJECTED,
        ),
        (200, {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603}}, EXIT_UNKNOWN),
    ],
)
def test_card_cli_mcp_error_parity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    http_code: int,
    body: dict[str, Any],
    expected: int,
) -> None:
    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        _read_req_json(req)
        _send_json(req, http_code, body)

    with _fake_http_server(_handler) as url:
        env = {"CFACTORY_API_URL": url, "CFACTORY_API_KEY": CANARY_KEY}
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        cli_code = main(["card", "create", "Example"], env=env, home=tmp_path)
        mcp = json.loads(_registered_tools(monkeypatch)["factory_card_create"]("Example"))
    assert cli_code == expected
    assert mcp["outcome"] == {EXIT_REJECTED: "rejected", EXIT_UNKNOWN: "unknown"}[expected]


@pytest.mark.parametrize("target", ["tf:p1/", "tf:/s1", "af:p1:", "af::t1"])
def test_action_rejects_empty_id_parts_before_http(tmp_path: Path, target: str) -> None:
    calls: list[str] = []

    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        calls.append(req.path)
        _send_json(req, 200, {})

    with _fake_http_server(_handler) as url:
        env = {f"{p}_API_URL": url for p in ("AIFACTORY", "TFACTORY")}
        env.update({f"{p}_MCP_KEY": CANARY_KEY for p in ("AIFACTORY", "TFACTORY")})
        assert main(["retry", target], env=env, home=tmp_path) == EXIT_PRECONDITION
    assert not calls


def test_invalid_action_prefix_needs_no_portal_key(tmp_path: Path) -> None:
    assert main(["retry", "bad:p1"], env={}, home=tmp_path) == EXIT_PRECONDITION


@pytest.mark.parametrize(
    ("argv", "tool", "args"),
    [
        (["card", "create", "   "], "factory_card_create", ("   ",)),
        (
            ["card", "create", "Example", "--tier", "invalid"],
            "factory_card_create",
            ("Example", None, "invalid"),
        ),
        (["card", "move", "FCT-1", "invalid"], "factory_card_move", ("FCT-1", "invalid")),
    ],
)
def test_card_validation_matches_registered_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    tool: str,
    args: tuple[str | None, ...],
) -> None:
    env = {"CFACTORY_API_KEY": CANARY_KEY}
    monkeypatch.setenv("CFACTORY_API_KEY", CANARY_KEY)
    assert main(argv, env=env, home=tmp_path) == EXIT_PRECONDITION
    assert json.loads(_registered_tools(monkeypatch)[tool](*args))["outcome"] == "rejected"


@pytest.mark.parametrize("action", ["create", "move", "run"])
def test_malformed_card_mutations_are_unknown(tmp_path: Path, action: str) -> None:
    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        _read_req_json(req)
        _send_json(req, 200, {"id": 1, "result": {"content": [{"text": "{}"}]}})

    with _fake_http_server(_handler) as url:
        ctx = RuntimeContext(
            env={"CFACTORY_API_URL": url, "CFACTORY_API_KEY": CANARY_KEY}, home=tmp_path
        )
        assert (
            run_card(action, title="Example", card_key="FCT-1", status="ready", ctx=ctx).exit_code
            == EXIT_UNKNOWN
        )
        assert run_card("list", ctx=ctx).exit_code == EXIT_REJECTED


def test_retry_requires_auto_restart_and_project_list_failure(tmp_path: Path) -> None:
    def _handler(req: http.server.BaseHTTPRequestHandler) -> None:
        if req.command == "POST":
            _read_req_json(req)
            _send_json(req, 200, {"data": {"autoRestarted": False}})
        else:
            _send_json(req, 503 if req.headers.get("Authorization") == "Bearer pf-key" else 200, {})

    with _fake_http_server(_handler) as url:
        env = {f"{p}_API_URL": url for p in ("AIFACTORY", "PFACTORY", "TFACTORY")}
        env.update(
            {
                "AIFACTORY_MCP_KEY": "af-key",
                "PFACTORY_MCP_KEY": "pf-key",
                "TFACTORY_MCP_KEY": "tf-key",
            }
        )
        ctx = RuntimeContext(env=env, home=tmp_path)
        assert run_action("retry", "af:p1:t1", ctx=ctx).exit_code == EXIT_UNKNOWN
        assert main(["project", "list"], env=env, home=tmp_path) == EXIT_REJECTED
        assert json.loads(handle_factory_project_list(ctx=ctx))["outcome"] == "rejected"
