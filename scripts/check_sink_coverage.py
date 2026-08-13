#!/usr/bin/env python3
"""Fail CI when a security-sensitive sink call site is not routed through its guard.

Factory security-cleanup review (2026-08-13). A correct SSRF guard was
written, tested, mutation-checked — and wired into 1 of 14 call sites. Every
signal was green (the guard's own tests, the guard's own mutation check)
because nothing checked that every SINK actually called it. Same shape
independently in a second repo. CodeQL and unit tests both look at the guard
or a call site in isolation; neither asserts "every call site of this shape
uses that guard."

This is a per-line heuristic (grep/AST-lite), not a dataflow analysis — it
does not need to be perfect, it needs to fail when sink call #15 is added
without the guard. Two knobs keep it from being a nuisance:

  - a `--window` of source lines around a sink call in which a guard call
    must appear (same function body in practice, cheap to approximate as
    "nearby lines" rather than parsing scopes)
  - an inline opt-out: a sink line (or the line immediately above it) carrying
    a comment matching ``sink-guard-exempt: <reason>`` is skipped — for
    genuinely trusted-input call sites (e.g. reading a hardcoded internal URL)

Sink classes (Factory brief, Gate 4):
  - outbound HTTP: httpx.get/post/put/delete/request, requests.get/post/...,
    urllib.request.urlopen — must be near a call matching --http-guard
  - subprocess with argv built from request data: subprocess.run/Popen/call/
    check_output — must be near a call matching --argv-guard
  - path joins from request data: Path(...) / os.path.join(...) — must be
    near a call matching --path-guard

Guard patterns are passed in rather than hardcoded because each repo names
its guard differently and this script is meant to be one reusable
implementation, not six copies with six sink lists baked in.

Usage:
    python scripts/check_sink_coverage.py --root . \
        --http-guard 'url_safety\\.|guard_url\\(|is_safe_url\\(' \
        --argv-guard 'argv_safety\\.|safe_argv\\(' \
        --path-guard 'path_containment\\.|safe_join\\('

    python scripts/check_sink_coverage.py --self-test

Exit codes:
    0 - every sink call site is within --window lines of a matching guard call
        (or carries an explicit opt-out comment)
    1 - an unguarded sink call site was found
    2 - bad invocation
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "vendor", "tests", "test",
}

_OPT_OUT = re.compile(r"sink-guard-exempt:\s*\S")


@dataclass(frozen=True)
class SinkClass:
    name: str
    sink_pattern: re.Pattern[str]
    guard_env_flag: str  # which CLI arg supplies this class's guard regex


SINK_CLASSES: tuple[SinkClass, ...] = (
    SinkClass(
        "outbound-http",
        re.compile(r"\b(httpx\.(get|post|put|delete|patch|request)|requests\.(get|post|put|delete|patch|request)|urlopen)\s*\("),
        "http_guard",
    ),
    SinkClass(
        "subprocess-argv",
        re.compile(r"\bsubprocess\.(run|Popen|call|check_output|check_call)\s*\("),
        "argv_guard",
    ),
    SinkClass(
        "path-join",
        re.compile(r"(\bos\.path\.join\s*\(|Path\([^)]*\)\s*/)"),
        "path_guard",
    ),
)


def _iter_source_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        out.append(path)
    return out


def find_unguarded(
    root: Path,
    guards: dict[str, re.Pattern[str] | None],
    window: int = 8,
) -> list[str]:
    problems: list[str] = []
    for path in _iter_source_files(root):
        rel = str(path.relative_to(root))
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for sink_class in SINK_CLASSES:
            guard = guards.get(sink_class.guard_env_flag)
            if guard is None:
                continue
            for i, line in enumerate(lines):
                if not sink_class.sink_pattern.search(line):
                    continue
                lo, hi = max(0, i - 1), min(len(lines), i + window)
                context = "\n".join(lines[lo:hi])
                if _OPT_OUT.search(context):
                    continue
                if guard.search(context):
                    continue
                problems.append(
                    f"{rel}:{i + 1}: [{sink_class.name}] sink call with no "
                    f"guard within {window} lines — {line.strip()}"
                )
    return problems


def run_check(root: Path, guards: dict[str, re.Pattern[str] | None], window: int) -> int:
    active = [name for name, pat in guards.items() if pat is not None]
    if not active:
        # Rule 4.10 ("assert on the artefact, not on the process"): a run
        # with every guard pattern unset would silently check nothing and
        # still print OK — indistinguishable from a real pass. That is the
        # exact shape of "1 of 14 call sites wired" reading green. Fail loud
        # instead of reporting a vacuous success.
        print(  # noqa: T201
            "ERROR: no --http-guard/--argv-guard/--path-guard given — this run "
            "would check zero sink classes and report OK regardless of coverage."
        )
        return 1
    problems = find_unguarded(root, guards, window)
    print(f"sink-coverage: scanned {root} for classes {active}")  # noqa: T201
    if problems:
        print("UNGUARDED SINK — a call site of a registered sink class has no guard nearby:")  # noqa: T201
        for problem in problems:
            print(f"  - {problem}")  # noqa: T201
        print(  # noqa: T201
            "\nRoute the call through the guard, or if the input is genuinely "
            "trusted, add `# sink-guard-exempt: <reason>` on or above the line."
        )
        return 1
    print("OK: every sink call site of a registered class is guarded (or explicitly exempt).")  # noqa: T201
    return 0


def _self_test() -> int:
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    http_guard = re.compile(r"url_safety\.check")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Case 1: guarded call site -> clean.
        (root / "guarded.py").write_text(
            "def fetch(url):\n"
            "    url_safety.check(url)\n"
            "    return httpx.get(url)\n"
        )
        expect(
            find_unguarded(root, {"http_guard": http_guard}) == [],
            "a sink within window of its guard must not be flagged",
        )
        (root / "guarded.py").unlink()

        # Case 2 (the mutation): 13 guarded call sites, a 14th added with no
        # guard call nearby — exactly today's failure shape (1 of 14 wired).
        body = "".join(
            f"def fetch_{n}(url):\n    url_safety.check(url)\n    return httpx.get(url)\n\n"
            for n in range(13)
        )
        body += "def fetch_14(url):\n    return httpx.get(url)  # forgot the guard\n"
        (root / "routes.py").write_text(body)
        problems = find_unguarded(root, {"http_guard": http_guard})
        expect(len(problems) == 1, f"exactly the unguarded 14th call site must be flagged, got {problems}")
        expect(
            bool(problems) and "fetch_14" not in problems[0] and "routes.py:" in problems[0],
            "flagged line must point at the unguarded call",
        )
        expect(
            run_check(root, {"http_guard": http_guard}, window=8) == 1,
            "run_check must fail when one sink of 14 is unguarded",
        )

        # Case 3: opt-out comment silences a genuinely trusted call site.
        (root / "trusted.py").write_text(
            "def ping_internal():\n"
            "    # sink-guard-exempt: hardcoded internal healthcheck URL\n"
            "    return httpx.get('http://localhost:9999/health')\n"
        )
        trusted_problems = [
            p for p in find_unguarded(root, {"http_guard": http_guard}) if "trusted.py" in p
        ]
        expect(
            trusted_problems == [],
            "an opt-out comment must silence that call site only",
        )
        (root / "trusted.py").unlink()

        # Case 3b: NO guard patterns configured at all must fail loud, not
        # report a vacuous OK (rule 4.10 — an unset guard is the process
        # succeeding while checking nothing, same shape as the original defect).
        expect(
            run_check(root, {"http_guard": None, "argv_guard": None, "path_guard": None}, window=8) == 1,
            "run_check with zero configured guards must fail loud, not report a vacuous pass",
        )

        # Case 4: healed (guard added to the 14th site) -> back to green.
        (root / "routes.py").write_text(body.replace("return httpx.get(url)  # forgot the guard", "url_safety.check(url)\n    return httpx.get(url)"))
        expect(
            run_check(root, {"http_guard": http_guard}, window=8) == 0,
            "run_check must pass once every sink is guarded again",
        )

    if failures:
        print("SELF-TEST FAILED:")  # noqa: T201
        for failure in failures:
            print(f"  - {failure}")  # noqa: T201
        return 1
    print("SELF-TEST OK: sink-coverage gate behaves as specified.")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="repo root to scan")
    parser.add_argument("--http-guard", help="regex matching a call to the outbound-HTTP guard")
    parser.add_argument("--argv-guard", help="regex matching a call to the subprocess-argv guard")
    parser.add_argument("--path-guard", help="regex matching a call to the path-containment guard")
    parser.add_argument("--window", type=int, default=8)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.root:
        parser.error("--root is required (or pass --self-test)")
    guards = {
        "http_guard": re.compile(args.http_guard) if args.http_guard else None,
        "argv_guard": re.compile(args.argv_guard) if args.argv_guard else None,
        "path_guard": re.compile(args.path_guard) if args.path_guard else None,
    }
    return run_check(Path(args.root), guards, args.window)


if __name__ == "__main__":
    sys.exit(main())
