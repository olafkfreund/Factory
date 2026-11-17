"""git_metadata baseline and remote-program refusal (#3737)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from agent_sandbox import check_git_metadata, merge_driver_pins, record_baseline


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FACTORY_GIT_BASELINE_DIR", str(tmp_path / "baselines"))
    r = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    return r


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def test_untouched_repo_passes(repo: Path) -> None:
    record_baseline(repo)
    check_git_metadata(repo)


@pytest.mark.parametrize(
    "key", ["merge.x.driver", "filter.x.smudge", "diff.x.textconv", "core.fsmonitor"]
)
def test_tampered_config_is_detected(repo: Path, key: str) -> None:
    record_baseline(repo)
    _git(repo, "config", key, "touch /tmp/pwned")
    with pytest.raises(RuntimeError, match="git metadata changed"):
        check_git_metadata(repo)


def test_tampered_attributes_are_detected(repo: Path) -> None:
    record_baseline(repo)
    (repo / ".git" / "info").mkdir(exist_ok=True)
    (repo / ".git" / "info" / "attributes").write_text("* merge=x\n")
    with pytest.raises(RuntimeError, match="info/attributes"):
        check_git_metadata(repo)


def test_rebaseline_accepts_the_change(repo: Path) -> None:
    record_baseline(repo)
    _git(repo, "config", "merge.x.driver", "true")
    record_baseline(repo, overwrite=True)
    check_git_metadata(repo)


def test_baseline_taken_late_when_missing(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    check_git_metadata(repo)
    assert "taken late" in capsys.readouterr().err
    _git(repo, "config", "merge.x.driver", "true")
    with pytest.raises(RuntimeError):
        check_git_metadata(repo)


def test_merge_driver_pins_runs_the_check(repo: Path) -> None:
    record_baseline(repo)
    _git(repo, "config", "merge.x.driver", "true")
    with pytest.raises(RuntimeError, match="git metadata changed"):
        merge_driver_pins(repo, env={"PATH": "/usr/bin:/bin"}, check=check_git_metadata)


@pytest.mark.parametrize("suffix", ["uploadpack", "receivepack", "vcs"])
@pytest.mark.parametrize("name", ["origin", "evil", "a.b"])
def test_remote_program_key_is_refused(repo: Path, name: str, suffix: str) -> None:
    _git(repo, "config", f"remote.{name}.{suffix}", "/tmp/x")
    with pytest.raises(RuntimeError, match="cannot be pinned"):
        merge_driver_pins(repo, env={})


def test_plain_remote_is_allowed(repo: Path) -> None:
    _git(repo, "remote", "add", "evil", "/tmp/nowhere")
    assert not any(p.startswith("remote.") for p in merge_driver_pins(repo, env={}))


def test_unpinnable_remote_program_would_run_without_the_refusal(tmp_path: Path) -> None:
    """Mutation witness: a -c override cannot beat the repo file (git keeps the first)."""
    bare = tmp_path / "o.git"
    work = tmp_path / "w"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    marker = tmp_path / "RAN"
    prog = tmp_path / "up.sh"
    prog.write_text(f'#!/bin/sh\ntouch {marker}\nexec git-upload-pack "$@"\n')
    prog.chmod(0o755)
    _git(work, "remote", "add", "evil", str(bare))
    _git(work, "config", "remote.evil.uploadpack", str(prog))
    subprocess.run(
        ["git", "-c", "remote.evil.uploadpack=git-upload-pack", "fetch", "evil"],
        cwd=work,
        check=False,
        capture_output=True,
    )
    assert marker.exists(), "git behaviour changed: a -c pin now overrides the repo file"
    marker.unlink()
    with pytest.raises(RuntimeError):
        merge_driver_pins(work, env={})


def test_reordered_duplicate_values_are_detected(repo: Path) -> None:
    _git(repo, "config", "--add", "diff.external", "safe")
    _git(repo, "config", "--add", "diff.external", "evil")
    record_baseline(repo)
    cfg = repo / ".git" / "config"
    text = cfg.read_text()
    cfg.write_text(
        text.replace("external = safe\n\texternal = evil", "external = evil\n\texternal = safe")
    )
    with pytest.raises(RuntimeError, match=r"diff\.external"):
        check_git_metadata(repo)


def test_rebaseline_command_fixes_a_linked_worktree(repo: Path, tmp_path: Path) -> None:
    _git(
        repo,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "x",
    )
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "b", str(wt))
    record_baseline(repo)
    record_baseline(wt, overwrite=True)
    _git(wt, "config", "extensions.worktreeConfig", "true")
    _git(wt, "config", "--worktree", "diff.external", "evil")
    with pytest.raises(RuntimeError) as err:
        check_git_metadata(wt)
    cmd = str(err.value).rsplit("--rebaseline ", 1)[1]
    assert Path(cmd) == wt.resolve()
    record_baseline(Path(cmd), overwrite=True)
    check_git_metadata(wt)


def test_carriage_return_change_is_detected(repo: Path) -> None:
    _git(repo, "config", "alias.probe", "!# harmless\rtouch /tmp/x")
    record_baseline(repo)
    cfg = repo / ".git" / "config"
    cfg.write_bytes(cfg.read_bytes().replace(b"\rtouch", b"\\ntouch"))
    with pytest.raises(RuntimeError, match="alias"):
        check_git_metadata(repo)


def test_recovery_hint_names_the_baseline_dir(repo: Path) -> None:
    record_baseline(repo)
    _git(repo, "config", "merge.x.driver", "true")
    with pytest.raises(RuntimeError, match="FACTORY_GIT_BASELINE_DIR="):
        check_git_metadata(repo)


def test_recovery_hint_quotes_a_path_with_spaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FACTORY_GIT_BASELINE_DIR", str(tmp_path / "b"))
    r = tmp_path / "my repo"
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    record_baseline(r)
    _git(r, "config", "merge.x.driver", "true")
    with pytest.raises(RuntimeError, match=r"--rebaseline '.*my repo'"):
        check_git_metadata(r)
