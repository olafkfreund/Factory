#!/usr/bin/env python3
"""Tests for scripts/benchmarks/run_pipeline_task.py -- pure-function checks
only, no network. HTTP is never exercised (register_project/submit_task/
poll_task all take an injected client and are covered by their unit tests
below using a tiny fake instead of the real HttpClient/urllib).

Covers the three things the deliverable calls out: the prediction-record
shape, scratch-repo idempotence against a real local tmp git repo (no
network -- `git init`/`git clone` of a local path only), and the evidence-gate
rejection on zero/missing tokens.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_pipeline_task as rpt

# ── fixtures ─────────────────────────────────────────────────────────────────


def _git(*args: str, cwd: Path) -> str:
    cmd = ["git", *args]
    result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)  # noqa: S603
    return result.stdout.strip()


@pytest.fixture
def upstream_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """A tiny local upstream with two commits; returns (path, base_sha, head_sha)."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git("init", "-q", "-b", "trunk", cwd=upstream)
    _git("config", "user.email", "t@example.com", cwd=upstream)
    _git("config", "user.name", "t", cwd=upstream)
    (upstream / "a.txt").write_text("one\n")
    _git("add", "a.txt", cwd=upstream)
    _git("commit", "-q", "-m", "base", cwd=upstream)
    base_sha = _git("rev-parse", "HEAD", cwd=upstream)
    (upstream / "a.txt").write_text("one\ntwo\n")
    _git("commit", "-aqm", "future (gold fix)", cwd=upstream)
    head_sha = _git("rev-parse", "HEAD", cwd=upstream)
    return upstream, base_sha, head_sha


# ── prediction record shape ─────────────────────────────────────────────────


def test_build_prediction_record_shape() -> None:
    record = rpt.build_prediction_record("astropy__astropy-1234", "diff --git a/x b/x\n")
    assert record == {
        "instance_id": "astropy__astropy-1234",
        "model_name_or_path": "factory-pipeline",
        "model_patch": "diff --git a/x b/x\n",
    }


def test_build_prediction_record_empty_diff_still_emits() -> None:
    record = rpt.build_prediction_record("x-1", "")
    assert record["model_patch"] == ""
    assert record["instance_id"] == "x-1"


def test_build_meta_record_shape() -> None:
    outcome = {
        "status": "completed",
        "halt_reason": None,
        "total_tokens": 4200,
        "cost_usd": 1.23,
        "duration_sec": 12.34,
    }
    meta = rpt.build_meta_record("inst-1", "task-1", "spec-1", outcome)
    assert meta == {
        "instance_id": "inst-1",
        "task_id": "task-1",
        "spec_id": "spec-1",
        "status": "completed",
        "halt_reason": None,
        "total_tokens": 4200,
        "cost_usd": 1.23,
        "duration_sec": 12.3,
    }


# ── scratch-repo idempotence (real local git, no network) ──────────────────


def test_prepare_scratch_repo_pins_to_base_commit(
    upstream_repo: tuple[Path, str, str], tmp_path: Path
) -> None:
    upstream, base_sha, _head_sha = upstream_repo
    scratch = tmp_path / "scratch" / "inst-1"
    rpt.prepare_scratch_repo(str(upstream), base_sha, scratch)

    head = _git("-C", str(scratch), "rev-parse", "HEAD", cwd=scratch)
    assert head == base_sha
    # the future/gold commit must not be reachable from ANY ref: main is
    # base_commit, the upstream default branch is deleted, origin removed.
    log_all = _git("-C", str(scratch), "log", "--oneline", "--all", cwd=scratch)
    assert "gold fix" not in log_all
    branches = _git(
        "-C", str(scratch), "for-each-ref", "--format=%(refname:short)", "refs/heads/", cwd=scratch
    )
    assert branches.splitlines() == ["main"]
    # origin removed -- no remote to leak history from
    remotes = _git("-C", str(scratch), "remote", cwd=scratch)
    assert remotes == ""


def test_prepare_scratch_repo_reuses_matching_scratch(
    upstream_repo: tuple[Path, str, str], tmp_path: Path
) -> None:
    upstream, base_sha, _head_sha = upstream_repo
    scratch = tmp_path / "scratch" / "inst-1"
    rpt.prepare_scratch_repo(str(upstream), base_sha, scratch)
    # second call is a no-op reuse, not a re-clone -- must not raise
    result = rpt.prepare_scratch_repo(str(upstream), base_sha, scratch)
    assert result == scratch


def test_prepare_scratch_repo_wrong_head_is_system_exit(
    upstream_repo: tuple[Path, str, str], tmp_path: Path
) -> None:
    upstream, base_sha, head_sha = upstream_repo
    scratch = tmp_path / "scratch" / "inst-1"
    rpt.prepare_scratch_repo(str(upstream), base_sha, scratch)
    with pytest.raises(SystemExit):
        rpt.prepare_scratch_repo(str(upstream), head_sha, scratch)


# ── evidence gate ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("total_tokens", "expected_status", "expected_halt"),
    [
        (None, "failed", "no_evidence"),
        (0, "failed", "no_evidence"),
        (-1, "failed", "no_evidence"),
        (1, "completed", None),
        (4200, "completed", None),
    ],
)
def test_apply_evidence_gate_on_completed(
    total_tokens: float | None, expected_status: str, expected_halt: str | None
) -> None:
    status, halt_reason = rpt.apply_evidence_gate("completed", total_tokens)
    assert (status, halt_reason) == (expected_status, expected_halt)


def test_apply_evidence_gate_passes_through_non_completed_status() -> None:
    # qa_failed (or any non-"completed" status) is not the evidence gate's
    # concern -- it passes through unchanged even with zero tokens.
    status, halt_reason = rpt.apply_evidence_gate("qa_failed", 0)
    assert (status, halt_reason) == ("qa_failed", None)


def test_read_evidence_from_token_usage_json(tmp_path: Path) -> None:
    spec_dir = tmp_path / ".aifactory" / "specs" / "spec-1"
    spec_dir.mkdir(parents=True)
    (spec_dir / "token_usage.json").write_text('{"total_tokens": 999, "cost_usd": 0.42}')
    evidence = rpt.read_evidence(tmp_path, "spec-1")
    assert evidence == {"total_tokens": 999, "cost_usd": 0.42}


def test_read_evidence_falls_back_to_completed_json(tmp_path: Path) -> None:
    spec_dir = tmp_path / ".aifactory" / "specs" / "spec-1"
    spec_dir.mkdir(parents=True)
    (spec_dir / "COMPLETED.json").write_text(
        '{"usage": {"worker-a": {"total_tokens": 100}, "worker-b": {"total_tokens": 50}}}'
    )
    evidence = rpt.read_evidence(tmp_path, "spec-1")
    assert evidence["total_tokens"] == 150


def test_read_evidence_missing_files_returns_none(tmp_path: Path) -> None:
    evidence = rpt.read_evidence(tmp_path, "spec-nope")
    assert evidence == {"total_tokens": None, "cost_usd": None}


# ── register_project / submit_task against a fake client (no real network) ──


class _FakeResp:
    def __init__(self, status: int, json_body: dict) -> None:
        self.status = status
        self.json = json_body


class _FakeClient:
    """Records calls and replays scripted responses -- stands in for
    HttpClient so register_project/submit_task are covered without a socket.
    """

    def __init__(self, responses: dict[tuple[str, str], _FakeResp]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str, dict | None]] = []

    def post(self, path: str, body: dict | None = None) -> _FakeResp:
        self.calls.append(("POST", path, body))
        return self._responses[("POST", path)]

    def get(self, path: str) -> _FakeResp:
        self.calls.append(("GET", path, None))
        return self._responses[("GET", path)]


def test_register_project_returns_new_id() -> None:
    client = _FakeClient({("POST", "/api/projects"): _FakeResp(200, {"project_id": "p-1"})})
    project_id = rpt.register_project(client, Path("/scratch/x"), "inst-1")
    assert project_id == "p-1"


def test_register_project_reuses_existing_on_conflict() -> None:
    client = _FakeClient(
        {
            ("POST", "/api/projects"): _FakeResp(409, {"error": "exists"}),
            ("GET", "/api/projects"): _FakeResp(
                200, {"projects": [{"name": "swebench-inst-1", "project_id": "p-old"}]}
            ),
        }
    )
    project_id = rpt.register_project(client, Path("/scratch/x"), "inst-1")
    assert project_id == "p-old"


def test_submit_task_raises_pipeline_error_on_failure() -> None:
    client = _FakeClient({("POST", "/api/tasks/from-issue"): _FakeResp(500, {"error": "boom"})})
    with pytest.raises(rpt.PipelineError) as exc_info:
        rpt.submit_task(client, "p-1", "inst-1", "do the thing", "medium")
    assert exc_info.value.halt_reason == "submit_failed"


def test_extract_worktree_patch_recovers_uncommitted(
    upstream_repo: tuple[Path, str, str], tmp_path: Path
) -> None:
    upstream, base_sha, _head = upstream_repo
    scratch = tmp_path / "scratch" / "inst-w"
    rpt.prepare_scratch_repo(str(upstream), base_sha, scratch)
    wt = scratch / ".aifactory" / "worktrees" / "tasks" / "001-x"
    _git(
        "-C", str(scratch), "worktree", "add", "-b", "aifactory/001-x", str(wt), "main", cwd=scratch
    )
    (wt / "a.txt").write_text("one\npatched\n")  # uncommitted change
    (wt / ".aifactory-status").write_text("junk")  # untracked artifact, must not appear
    patch = rpt.extract_worktree_patch(scratch, base_sha, "001-x")
    assert "patched" in patch
    assert ".aifactory-status" not in patch


def test_extract_worktree_patch_missing_worktree_is_empty(tmp_path: Path) -> None:
    assert rpt.extract_worktree_patch(tmp_path, "deadbeef", "nope") == ""


# ── provision_worktree_venv ──────────────────────────────────────────────────


def test_exclude_venv_writes_into_linked_worktree_gitdir(
    upstream_repo: tuple[Path, str, str], tmp_path: Path
) -> None:
    upstream, base_sha, _head = upstream_repo
    scratch = tmp_path / "scratch" / "inst-venv"
    rpt.prepare_scratch_repo(str(upstream), base_sha, scratch)
    wt = scratch / ".aifactory" / "worktrees" / "tasks" / "001-x"
    _git(
        "-C", str(scratch), "worktree", "add", "-b", "aifactory/001-x", str(wt), "main", cwd=scratch
    )

    rpt._exclude_venv(wt)

    gitdir = rpt._worktree_gitdir(wt)
    assert gitdir != wt / ".git"  # resolved through the `gitdir: <path>` file
    exclude_text = (gitdir / "info" / "exclude").read_text()
    assert ".venv/\n" in exclude_text


def test_exclude_venv_regular_repo_layout(tmp_path: Path) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()
    _git("init", "-q", cwd=repo)

    rpt._exclude_venv(repo)

    assert ".venv/\n" in (repo / ".git" / "info" / "exclude").read_text()


def test_provision_worktree_venv_poll_timeout_returns_false_fast(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(rpt, "_VENV_POLL_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(rpt, "_VENV_POLL_INTERVAL_SEC", 0.01)

    result = rpt.provision_worktree_venv(tmp_path / "no-such-scratch", "spec-nope", [])

    assert result is False


def _stub_pipeline(monkeypatch: pytest.MonkeyPatch, calls: list[tuple]) -> None:
    """Stub every network-touching step of main() so only the
    --provision-venv wiring is under test."""
    monkeypatch.setattr(rpt, "HttpClient", lambda *_a, **_k: object())
    monkeypatch.setattr(rpt, "register_project", lambda *_a, **_k: "p-1")
    monkeypatch.setattr(rpt, "submit_task", lambda *_a, **_k: ("task-1", "spec-1"))
    monkeypatch.setattr(rpt, "poll_task", lambda *_a, **_k: None)
    monkeypatch.setattr(
        rpt,
        "get_task_detail",
        lambda *_a, **_k: {"status": "completed", "branch_name": None},
    )
    monkeypatch.setattr(
        rpt, "read_evidence", lambda *_a, **_k: {"total_tokens": 1, "cost_usd": 0.1}
    )
    monkeypatch.setattr(rpt, "provision_worktree_venv", lambda *a, **_k: calls.append(a) or True)


def test_provision_venv_flag_off_not_called(
    monkeypatch: pytest.MonkeyPatch, upstream_repo: tuple[Path, str, str], tmp_path: Path
) -> None:
    upstream, base_sha, _head = upstream_repo
    calls: list[tuple] = []
    _stub_pipeline(monkeypatch, calls)

    rpt.main(
        [
            "--instance-id",
            "inst-1",
            "--repo-url",
            str(upstream),
            "--base-commit",
            base_sha,
            "--problem-statement",
            "fix it",
            "--scratch-root",
            str(tmp_path / "scratch"),
            "--out",
            str(tmp_path / "preds.jsonl"),
        ]
    )

    assert calls == []


def test_provision_venv_flag_on_calls_with_spec_id(
    monkeypatch: pytest.MonkeyPatch, upstream_repo: tuple[Path, str, str], tmp_path: Path
) -> None:
    upstream, base_sha, _head = upstream_repo
    calls: list[tuple] = []
    _stub_pipeline(monkeypatch, calls)
    scratch_root = tmp_path / "scratch"

    rpt.main(
        [
            "--instance-id",
            "inst-1",
            "--repo-url",
            str(upstream),
            "--base-commit",
            base_sha,
            "--problem-statement",
            "fix it",
            "--scratch-root",
            str(scratch_root),
            "--out",
            str(tmp_path / "preds.jsonl"),
            "--provision-venv",
            "--extra-deps",
            "mpmath, pytest",
        ]
    )

    assert len(calls) == 1
    scratch_dir, spec_id, extra_deps = calls[0][:3]
    assert scratch_dir == scratch_root / "inst-1"
    assert spec_id == "spec-1"
    assert extra_deps == ["mpmath", "pytest"]
