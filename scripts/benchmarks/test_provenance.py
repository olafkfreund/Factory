"""Tests for provenance.py (Factory#3713). Local files and git only."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import provenance as pv

CONFIG = {"services": ["AIFactory", "PFactory"], "prompt_globs": ["apps/backend/prompts/**/*.md"]}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True)  # noqa: S603, S607


def _aifactory(tmp_path: Path, model: str = "opus") -> Path:
    root = tmp_path / "AIFactory"
    (root / "apps/backend/prompts/sub").mkdir(parents=True)
    (root / "apps/backend/phase_config.py").write_text(
        f'DEFAULT_PHASE_MODELS: dict[str, str] = {{"coding": "{model}", "qa": "opus"}}\n'
    )
    (root / "apps/backend/prompts/a.md").write_text("one")
    (root / "apps/backend/prompts/sub/b.md").write_text("two")
    _git(root, "init", "-q")
    _git(
        root,
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
    return root


def test_models_read_without_import(tmp_path: Path) -> None:
    root = _aifactory(tmp_path, "sonnet")
    assert pv.read_default_models(root) == {"coding": "sonnet", "qa": "opus"}


def test_prompt_hash_changes_with_content_and_ignores_unmatched(tmp_path: Path) -> None:
    root = _aifactory(tmp_path)
    globs = CONFIG["prompt_globs"]
    first = pv.prompt_hash(root, globs)
    (root / "apps/backend/prompts/other.txt").write_text("ignored")
    assert pv.prompt_hash(root, globs) == first
    (root / "apps/backend/prompts/sub/b.md").write_text("changed")
    assert pv.prompt_hash(root, globs) != first


def test_collect_records_commits_and_nulls(tmp_path: Path) -> None:
    root = _aifactory(tmp_path)
    prov = pv.collect(CONFIG, {"AIFACTORY_DIR": str(root)})
    assert len(prov["commits"]["AIFactory"]) == 40
    assert prov["commits"]["PFactory"] is None
    assert prov["models_configured"]["coding"] == "opus"


def test_override_and_label_change(tmp_path: Path) -> None:
    root = _aifactory(tmp_path)
    base = pv.collect(CONFIG, {"AIFACTORY_DIR": str(root)})
    over = pv.collect(
        CONFIG, {"AIFACTORY_DIR": str(root), "NIGHTLY_MODEL_OVERRIDES": '{"coding": "x"}'}
    )
    assert over["models_configured"]["coding"] == "x"
    assert pv.label(base) != pv.label(over)
    assert pv.label(base) == pv.label(base)


def test_missing_aifactory_dir_is_an_error() -> None:
    with pytest.raises(SystemExit):
        pv.collect(CONFIG, {})
