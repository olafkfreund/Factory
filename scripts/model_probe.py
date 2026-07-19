#!/usr/bin/env python3
"""Model-availability probe (#299).

Query each provider's live model list and diff it against the model ids the fleet
actually uses (AIFactory's ``core/model-catalog.json`` + ``phase_config.py``
``MODEL_ID_MAP``). Report-only: it never edits the catalog — a human decides which
stage adopts a new frontier model. It emits a JSON report to ``--out`` that the
``model-probe`` workflow turns into GitHub issues.

Findings:
  - ``new``        : an id the provider offers that we do not reference yet.
  - ``deprecated`` : an id we USE that the provider no longer lists (high priority).

Degrades, never fabricates: a provider with no API key (or an unreachable
endpoint) is reported as ``skipped`` and contributes no findings — an absent
provider is never treated as "everything deprecated".

Usage:
  model_probe.py --catalog path/to/model-catalog.json \
                 --phase-config path/to/phase_config.py \
                 --out probe-report.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

# id-prefix -> provider. Used both to bucket OUR ids and to compare against the
# right upstream list (a new gpt-* is not a "missing claude").
_PREFIXES = {
    "anthropic": ("claude-",),
    "openai": ("gpt-", "o1-", "o3-", "o4-", "chatgpt-", "codex"),
    "google": ("gemini-", "gemma-"),
}


# Runtime selectors, not literal provider model ids: the CLI/runtime picks the
# actual model. They never appear in a /v1/models list, so exclude them from the
# deprecated check (they are not deprecated — they are shorthands).
_RUNTIME_SHORTHANDS = {"codex", "gemini", "github-models", "claude-subagents", "dynamic-workflow"}


def _provider_of(model_id: str) -> str | None:
    if model_id in _RUNTIME_SHORTHANDS:
        return None
    for prov, prefixes in _PREFIXES.items():
        if model_id.startswith(prefixes):
            return prov
    return None


def _get_json(url: str, headers: dict[str, str], timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers=headers)  # noqa: S310 - https only, fixed hosts
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


def _anthropic_models() -> list[str]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise KeyError("ANTHROPIC_API_KEY")
    data = _get_json(
        "https://api.anthropic.com/v1/models?limit=1000",
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    return [m["id"] for m in data.get("data", []) if m.get("id")]


def _openai_models() -> list[str]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise KeyError("OPENAI_API_KEY")
    data = _get_json(
        "https://api.openai.com/v1/models",
        {"Authorization": f"Bearer {key}"},
    )
    return [m["id"] for m in data.get("data", []) if m.get("id")]


def _google_models() -> list[str]:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise KeyError("GEMINI_API_KEY/GOOGLE_API_KEY")
    data = _get_json(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=1000",
        {},
    )
    # names come back as "models/gemini-2.5-pro" — strip the prefix
    return [
        m["name"].split("/", 1)[-1]
        for m in data.get("models", [])
        if m.get("name")
    ]


_PROVIDERS = {
    "anthropic": _anthropic_models,
    "openai": _openai_models,
    "google": _google_models,
}


def _known_ids(catalog_path: str, phase_config_path: str | None) -> set[str]:
    """The model ids the fleet references: catalog keys/ids + MODEL_ID_MAP values."""
    ids: set[str] = set()
    with open(catalog_path) as f:
        catalog = json.load(f)
    # model-catalog.json is either {id: {...}} or {"models": [{"id": ...}]}
    if isinstance(catalog, dict):
        entries = catalog.get("models") if "models" in catalog else catalog
        if isinstance(entries, dict):
            ids.update(entries.keys())
            for v in entries.values():
                if isinstance(v, dict) and isinstance(v.get("id"), str):
                    ids.add(v["id"])
        elif isinstance(entries, list):
            ids.update(e["id"] for e in entries if isinstance(e, dict) and e.get("id"))
    # phase_config.py: pull any "provider-looking" id string literals
    if phase_config_path and os.path.exists(phase_config_path):
        text = open(phase_config_path).read()
        for m in re.findall(r"[\"'](claude-[\w.-]+|gpt-[\w.-]+|gemini-[\w.-]+)[\"']", text):
            ids.add(m)
    return {i for i in ids if _provider_of(i)}


def probe(
    catalog_path: str, phase_config_path: str | None, baseline: dict[str, list[str]]
) -> tuple[dict, dict[str, list[str]]]:
    """Return (report, updated_baseline).

    ``new`` is a TEMPORAL delta — upstream ids not in the last run's baseline —
    so a stable week reports zero, not "every model we do not use". A provider
    with no prior baseline is seeded silently (no first-run issue storm).
    ``deprecated`` compares the ids we USE against what the provider still lists.
    """
    known = _known_ids(catalog_path, phase_config_path)
    report: dict = {"providers": {}, "findings": []}
    new_baseline = dict(baseline)
    for prov, fetch in _PROVIDERS.items():
        our = {i for i in known if _provider_of(i) == prov}
        try:
            upstream = set(fetch())
        except KeyError as exc:
            report["providers"][prov] = {"status": "skipped", "reason": f"no key ({exc})"}
            continue
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as exc:
            report["providers"][prov] = {"status": "error", "reason": str(exc)[:200]}
            continue
        seen = set(baseline.get(prov, []))
        report["providers"][prov] = {
            "status": "ok",
            "upstream_count": len(upstream),
            "seeded": not seen,
        }
        # New only relative to the last baseline (skip the first-run seed).
        if seen:
            for mid in sorted(upstream - seen):
                report["findings"].append({"kind": "new", "provider": prov, "id": mid})
        for mid in sorted(our - upstream):
            report["findings"].append(
                {"kind": "deprecated", "provider": prov, "id": mid, "priority": "high"}
            )
        new_baseline[prov] = sorted(upstream)
    return report, new_baseline


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--phase-config", default=None)
    ap.add_argument("--out", default="probe-report.json")
    ap.add_argument(
        "--baseline",
        default="scripts/model_probe_baseline.json",
        help="last-seen upstream ids per provider; updated in place so 'new' is a temporal delta",
    )
    args = ap.parse_args()
    baseline: dict[str, list[str]] = {}
    if os.path.exists(args.baseline):
        with open(args.baseline) as f:
            baseline = json.load(f)
    report, new_baseline = probe(args.catalog, args.phase_config, baseline)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    with open(args.baseline, "w") as f:
        json.dump(new_baseline, f, indent=2, sort_keys=True)
    n_new = sum(1 for x in report["findings"] if x["kind"] == "new")
    n_dep = sum(1 for x in report["findings"] if x["kind"] == "deprecated")
    print(f"model-probe: {n_new} new, {n_dep} deprecated-in-use across providers")
    print(json.dumps(report["providers"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
