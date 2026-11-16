"""git_pins: config pins and merge-driver / filter pins (#3709)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from agent_sandbox import child_env, merge_driver_pins, pin_git_config
from policies import PFACTORY


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def test_pin_git_config_appends_after_existing():
    env = pin_git_config({"GIT_CONFIG_COUNT": "2"})
    assert env["GIT_CONFIG_COUNT"] == "12"
    assert env["GIT_CONFIG_KEY_2"] == "core.hooksPath"
    assert env["GIT_CONFIG_VALUE_4"] == "never"
    assert env["GIT_CONFIG_VALUE_5"] == "ssh"
    assert env["GIT_CONFIG_VALUE_6"] == "cat" and env["GIT_PAGER"] == "cat"
    assert env["GIT_CONFIG_VALUE_7"] == "true"


@pytest.mark.parametrize("count", ["x", "-5"])
def test_pin_git_config_bad_count_restarts_at_zero(count):
    assert pin_git_config({"GIT_CONFIG_COUNT": count})["GIT_CONFIG_COUNT"] == "10"


def test_child_env_pins_hooks(tmp_path):
    env = child_env(PFACTORY, agent=True)
    assert _git_hooks_path(tmp_path, env) == "/dev/null"


def _git_hooks_path(cwd: Path, env: dict[str, str]) -> str:
    subprocess.run(["git", "init", "-q", str(cwd)], check=True)
    return subprocess.run(
        ["git", "config", "core.hooksPath"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def iso_env(tmp_path: Path) -> dict[str, str]:
    """Env that ignores the machine's own git config (lfs filters and the like)."""
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }


@pytest.fixture
def evil_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "merge.x.driver", "touch pwned")
    _git(tmp_path, "config", "filter.y.clean", "touch pwned")
    _git(tmp_path, "config", "filter.y.smudge", "cat")
    _git(tmp_path, "config", "filter.y.process", "cat")
    _git(tmp_path, "config", "filter.y.required", "true")
    _git(tmp_path, "config", "merge.z.name", "keep")
    return tmp_path


def test_pins_driver_and_filters_not_others(evil_repo, iso_env):
    pins = merge_driver_pins(evil_repo, env=iso_env)
    keys = pins[1::2]
    assert set(pins[0::2]) == {"-c"}
    assert sorted(keys) == [
        "filter.y.clean=", "filter.y.process=", "filter.y.smudge=", "merge.x.driver=",
    ]  # fmt: skip


def test_pins_neutralise_driver_and_filter(evil_repo, iso_env):
    pins = merge_driver_pins(evil_repo, env=iso_env)
    (evil_repo / "f").write_text("a\n")
    (evil_repo / ".git" / "info").mkdir(exist_ok=True)
    (evil_repo / ".git" / "info" / "attributes").write_text("* filter=y merge=x\n")
    _git(evil_repo, "config", "filter.y.required", "false")
    subprocess.run(
        ["git", *pins, "add", "f"], cwd=evil_repo, env=iso_env, check=True, capture_output=True
    )
    assert not (evil_repo / "pwned").exists()


def test_run_injected_and_check_called():
    calls = []

    def run(argv):
        calls.append(argv)
        return 0, "merge.a.driver\0core.bare\0"

    seen = []
    pins = merge_driver_pins(".", run=run, check=lambda c, r: seen.append((c, r)))
    assert pins == ["-c", "merge.a.driver="]
    assert calls[0][:2] == ["git", "config"] and seen == [(".", run)]


def test_check_failure_propagates():
    def boom(cwd, run):
        raise RuntimeError("metadata changed")

    with pytest.raises(RuntimeError, match="metadata"):
        merge_driver_pins(".", run=lambda a: (0, ""), check=boom)


@pytest.mark.parametrize(
    ("result", "msg"),
    [((1, ""), "exited 1"), ((0, "merge.a=b.driver\0"), "contains '='")],
)
def test_fail_closed(result, msg):
    with pytest.raises(RuntimeError, match=msg):
        merge_driver_pins(".", run=lambda a: result)


def test_run_oserror_is_runtime_error():
    def run(argv):
        raise OSError("gone")

    with pytest.raises(RuntimeError, match="git config failed"):
        merge_driver_pins(".", run=run)


def test_non_utf8_subsection_round_trips(tmp_path):
    out = "merge.\udcff.driver\0"
    assert merge_driver_pins(tmp_path, run=lambda a: (0, out)) == [
        "-c",
        "merge.\udcff.driver=",
    ]


def test_needs_env_or_run():
    # No hidden child_env default: git_pins must not import env (CodeQL cyclic import).
    with pytest.raises(ValueError, match="env or run"):
        merge_driver_pins(".")
