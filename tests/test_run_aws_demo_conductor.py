"""Exercise the AWS demo conductor with local tools only (Factory#3839)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

CONDUCTOR = Path(__file__).resolve().parents[1] / ".claude/skills/run-aws-demo/conductor.sh"
RunConductor = Callable[..., tuple[subprocess.CompletedProcess[str], str]]
STUB = r"""#!/usr/bin/env bash
tool=${0##*/}
printf '%s %s\n' "$tool" "$*" >> "$STUB_LOG"
case "$tool" in
  docker) [ "$1" = login ] && cat > /dev/null; exit 0 ;;  # drain stdin (SIGPIPE race)
  python3)
    if [ "${1:-}" = -m ] && [ "${2:-}" = pytest ]; then
      [ "${STUB_PYTEST_FAIL:-0}" != 1 ]
      exit $?
    fi
    exec "$REAL_PYTHON" "$@" ;;
  terraform)
    infra=${1#-chdir=}; shift
    case "$1" in
      init) mkdir -p "$infra/.terraform" ;;
      validate) [ "${STUB_FAIL_VALIDATE:-0}" != 1 ] ;;
      apply)
        if [[ " $* " != *' -target='* ]] && [ "${STUB_FAIL_APPLY:-0}" = 1 ]; then
          printf '%s%s\n' 'Error: creating App Runner Service: InvalidRequestException: ' \
            "Account 1234 can't create new App Runner services." >&2
          exit 1
        fi ;;
      destroy) [ "${STUB_FAIL_DESTROY:-0}" != 1 ] ;;
      output)
        if [ "$3" = url_frontend ] || [ "$3" = url_scoreboard ]; then
          [ "${STUB_EMPTY_URL:-0}" = 1 ] || printf 'https://%s.example.invalid\n' "$3"
        else
          printf '1234.dkr.ecr.example.invalid/%s\n' "$3"
        fi ;;
    esac ;;
  aws)
    case "$1 $2" in
      'sts get-caller-identity') echo 1234 ;;
      'ecr get-login-password') echo dummy ;;
      'apprunner list-services')
        if [[ " $* " = *' --max-items '* ]] && [ "${STUB_FAIL_PREFLIGHT:-0}" = 1 ]; then exit 1; fi
        echo '[]' ;;
      'logs describe-log-groups')
        if [ "${STUB_FAIL_LOGS:-0}" = 1 ]; then exit 1; fi
        echo '[]' ;;
    esac ;;
  curl) echo '{}' ;;
esac
"""


@pytest.fixture
def run_conductor(tmp_path: Path) -> RunConductor:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("terraform", "aws", "docker", "curl", "python3"):
        stub = bin_dir / tool
        stub.write_text(STUB)
        stub.chmod(0o755)
    envrc = tmp_path / "envrc"
    envrc.write_text("AWS_ACCESS_KEY_ID=dummy\nAWS_SECRET_ACCESS_KEY=dummy\n")
    log = tmp_path / "calls.log"
    workspace = tmp_path / "w"
    env = os.environ.copy()
    env.update(
        PATH=f"{bin_dir}:{env['PATH']}",
        REAL_PYTHON=sys.executable,
        STUB_LOG=str(log),
        ENVRC=str(envrc),
        W=str(workspace),
        REGION="eu-west-2",
        SPEC="stub",
    )

    def run(*args: str, **flags: str) -> tuple[subprocess.CompletedProcess[str], str]:
        result = subprocess.run(  # noqa: S603 - fixed local script and stub arguments
            [shutil.which("bash") or "/bin/bash", str(CONDUCTOR), *args],
            env=env | flags,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return result, log.read_text() if log.exists() else ""

    return run


def test_apply_failure_quotes_error_and_destroys(run_conductor: RunConductor) -> None:
    result, calls = run_conductor(STUB_FAIL_APPLY="1")
    assert result.returncode != 0
    assert "GREEN" not in result.stdout + result.stderr
    assert "can't create new App Runner services" in result.stderr
    assert "Owner step: open an AWS" in result.stderr
    assert "terraform -chdir=" in calls and " destroy " in calls


def test_all_pass_and_destroy(run_conductor: RunConductor) -> None:
    result, calls = run_conductor()
    assert result.returncode == 0, result.stderr
    assert "GREEN" in result.stdout
    assert " destroy " in calls


@pytest.mark.parametrize("flag", ["STUB_EMPTY_URL", "STUB_PYTEST_FAIL"])
def test_verification_failure_never_green(run_conductor: RunConductor, flag: str) -> None:
    result, calls = run_conductor(**{flag: "1"})
    assert result.returncode != 0
    assert "GREEN" not in result.stdout + result.stderr
    assert " destroy " in calls


def test_validate_failure_stops_before_apply(run_conductor: RunConductor) -> None:
    result, calls = run_conductor(STUB_FAIL_VALIDATE="1")
    assert result.returncode != 0
    assert "GREEN" not in result.stdout + result.stderr
    assert " apply " not in calls
    assert " destroy " in calls


def test_destroy_failure_changes_success_status(run_conductor: RunConductor) -> None:
    result, calls = run_conductor(STUB_FAIL_DESTROY="1")
    assert result.returncode != 0
    assert "GREEN" in result.stdout
    assert " destroy " in calls


def test_primary_failure_survives_cleanup_failure(run_conductor: RunConductor) -> None:
    result, calls = run_conductor(STUB_FAIL_APPLY="1", STUB_FAIL_DESTROY="1")
    assert result.returncode != 0
    assert "GREEN" not in result.stdout + result.stderr
    assert "can't create new App Runner services" in result.stderr
    assert " destroy " in calls


def test_log_listing_failure_changes_success_status(run_conductor: RunConductor) -> None:
    result, calls = run_conductor(STUB_FAIL_LOGS="1")
    assert result.returncode != 0
    assert "log group listing FAILED" in result.stderr
    assert "apprunner list-services" in calls


def test_keep_skips_destroy(run_conductor: RunConductor) -> None:
    result, calls = run_conductor("--keep")
    assert result.returncode == 0, result.stderr
    assert "GREEN" in result.stdout
    assert " destroy " not in calls


def test_preflight_preserves_existing_workspace(
    run_conductor: RunConductor, tmp_path: Path
) -> None:
    workspace = tmp_path / "w"
    workspace.mkdir()
    marker = workspace / "marker"
    marker.write_text("keep")
    result, calls = run_conductor(STUB_FAIL_PREFLIGHT="1")
    assert result.returncode != 0
    assert "GREEN" not in result.stdout + result.stderr
    assert " destroy " not in calls
    assert marker.read_text() == "keep"


def test_existing_state_is_not_wiped(run_conductor: RunConductor, tmp_path: Path) -> None:
    infra = tmp_path / "w" / "infra"
    infra.mkdir(parents=True)
    state = infra / "terraform.tfstate"
    state.write_text('{"resources":[{"type":"aws_apprunner_service"}]}')
    result, calls = run_conductor()
    assert result.returncode != 0
    assert "destroy -auto-approve first" in result.stderr
    assert " destroy " not in calls
    assert state.exists()
