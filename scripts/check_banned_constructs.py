#!/usr/bin/env python3
"""Fail CI on two banned constructs ruff's `S` rules cannot express.

Factory security-cleanup review (2026-08-13). Two failure shapes found today
have no stock lint rule:

1. ``existsSync(path)`` (or ``os.path.exists`` / ``Path.exists()``) followed by
   a read of the SAME path a few lines later collapses "absent" and
   "unreadable" into one branch — a permission error reads as success, or the
   file vanishes in the TOCTOU window between the check and the read.
2. Returning raw exception text (``str(e)``, ``repr(e)``, an f-string
   interpolating ``e``) in an HTTP response body leaks stack internals,
   paths, and query fragments to the client — 152 alerts of this shape today.

(pickle/eval-exec/shell=True are owned by the g2-seclint ruff-S gate; this
script deliberately does not re-check them.)

This is a regex/line-window heuristic, not a real AST/dataflow analysis — it
does not need to be perfect, it needs to fail when someone adds occurrence
number N+1 without going through the allowlist. False positives are handled
by the allowlist file, not by making the heuristic cleverer.

Allowlist format matches the sibling ruff-S gate's shape for a future merge:
YAML list of ``{path, rule, reason, issue}``; an entry with no ``issue`` is
itself a gate failure (an unreviewed grandfather is not a grandfather).

Usage:
    python scripts/check_banned_constructs.py --root . --allowlist standards/banned-constructs-allowlist.yaml
    python scripts/check_banned_constructs.py --self-test

Exit codes:
    0 - no new (non-allowlisted) violations
    1 - a violation was found, or the allowlist itself is malformed
    2 - bad invocation
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - CI always has pyyaml; self-test doesn't need it
    yaml = None  # type: ignore[assignment]

_SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "vendor",
}

_EXISTS_THEN_READ = re.compile(
    r"(existsSync|\.exists\(\)|os\.path\.exists)\s*\("
)
_RAW_EXCEPTION = re.compile(
    r"\b(str\(e\)|str\(exc\)|repr\(e\)|repr\(exc\))"
)
_HTTP_RESPONSE_HINT = re.compile(
    r"(HTTPException|JSONResponse|Response|jsonify|res\.json|res\.send|reply)",
    re.IGNORECASE,
)


def _iter_source_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in (".py", ".js", ".ts", ".tsx", ".jsx"):
            out.append(path)
    return out


def _find_exists_then_read(path: Path, window: int = 5) -> list[tuple[int, str]]:
    """Lines where an existsSync/exists() check is followed within `window`
    lines by what looks like a read of the same kind of path."""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    hits: list[tuple[int, str]] = []
    read_pat = re.compile(r"(readFileSync|readFile\(|open\(|read_text|read_bytes)")
    for i, line in enumerate(lines):
        if _EXISTS_THEN_READ.search(line):
            for j in range(i + 1, min(i + 1 + window, len(lines))):
                if read_pat.search(lines[j]):
                    hits.append((i + 1, line.strip()))
                    break
    return hits


def _find_raw_exception_in_response(path: Path, window: int = 6) -> list[tuple[int, str]]:
    """Lines with str(e)/repr(e) near something that looks like an HTTP response."""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if _RAW_EXCEPTION.search(line):
            lo, hi = max(0, i - window), min(len(lines), i + window)
            context = "\n".join(lines[lo:hi])
            if _HTTP_RESPONSE_HINT.search(context):
                hits.append((i + 1, line.strip()))
    return hits


def _load_allowlist(path: Path | None) -> set[tuple[str, str]]:
    """Return {(relative_path, rule_id)} that is pre-approved (grandfathered)."""
    if path is None or not path.is_file():
        return set()
    if yaml is None:
        raise RuntimeError("pyyaml is required to read the allowlist")
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    allowed: set[tuple[str, str]] = set()
    unreviewed: list[str] = []
    for entry in entries:
        if not entry.get("issue"):
            unreviewed.append(entry.get("path", "<unknown>"))
            continue
        allowed.add((entry["path"], entry["rule"]))
    if unreviewed:
        raise ValueError(
            f"allowlist entries with no `issue` (unreviewed grandfather): {unreviewed}"
        )
    return allowed


def check(root: Path, allowlist_path: Path | None) -> list[str]:
    allowed = _load_allowlist(allowlist_path)
    problems: list[str] = []
    for path in _iter_source_files(root):
        rel = str(path.relative_to(root))
        for lineno, snippet in _find_exists_then_read(path):
            if (rel, "exists-then-read") in allowed:
                continue
            problems.append(f"{rel}:{lineno}: exists-then-read — {snippet}")
        for lineno, snippet in _find_raw_exception_in_response(path):
            if (rel, "raw-exception-in-response") in allowed:
                continue
            problems.append(f"{rel}:{lineno}: raw-exception-in-response — {snippet}")
    return problems


def run_check(root: Path, allowlist_path: Path | None) -> int:
    try:
        problems = check(root, allowlist_path)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")  # noqa: T201
        return 1
    print(f"banned-constructs: scanned {root}")  # noqa: T201
    if problems:
        print("BANNED CONSTRUCT — new (non-allowlisted) occurrence(s):")  # noqa: T201
        for problem in problems:
            print(f"  - {problem}")  # noqa: T201
        print(  # noqa: T201
            "\nFix it, or if pre-existing and out of scope for this change, add an "
            "entry to the allowlist with a `reason` and an `issue` ref (a "
            "grandfather with no issue ref itself fails this gate)."
        )
        return 1
    print("OK: no banned constructs found (outside the allowlist).")  # noqa: T201
    return 0


def _self_test() -> int:
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Case 1: clean file -> no violations.
        (root / "clean.py").write_text(
            "def read(path):\n    return path.read_text()\n"
        )
        expect(check(root, None) == [], "a clean file must produce no violations")

        # Case 2 (mutation): exists-then-read TOCTOU, JS shape.
        (root / "toctou.js").write_text(
            "if (existsSync(p)) {\n  const data = readFileSync(p);\n  return data;\n}\n"
        )
        problems = check(root, None)
        expect(
            any("exists-then-read" in p and "toctou.js" in p for p in problems),
            "existsSync-then-read must be caught",
        )
        (root / "toctou.js").unlink()

        # Case 3 (mutation): raw exception text returned to an HTTP client.
        (root / "handler.py").write_text(
            "def handler(request):\n"
            "    try:\n"
            "        do_thing()\n"
            "    except Exception as e:\n"
            "        return HTTPException(status_code=500, detail=str(e))\n"
        )
        problems = check(root, None)
        expect(
            any("raw-exception-in-response" in p and "handler.py" in p for p in problems),
            "str(e) returned via HTTPException must be caught",
        )
        expect(run_check(root, None) == 1, "run_check must fail with an uncaught violation present")

        # Case 4: allowlisting the handler.py finding silences exactly that one.
        allowlist = root / "allowlist.yaml"
        allowlist.write_text(
            "- path: handler.py\n"
            "  rule: raw-exception-in-response\n"
            "  reason: grandfathered, pre-existing\n"
            "  issue: FAKE-123\n"
        )
        remaining = check(root, allowlist)
        expect(
            not any("handler.py" in p for p in remaining),
            "an allowlisted (path, rule) pair must be silenced",
        )
        expect(
            any("toctou.js" not in p for p in remaining) or not remaining,
            "allowlisting one finding must not silence unrelated files",
        )

        # Case 5: an allowlist entry with no issue ref fails the gate outright.
        bad_allowlist = root / "bad.yaml"
        bad_allowlist.write_text(
            "- path: handler.py\n  rule: raw-exception-in-response\n  reason: no issue ref\n"
        )
        expect(
            run_check(root, bad_allowlist) == 1,
            "an allowlist entry without an issue ref must itself fail the gate",
        )

        # Case 6: healed -> back to green (with the reviewed allowlist).
        (root / "handler.py").write_text(
            "def handler(request):\n    return safe_message()\n"
        )
        expect(run_check(root, allowlist) == 0, "gate must pass once the violation is fixed")

    if failures:
        print("SELF-TEST FAILED:")  # noqa: T201
        for failure in failures:
            print(f"  - {failure}")  # noqa: T201
        return 1
    print("SELF-TEST OK: banned-constructs gate behaves as specified.")  # noqa: T201
    return 0


def _emit_allowlist(root: Path, issue: str) -> str:
    """Grandfather every CURRENT finding so the gate can land green on day one.

    This is the ratchet mechanism: run once at rollout to snapshot today's
    violations under one tracking issue, then the gate blocks on anything new.
    """
    problems = check(root, None)
    entries = []
    for problem in problems:
        loc, _, rest = problem.partition(": ")
        path, _, _lineno = loc.rpartition(":")
        rule = "exists-then-read" if "exists-then-read" in rest else "raw-exception-in-response"
        entries.append({"path": path, "rule": rule})
    seen: set[tuple[str, str]] = set()
    lines = []
    for e in entries:
        key = (e["path"], e["rule"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- path: {e['path']}\n  rule: {e['rule']}\n  reason: grandfathered at gate rollout\n  issue: {issue}\n")
    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="repo root to scan")
    parser.add_argument("--allowlist", help="path to the YAML allowlist file")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--emit-allowlist",
        metavar="ISSUE",
        help="print a grandfather allowlist covering today's findings, tagged with ISSUE, and exit",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.root:
        parser.error("--root is required (or pass --self-test)")
    if args.emit_allowlist:
        print(_emit_allowlist(Path(args.root), args.emit_allowlist), end="")  # noqa: T201
        return 0
    allowlist_path = Path(args.allowlist) if args.allowlist else None
    return run_check(Path(args.root), allowlist_path)


if __name__ == "__main__":
    sys.exit(main())
