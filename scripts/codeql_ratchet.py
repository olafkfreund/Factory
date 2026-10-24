#!/usr/bin/env python3
"""CodeQL ratchet: fail when open alerts exceed the committed baseline (Factory#813).

Counts the calling repo's open code-scanning alerts at critical, high, error
and medium severity and compares each with ``.github/codeql-baseline.json``.
GITHUB_TOKEN reads only its own repo's alerts, so this runs from a reusable
workflow inside each repo (``.github/workflows/codeql-ratchet.yml``).

Each alert lands in ONE bucket: its security severity (critical/high/medium/low)
when it has one, else its rule severity (error/warning/note). A high security
alert is therefore not also counted as an error.

Usage:
    codeql_ratchet.py --repo OWNER/NAME [--baseline PATH]
    codeql_ratchet.py --self-test

Exit codes: 0 within baseline, 1 above baseline or unreadable input.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

TRACKED = ("critical", "high", "error", "medium")


def count(alerts: list[dict]) -> dict[str, int]:
    counts = dict.fromkeys(TRACKED, 0)
    for alert in alerts:
        rule = alert.get("rule") or {}
        bucket = rule.get("security_severity_level") or rule.get("severity")
        if bucket in counts:
            counts[bucket] += 1
    return counts


def compare(current: dict[str, int], baseline: dict[str, int]) -> tuple[bool, list[str]]:
    """Return (ok, report lines). A missing baseline key means 0."""
    lines, ok = [], True
    for sev in TRACKED:
        cur, base = current[sev], baseline.get(sev, 0)
        lines.append(f"{sev}: {cur} / baseline {base} ({cur - base:+d})")
        ok = ok and cur <= base
    if ok and any(current[s] < baseline.get(s, 0) for s in TRACKED):
        lines.append("below baseline: lower .github/codeql-baseline.json to lock it in")
    return ok, lines


def fetch(repo: str) -> list[dict]:
    out = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", f"repos/{repo}/code-scanning/alerts?state=open&per_page=100"],
        check=True, capture_output=True, text=True,
    ).stdout
    return [a for page in json.loads(out) for a in page]


def _self_test() -> int:
    def alert(sec: str | None, sev: str) -> dict:
        return {"rule": {"security_severity_level": sec, "severity": sev}}

    got = count([alert("high", "error"), alert(None, "error"), alert("medium", "warning"),
                 alert("critical", "error"), alert("low", "warning"), alert(None, "note"), {}])
    assert got == {"critical": 1, "high": 1, "error": 1, "medium": 1}, got
    ok, _ = compare(got, {"critical": 1, "high": 1, "error": 1, "medium": 1})
    assert ok
    ok, lines = compare(got, {"critical": 1, "high": 0})  # missing keys are 0
    assert not ok and "high: 1 / baseline 0 (+1)" in lines
    ok, lines = compare(dict.fromkeys(TRACKED, 0), {"high": 2})
    assert ok and any("below baseline" in line for line in lines)
    print("self-test ok")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo")
    ap.add_argument("--baseline", default=".github/codeql-baseline.json")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if not args.repo:
        ap.error("--repo is required")
    try:
        with open(args.baseline, encoding="utf-8") as f:
            baseline = json.load(f)
        current = count(fetch(args.repo))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"CANNOT VERIFY: {exc}")  # no answer must not read as success
        return 1
    ok, lines = compare(current, baseline)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
