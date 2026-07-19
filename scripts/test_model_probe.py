#!/usr/bin/env python3
"""Offline self-check for the model-availability probe (#299) — no network, no
pytest. Run: python3 scripts/test_model_probe.py"""

import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_probe as mp


def _catalog(d: Path, ids):
    p = d / "catalog.json"
    p.write_text(json.dumps({mid: {"id": mid} for mid in ids}))
    return str(p)


@contextmanager
def _providers(anthropic=(), openai=(), google=()):
    orig = dict(mp._PROVIDERS)
    mp._PROVIDERS["anthropic"] = lambda: list(anthropic)
    mp._PROVIDERS["openai"] = lambda: list(openai)
    mp._PROVIDERS["google"] = lambda: list(google)
    try:
        yield
    finally:
        mp._PROVIDERS.clear()
        mp._PROVIDERS.update(orig)


def _kinds(report, kind):
    return [f["id"] for f in report["findings"] if f["kind"] == kind]


def run():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)

        # 1. "new" is a temporal delta vs the baseline, not upstream-minus-catalog
        cat = _catalog(d, ["claude-opus-4-8"])
        with _providers(anthropic=["claude-opus-4-8", "claude-opus-4-9"]):
            rep, nb = mp.probe(cat, None, {"anthropic": ["claude-opus-4-8"]})
        assert _kinds(rep, "new") == ["claude-opus-4-9"], _kinds(rep, "new")
        assert "claude-opus-4-9" in nb["anthropic"]

        # 2. first run (no baseline) seeds silently — no "new" storm
        with _providers(anthropic=["claude-opus-4-8", "claude-x", "claude-y"]):
            rep, _ = mp.probe(cat, None, {})
        assert _kinds(rep, "new") == [], _kinds(rep, "new")

        # 3. a USED id missing upstream is a high-priority deprecated finding
        cat2 = _catalog(d, ["claude-opus-4-8", "claude-old"])
        with _providers(anthropic=["claude-opus-4-8"]):
            rep, _ = mp.probe(cat2, None, {"anthropic": ["claude-opus-4-8", "claude-old"]})
        dep = [(f["id"], f.get("priority")) for f in rep["findings"] if f["kind"] == "deprecated"]
        assert dep == [("claude-old", "high")], dep

        # 4. runtime shorthands (codex/gemini) are never flagged
        cat3 = _catalog(d, ["codex", "gemini"])
        with _providers(openai=["gpt-4o"], google=["gemini-2.5-pro"]):
            rep, _ = mp.probe(cat3, None, {"openai": ["gpt-4o"], "google": ["gemini-2.5-pro"]})
        assert [f for f in rep["findings"] if f["kind"] == "deprecated"] == []

        # 5. a keyless provider is skipped — never "everything deprecated"
        cat4 = _catalog(d, ["claude-opus-4-8"])

        def _raise():
            raise KeyError("ANTHROPIC_API_KEY")

        orig = dict(mp._PROVIDERS)
        mp._PROVIDERS["anthropic"] = _raise
        mp._PROVIDERS["openai"] = lambda: []
        mp._PROVIDERS["google"] = lambda: []
        try:
            rep, _ = mp.probe(cat4, None, {"anthropic": ["claude-opus-4-8"]})
        finally:
            mp._PROVIDERS.clear()
            mp._PROVIDERS.update(orig)
        assert rep["providers"]["anthropic"]["status"] == "skipped"
        assert [f for f in rep["findings"] if f["kind"] == "deprecated"] == []

    print("model_probe self-check: all 5 checks passed")  # noqa: T201


if __name__ == "__main__":
    run()
