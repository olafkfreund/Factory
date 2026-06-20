#!/usr/bin/env python3
"""Self-test for the factory-contracts generator (scripts/gen_contracts.py).

Behaviour-locking tests for the generated single source of truth (Factory#160):

1. The committed generated output is NOT stale (``--check`` exits 0) - so a token
   set or schema field cannot drift from ``apis/status-taxonomy.json`` /
   ``apis/completion-events.asyncapi.yaml`` without the generator being rerun and
   the output recommitted.
2. The generated Python module imports and exposes the RFC-0001 envelope, the
   v1.1 usage block, the rollup helpers and the status classifiers.
3. The pydantic models accept the asyncapi examples and preserve unknown fields.
4. The classifiers match CFactory's canonical token-boundary semantics (the
   substring bug - ``'ready'`` matching ``'already'`` - stays fixed).

Skips cleanly when pydantic is unavailable (e.g. outside the Nix devShell);
the generated module is the only part that needs it - the generator itself does
not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO_ROOT / "scripts"
_GEN_PY = _REPO_ROOT / "shared" / "factory-contracts" / "python"
_TAXONOMY_JSON = _REPO_ROOT / "apis" / "status-taxonomy.json"

sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_GEN_PY))

import gen_contracts as gc  # noqa: E402  (path set above)

# The generated module needs pydantic; the generator itself does not. Skip the
# whole module cleanly outside the devShell rather than failing at import.
fc = pytest.importorskip("factory_contracts")


def test_committed_output_is_not_stale() -> None:
    """`gen_contracts.py --check` must pass: committed output matches the inputs."""
    assert gc.generate(check=True) == 0


def test_generator_is_idempotent() -> None:
    """Rendering twice yields byte-identical output (deterministic ordering)."""
    taxonomy = gc.load_taxonomy()
    assert gc.render_python(taxonomy) == gc.render_python(gc.load_taxonomy())
    assert gc.render_typescript(taxonomy) == gc.render_typescript(gc.load_taxonomy())


def test_token_sets_match_taxonomy_json() -> None:
    """The generated Python token sets equal the canonical JSON token sets."""
    data = json.loads(_TAXONOMY_JSON.read_text(encoding="utf-8"))["states"]
    assert frozenset(data["failed"]["tokens"]) == fc._FAILED_TOKENS
    assert frozenset(data["done"]["tokens"]) == fc._DONE_TOKENS
    assert frozenset(data["review"]["tokens"]) == fc._REVIEW_TOKENS
    assert frozenset(data["queued"]["tokens"]) == fc._QUEUED_TOKENS
    assert frozenset(data["running"]["tokens"]) == fc._RUNNING_TOKENS
    assert frozenset(data["stuck"]["tokens"]) == fc._STUCK_TOKENS


def test_completion_event_accepts_examples_and_preserves_unknown() -> None:
    """The pydantic envelope round-trips the asyncapi examples + extra fields."""
    ev = fc.CompletionEvent(
        correlation_key="142",
        service="aifactory",
        task_id="proj:001",
        status="done",
        phase="act",
        updated_at="2026-06-05T12:00:00+00:00",
        usage=fc.Usage(input_tokens=2400, output_tokens=100, total_tokens=2500, cost_usd=1.25),
        future_field="ignored-but-kept",  # type: ignore[call-arg]
    )
    assert ev.usage is not None
    assert ev.usage.total_tokens == 2500
    # Unknown fields are preserved, not dropped (extra="allow").
    assert ev.model_dump()["future_field"] == "ignored-but-kept"


def test_usage_rollup_sums_fieldwise() -> None:
    """add_usage / rollup_usage sum tokens + cost and carry the first model."""
    total = fc.rollup_usage(
        [
            fc.Usage(input_tokens=10, output_tokens=5, cost_usd=0.5, model="sonnet"),
            fc.Usage(input_tokens=2, cost_usd=0.1),
            None,
        ]
    )
    assert total.input_tokens == 12
    assert total.output_tokens == 5
    assert total.cost_usd == pytest.approx(0.6)
    assert total.model == "sonnet"


def test_status_classifiers_use_token_boundaries() -> None:
    """Classifiers mirror CFactory's exact-token semantics (no substring bug)."""
    assert fc.is_terminal("done") and fc.is_terminal("failed")
    assert fc.is_done("skipped") and fc.is_done("human_review") is False
    assert fc.is_failed("rejected") and not fc.is_failed("ready")
    # The historical substring bug: 'ready' must NOT match 'already'.
    assert not fc.is_done("already")
    assert fc.is_review("human_review") and fc.is_queued("backlog")
    assert fc.is_failure_or_stuck("stuck") and not fc.is_failed("stuck")
    assert fc.is_running("coding") and not fc.is_running("done")
    assert fc.is_running(None) is False
    assert fc.is_active(None) is True and not fc.is_active("done")
