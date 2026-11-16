#!/usr/bin/env python3
"""What produced a benchmark run: model ids, prompt hash, service commits (Factory#3713).

Replaces the old constant `MODEL_NAME = "factory-pipeline"`: two runs that
differ in models, prompts or service code now get different labels.

Checkout locations come from env vars, never guessed:
  AIFACTORY_DIR (required for models and prompts), PFACTORY_DIR, TFACTORY_DIR,
  CFACTORY_DIR (optional, commit only). The Factory repo is the working tree
  this file lives in.
  NIGHTLY_MODEL_OVERRIDES: JSON {role: model} that MUST mirror the server's
  environment; it is recorded, not applied.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

FACTORY_DIR = Path(__file__).resolve().parents[2]
# shortcut: the aliases ("opus") are recorded as configured, not resolved
# through AIFactory's model map, so see models_observed for what ran; upgrade
# if a stable resolve API appears.
PHASE_CONFIG = Path("apps/backend/phase_config.py")


def read_default_models(aifactory_dir: Path) -> dict[str, str]:
    """DEFAULT_PHASE_MODELS from phase_config.py by AST, never imported."""
    tree = ast.parse((aifactory_dir / PHASE_CONFIG).read_text())
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "DEFAULT_PHASE_MODELS"
            and node.value is not None
        ):
            value = ast.literal_eval(node.value)
            return {str(k): str(v) for k, v in value.items()}
    raise ValueError(f"DEFAULT_PHASE_MODELS not found in {aifactory_dir / PHASE_CONFIG}")


def prompt_hash(root: Path, globs: list[str]) -> str:
    """sha256 over sorted (relative path, bytes) of every matching file."""
    files = sorted({p for g in globs for p in root.glob(g) if p.is_file()})
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def git_head(repo: Path | None) -> str | None:
    if repo is None or not (repo / ".git").exists():
        return None
    # fixed argv, local git binary, no shell
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def collect(config: dict[str, Any], env: dict[str, str] | None = None) -> dict[str, Any]:
    env = dict(os.environ) if env is None else env
    aif = Path(env["AIFACTORY_DIR"]) if env.get("AIFACTORY_DIR") else None
    if aif is None:
        raise SystemExit("AIFACTORY_DIR is not set: cannot record models and prompt hash")
    models = read_default_models(aif)
    models.update(json.loads(env.get("NIGHTLY_MODEL_OVERRIDES") or "{}"))
    commits: dict[str, str | None] = {"Factory": git_head(FACTORY_DIR)}
    for service in config["services"]:
        value = env.get(f"{service.upper()}_DIR")
        commits[service] = git_head(Path(value) if value else None)
    return {
        "models_configured": models,
        "prompt_hash": prompt_hash(aif, config["prompt_globs"]),
        "commits": commits,
    }


def label(prov: dict[str, Any]) -> str:
    """Safe-for-filename run label; changes when models, prompts or commits do."""
    key = json.dumps(
        [prov["models_configured"], prov["prompt_hash"], prov["commits"]], sort_keys=True
    )
    return f"factory-pipeline-{hashlib.sha256(key.encode()).hexdigest()[:8]}"
