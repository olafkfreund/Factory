#!/usr/bin/env python3
"""Drive ONE SWE-bench instance through the live AIFactory pipeline end to end
and emit an official-harness prediction record.

Design: docs/benchmarks/pipeline-driver-design.md (issue #271). Follows it
exactly -- endpoints, payloads, precedence and risks are locked there, not
re-derived here.

Sequence (see the design doc's "Endpoint sequence" section):
    prepare_scratch_repo()   local clone pinned to base_commit, origin removed
    POST /api/projects       register the scratch repo (path mode)
    POST /api/tasks/from-issue   submit with base_branch=main, auto_continue
    GET  /api/tasks/{id}/status  poll to terminal (is_running == false)
    GET  /api/tasks/{id}          read status + branch_name (the verdict)
    git diff <base_commit> <branch_name>   the scored patch (two-dot, local)
    read <spec_dir>/token_usage.json | COMPLETED.json   evidence gate

Reuses `shared/factory-common/factory_common/http.py::HttpClient` (the
Cloudflare-friendly urllib client already used by scripts/parr_regression.py)
for all HTTP -- no new client, no third-party HTTP dependency.

Exit codes: 0 -- prediction emitted (even a likely-unresolved one: an empty
diff on a "completed" status still scores, just probably unresolved). 2 --
pipeline failure (qa_failed / no_evidence / timeout / any submit-or-poll
error); the meta sidecar is still written so the failure is inspectable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# factory-common is the deduped hub utility layer; scripts/ is a flat dir (not
# an installed package), so the sibling shared/ package is added to the path
# the same way scripts/parr_regression.py does.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "factory-common"))

from factory_common.http import HttpClient, bearer_auth, is_success

DEFAULT_AIFACTORY_URL = "http://localhost:3101"
MODEL_NAME = "factory-pipeline"


class PipelineError(Exception):
    """A failure after the task was submitted (or while submitting it).

    Distinct from a scratch-repo setup SystemExit: by the time this is
    raised, `main()` has enough context (instance_id, maybe task_id/spec_id)
    to still emit the meta sidecar before exiting non-zero.
    """

    def __init__(self, message: str, halt_reason: str) -> None:
        super().__init__(message)
        self.halt_reason = halt_reason


# ── scratch repo (repo pinning + test-leak guard) ───────────────────────────


def _run_git(args: list[str]) -> str:
    # argv is fixed git subcommands plus repo-internal paths, not untrusted
    # input; this driver legitimately shells out to the local git binary via
    # PATH (no shell, no user-controlled executable).
    cmd = ["git", *args]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)  # noqa: S603
    return result.stdout.strip()


def prepare_scratch_repo(upstream: str, base_commit: str, scratch_dir: Path) -> Path:
    """Pin a local scratch clone to `base_commit` on branch `main`, no remote.

    Idempotent: reusing an existing scratch dir already pinned to
    `base_commit` is a no-op; a scratch dir that exists but points elsewhere
    is a SystemExit (a setup/user error, not a pipeline failure -- nothing
    has been submitted yet).
    """
    if scratch_dir.exists():
        try:
            head = _run_git(["-C", str(scratch_dir), "rev-parse", "HEAD"])
            expected = _run_git(["-C", str(scratch_dir), "rev-parse", base_commit])
        except subprocess.CalledProcessError as exc:
            raise SystemExit(
                f"{scratch_dir} exists but is not a usable git repo: {exc.stderr}"
            ) from exc
        if head == expected:
            return scratch_dir
        raise SystemExit(
            f"{scratch_dir} exists at {head}, expected base_commit {base_commit} ({expected}) "
            "-- remove it or point --scratch-root elsewhere"
        )
    scratch_dir.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["clone", "--no-tags", upstream, str(scratch_dir)])
    _run_git(["-C", str(scratch_dir), "checkout", "-B", "main", base_commit])
    _run_git(["-C", str(scratch_dir), "remote", "remove", "origin"])
    # Gold-test leak guard, part 2: the upstream default branch (e.g. master)
    # still points at the clone-time tip, so future/gold history would remain
    # reachable via `git log --all`. Delete every local branch except main.
    for branch in _run_git(
        ["-C", str(scratch_dir), "for-each-ref", "--format=%(refname:short)", "refs/heads/"]
    ).splitlines():
        if branch and branch != "main":
            _run_git(["-C", str(scratch_dir), "branch", "-D", branch])
    return scratch_dir


def extract_patch(scratch_dir: Path, base_commit: str, branch_name: str) -> str:
    """The scored artifact: a two-dot diff against the pinned base, local only."""
    cmd = ["git", "-C", str(scratch_dir), "diff", base_commit, branch_name]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)  # noqa: S603
    except subprocess.CalledProcessError as exc:
        raise PipelineError(f"git diff failed: {exc.stderr}", "diff_extraction_failed") from exc
    return result.stdout


def extract_worktree_patch(scratch_dir: Path, base_commit: str, spec_id: str) -> str:
    """Fallback: diff the task worktree's WORKING TREE against base.

    A build that halts before its commit step (e.g. parked in human_review
    because tests could not run) leaves the produced code uncommitted in
    the worktree, so the branch diff is empty while the patch exists on
    disk. Untracked files (.aifactory/ artifacts) never appear in git diff,
    so no pathspec exclusion is needed.
    """
    worktree = scratch_dir / ".aifactory" / "worktrees" / "tasks" / spec_id
    if not worktree.is_dir():
        return ""
    cmd = ["git", "-C", str(worktree), "diff", base_commit]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)  # noqa: S603
    except subprocess.CalledProcessError:
        return ""
    return result.stdout


# ── opt-in per-task venv provisioning (so the coder can run repo tests) ────

_VENV_POLL_INTERVAL_SEC = 2
_VENV_POLL_TIMEOUT_SEC = 120


def _worktree_gitdir(worktree: Path) -> Path:
    """The real git-dir for `worktree`: a linked worktree's `.git` is a FILE
    containing `gitdir: <path>`; a regular repo/worktree has `.git` as a dir."""
    git_marker = worktree / ".git"
    if git_marker.is_file():
        return Path(git_marker.read_text().strip().removeprefix("gitdir:").strip())
    return git_marker


def _exclude_venv(worktree: Path) -> None:
    """Append `.venv/` to the worktree's git exclude file so a safety-net
    `git add -A` can never commit it into the scored branch."""
    exclude_path = _worktree_gitdir(worktree) / "info" / "exclude"
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    with exclude_path.open("a") as f:
        f.write(".venv/\n")


def provision_worktree_venv(
    scratch_dir: Path, spec_id: str, extra_deps: list[str], timeout_sec: int = 600
) -> bool:
    """Best-effort: create a venv in the task worktree and `pip install -e .`
    (plus any extra deps) so the coding agent can run the target repo's tests
    -- the host python is otherwise immutable/missing repo deps (design doc
    risk: build parks in human_review because tests can't run). This must
    NEVER fail the pipeline: any problem prints one warning and returns False.
    """
    worktree = scratch_dir / ".aifactory" / "worktrees" / "tasks" / spec_id
    deadline = time.monotonic() + _VENV_POLL_TIMEOUT_SEC
    while not worktree.is_dir():
        if time.monotonic() >= deadline:
            print(  # noqa: T201 -- CLI output
                f"provision_worktree_venv: {worktree} did not appear within "
                f"{_VENV_POLL_TIMEOUT_SEC}s -- skipping"
            )
            return False
        time.sleep(_VENV_POLL_INTERVAL_SEC)

    try:
        _exclude_venv(worktree)
        venv_result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "venv", str(worktree / ".venv")],
            cwd=worktree,
            capture_output=True,
            check=False,
            timeout=timeout_sec,
        )
        if venv_result.returncode != 0:
            raise RuntimeError(venv_result.stderr.decode(errors="replace"))
        pip = worktree / ".venv" / "bin" / "pip"
        pip_result = subprocess.run(  # noqa: S603
            [str(pip), "install", "-e", ".", *extra_deps],
            cwd=worktree,
            capture_output=True,
            check=False,
            timeout=timeout_sec,
        )
        if pip_result.returncode != 0:
            raise RuntimeError(pip_result.stderr.decode(errors="replace"))
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"provision_worktree_venv: best-effort venv setup failed: {exc}")  # noqa: T201
        return False
    return True


# ── AIFactory HTTP calls ─────────────────────────────────────────────────────


def _find_existing_project(client: HttpClient, name: str, path: str) -> str | None:
    resp = client.get("/api/projects")
    if not is_success(resp.status):
        return None
    items = resp.json.get("projects") or resp.json.get("items") or []
    for item in items:
        if item.get("name") == name or item.get("path") == path:
            return item.get("project_id") or item.get("id")
    return None


def register_project(client: HttpClient, scratch_dir: Path, instance_id: str) -> str:
    """POST /api/projects (path mode); reuse the project on a rerun instead of
    erroring on a name/path conflict."""
    name = f"swebench-{instance_id}"
    path = str(scratch_dir)
    resp = client.post("/api/projects", body={"path": path, "name": name})
    if is_success(resp.status):
        project_id = resp.json.get("project_id") or resp.json.get("id")
        if project_id:
            return project_id
        raise PipelineError(
            f"project create response missing id: {resp.json}", "project_registration_failed"
        )
    existing = _find_existing_project(client, name, path)
    if existing:
        return existing
    raise PipelineError(
        f"POST /api/projects -> {resp.status}: {resp.json}", "project_registration_failed"
    )


def submit_task(
    client: HttpClient, project_id: str, instance_id: str, problem_statement: str, tier: str
) -> tuple[str, str | None]:
    """POST /api/tasks/from-issue -- the only intake door that threads
    base_branch through to the worktree (design doc: "Intake: three doors")."""
    body = {
        "project_id": project_id,
        "payload": {
            "title": instance_id,
            "body": problem_statement,
            "labels": [f"tier:{tier}"],
        },
        "base_branch": "main",
        "auto_continue": True,
    }
    resp = client.post("/api/tasks/from-issue", body=body)
    if not is_success(resp.status):
        raise PipelineError(
            f"POST /api/tasks/from-issue -> {resp.status}: {resp.json}", "submit_failed"
        )
    task_id = resp.json.get("task_id") or resp.json.get("id")
    if not task_id:
        raise PipelineError(f"from-issue response missing task_id: {resp.json}", "submit_failed")
    return task_id, resp.json.get("spec_id")


@dataclass
class _Clock:
    """Real time by default; a test swaps in fake sleep/now to skip real waits."""

    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], float] = time.monotonic


def poll_task(
    client: HttpClient,
    task_id: str,
    timeout_min: int,
    poll_sec: int,
    *,
    clock: _Clock | None = None,
) -> None:
    """Poll GET /api/tasks/{id}/status to terminal (is_running == false).

    Prints phase/message only when it changes. `is_running == false` is not a
    verdict on its own (design doc) -- the caller re-reads `GET /api/tasks/{id}`
    for the authoritative `status`.
    """
    clock = clock or _Clock()
    deadline = clock.now() + timeout_min * 60
    last_seen: tuple[Any, Any] | None = None
    while True:
        resp = client.get(f"/api/tasks/{task_id}/status")
        if not is_success(resp.status):
            raise PipelineError(f"GET status -> {resp.status}: {resp.json}", "status_poll_failed")
        seen = (resp.json.get("phase"), resp.json.get("message"))
        if seen != last_seen:
            print(f"task {task_id}: phase={seen[0]} message={seen[1]}")  # noqa: T201 -- CLI output
            last_seen = seen
        if not resp.json.get("is_running", True):
            return
        if clock.now() >= deadline:
            raise PipelineError(f"task {task_id} did not finish within {timeout_min}min", "timeout")
        clock.sleep(poll_sec)


def get_task_detail(client: HttpClient, task_id: str) -> dict[str, Any]:
    resp = client.get(f"/api/tasks/{task_id}")
    if not is_success(resp.status):
        raise PipelineError(
            f"GET /api/tasks/{task_id} -> {resp.status}: {resp.json}", "task_detail_failed"
        )
    return resp.json


# ── evidence gate (cost/token source of truth) ──────────────────────────────


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _sum_tokens(data: dict[str, Any]) -> float | None:
    """Best-effort total_tokens extraction: a flat field, a nested `usage`
    block, or the v1.3 per-worker `usage` map (summed)."""
    if isinstance(data.get("total_tokens"), int | float):
        return data["total_tokens"]
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    if isinstance(usage.get("total_tokens"), int | float):
        return usage["total_tokens"]
    per_worker = [v.get("total_tokens") for v in usage.values() if isinstance(v, dict)]
    per_worker = [t for t in per_worker if isinstance(t, int | float)]
    return sum(per_worker) if per_worker else None


def _extract_cost(data: dict[str, Any]) -> float | None:
    for key in ("cost_usd", "total_cost_usd", "cost"):
        value = data.get(key)
        if isinstance(value, int | float):
            return value
    usage = data.get("usage")
    if isinstance(usage, dict):
        for key in ("cost_usd", "total_cost_usd", "cost"):
            value = usage.get(key)
            if isinstance(value, int | float):
                return value
    return None


def read_evidence(scratch_dir: Path, spec_id: str) -> dict[str, float | None]:
    """Source of truth: <scratch>/.aifactory/specs/<spec_id>/token_usage.json,
    falling back to COMPLETED.json for whichever field the first file lacks."""
    spec_dir = scratch_dir / ".aifactory" / "specs" / str(spec_id)
    evidence: dict[str, float | None] = {"total_tokens": None, "cost_usd": None}
    for name in ("token_usage.json", "COMPLETED.json"):
        data = _read_json(spec_dir / name)
        if data is None:
            continue
        if evidence["total_tokens"] is None:
            evidence["total_tokens"] = _sum_tokens(data)
        if evidence["cost_usd"] is None:
            evidence["cost_usd"] = _extract_cost(data)
    return evidence


def apply_evidence_gate(status: str, total_tokens: float | None) -> tuple[str, str | None]:
    """A "completed" verdict with total_tokens <= 0 (or missing) is a hollow
    pass (design doc risk #2: expired provider credential) -- downgrade it to
    failed with halt_reason="no_evidence". Any other status passes through."""
    if status == "completed" and (total_tokens is None or total_tokens <= 0):
        return "failed", "no_evidence"
    return status, None


# ── prediction + meta records ───────────────────────────────────────────────


def build_prediction_record(instance_id: str, diff: str) -> dict[str, str]:
    """The official SWE-bench harness prediction format."""
    return {
        "instance_id": instance_id,
        "model_name_or_path": MODEL_NAME,
        "model_patch": diff,
    }


def build_meta_record(
    instance_id: str, task_id: str | None, spec_id: str | None, outcome: dict[str, Any]
) -> dict[str, Any]:
    """`outcome` carries status/halt_reason/evidence/duration_sec (main() builds
    it from the evidence dict plus the verdict, keeping this under the
    max-args-5 lint cap without losing the sidecar's field set)."""
    return {
        "instance_id": instance_id,
        "task_id": task_id,
        "spec_id": spec_id,
        "status": outcome["status"],
        "halt_reason": outcome["halt_reason"],
        "total_tokens": outcome["total_tokens"],
        "cost_usd": outcome["cost_usd"],
        "duration_sec": round(outcome["duration_sec"], 1),
    }


def append_jsonl(out_path: Path, record: dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def write_meta_sidecar(out_path: Path, instance_id: str, meta: dict[str, Any]) -> None:
    sidecar = out_path.parent / f"{instance_id}.meta.json"
    sidecar.write_text(json.dumps(meta, indent=2) + "\n")


# ── CLI ──────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instance-id", required=True)
    ap.add_argument("--repo-url", required=True, help="upstream git URL")
    ap.add_argument("--base-commit", required=True)
    statement = ap.add_mutually_exclusive_group(required=True)
    statement.add_argument("--problem-statement-file", type=Path)
    statement.add_argument("--problem-statement")
    ap.add_argument("--scratch-root", default="./bench-scratch")
    ap.add_argument(
        "--aifactory-url",
        default=os.environ.get("AIFACTORY_URL", DEFAULT_AIFACTORY_URL),
    )
    ap.add_argument("--token", default=os.environ.get("APP_API_TOKEN", ""))
    ap.add_argument("--tier", default="medium")
    ap.add_argument("--timeout-min", type=int, default=90)
    ap.add_argument("--poll-sec", type=int, default=20)
    ap.add_argument("--out", required=True, help="predictions.jsonl append path")
    ap.add_argument(
        "--provision-venv",
        action="store_true",
        help="best-effort per-task venv so the coder can run the repo's tests",
    )
    ap.add_argument(
        "--extra-deps", default="", help="comma-separated extra pip packages for --provision-venv"
    )
    return ap.parse_args(argv)


def _load_problem_statement(args: argparse.Namespace) -> str:
    if args.problem_statement is not None:
        return args.problem_statement
    return args.problem_statement_file.read_text()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.monotonic()
    problem_statement = _load_problem_statement(args)
    scratch_dir = Path(args.scratch_root) / args.instance_id
    prepare_scratch_repo(args.repo_url, args.base_commit, scratch_dir)

    client = HttpClient(
        base_url=args.aifactory_url.rstrip("/"), auth=bearer_auth(args.token), timeout=30
    )

    task_id: str | None = None
    spec_id: str | None = None
    status = "failed"
    halt_reason: str | None = "pipeline_error"
    evidence: dict[str, float | None] = {"total_tokens": None, "cost_usd": None}
    diff = ""

    try:
        project_id = register_project(client, scratch_dir, args.instance_id)
        task_id, spec_id = submit_task(
            client, project_id, args.instance_id, problem_statement, args.tier
        )
        if args.provision_venv:
            if spec_id:
                extra_deps = [d.strip() for d in args.extra_deps.split(",") if d.strip()]
                provision_worktree_venv(scratch_dir, spec_id, extra_deps)
            else:
                print(  # noqa: T201 -- CLI output
                    f"[{args.instance_id}] --provision-venv requested but no spec_id yet"
                )
        poll_task(client, task_id, args.timeout_min, args.poll_sec)
        detail = get_task_detail(client, task_id)
        status = detail.get("status", "unknown")
        spec_id = spec_id or detail.get("spec_id")
        branch_name = detail.get("branch_name")
        if spec_id:
            evidence = read_evidence(scratch_dir, spec_id)
        status, halt_reason = apply_evidence_gate(status, evidence["total_tokens"])
        if branch_name:
            diff = extract_patch(scratch_dir, args.base_commit, branch_name)
        if not diff and spec_id:
            diff = extract_worktree_patch(scratch_dir, args.base_commit, spec_id)
            if diff:
                print(f"[{args.instance_id}] patch recovered from uncommitted worktree")  # noqa: T201
    except PipelineError as exc:
        halt_reason = exc.halt_reason
        status = "failed"
        print(f"[{args.instance_id}] pipeline failure ({halt_reason}): {exc}")  # noqa: T201

    if not diff:
        print(f"[{args.instance_id}] WARNING: empty diff (status={status})")  # noqa: T201

    out_path = Path(args.out)
    append_jsonl(out_path, build_prediction_record(args.instance_id, diff))
    outcome = {
        "status": status,
        "halt_reason": halt_reason,
        "total_tokens": evidence["total_tokens"],
        "cost_usd": evidence["cost_usd"],
        "duration_sec": time.monotonic() - started,
    }
    write_meta_sidecar(
        out_path,
        args.instance_id,
        build_meta_record(args.instance_id, task_id, spec_id, outcome),
    )

    return 0 if status == "completed" and halt_reason is None else 2


if __name__ == "__main__":
    sys.exit(main())
