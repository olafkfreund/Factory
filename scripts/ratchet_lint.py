#!/usr/bin/env python3
"""Diff-scoped lint ratchet for the Factory hub Python (scripts/).

Implements the Factory coding-standards ratchet (coding-standards.md sections 0
and 4.6): the strict bar (`ruff` with the shared select set + `mypy --strict`)
is enforced on the files a PR changes, and a changed file MAY NOT REGRESS - i.e.
it may not gain ruff violations relative to the PR base. Untouched legacy
hotspots are allowed until touched, and the existing legacy backlog inside a
touched file does not block (a whole-repo strict gate would be instantly red:
the hub's scripts/ carry pre-existing S/BLE/PL/T20 debt at adoption). New code
and any net-new violation a PR introduces are blocked.

Mechanism: for each changed Python file, count ruff violations (shared config)
at the PR base and at HEAD; fail if HEAD has more. `ruff format` reflowing legacy
lines never increases the count, so a pure-cleanup PR stays green while genuine
new violations are caught.

This module is intentionally vendored verbatim from CFactory's reference
implementation (cross-service reuse of the proven Factory ratchet); only the
default package scope differs (the hub's first-class Python is the flat
`scripts/` dir, not a package).

Usage:
    python scripts/ratchet_lint.py --base <git-ref> [--package <dir>]

Exit code 0 if no changed file regressed; 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

PACKAGE_DEFAULT = "scripts"


def _emit(message: str) -> None:
    # This is a CLI lint tool; its stdout report IS its purpose, so the T20
    # (no-print) rule is intentionally suppressed at the single output sink.
    print(message)  # noqa: T201


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    # cmd is built from constant git/ruff argv plus repo-internal paths, not
    # untrusted input; this lint tool legitimately shells out to git and ruff.
    return subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603


def changed_python_files(base: str, package: str) -> list[str]:
    """Python files under *package* changed (added/modified) vs *base*."""
    res = _run(["git", "diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD"])
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        sys.exit(2)
    pkg = Path(package)
    out: list[str] = []
    for line in res.stdout.splitlines():
        path = Path(line)
        # `pkg in path.parents` matches both nested packages and a flat dir like
        # scripts/ (for scripts/foo.py, parents == [scripts, .]).
        if path.suffix == ".py" and pkg in path.parents and path.exists():
            out.append(str(path))
    return out


def ruff_counts(source: str, filename: str) -> Counter[str]:
    """Per-rule ruff violation counts for *source* checked as *filename*."""
    # Write under the REAL basename inside a temp dir: a random-prefixed name
    # (the old NamedTemporaryFile suffix trick) defeats per-file-ignores like
    # `**/test_*.py`, so test files were held to the non-test bar.
    tmpdir = tempfile.mkdtemp()
    tmp = str(Path(tmpdir) / Path(filename).name)
    Path(tmp).write_text(source)
    try:
        res = _run(["ruff", "check", "--config", "ruff.toml", "--output-format", "json", tmp])
        if not res.stdout.strip():
            return Counter()
        try:
            items = json.loads(res.stdout)
        except json.JSONDecodeError:
            sys.stderr.write(res.stdout + res.stderr)
            sys.exit(2)
        return Counter(item["code"] for item in items)
    finally:
        Path(tmp).unlink(missing_ok=True)
        Path(tmpdir).rmdir()


def file_at_base(base: str, path: str) -> str | None:
    res = _run(["git", "show", f"{base}:{path}"])
    return res.stdout if res.returncode == 0 else None


def regressions(base: str, path: str) -> list[str]:
    head_src = Path(path).read_text()
    head_counts = ruff_counts(head_src, path)
    base_src = file_at_base(base, path)
    base_counts = ruff_counts(base_src, path) if base_src is not None else Counter()
    out: list[str] = []
    for code, head_n in head_counts.items():
        base_n = base_counts.get(code, 0)
        if head_n > base_n:
            out.append(f"{path}: {code} +{head_n - base_n} (base {base_n} -> head {head_n})")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="git ref to diff against")
    parser.add_argument("--package", default=PACKAGE_DEFAULT)
    args = parser.parse_args()

    files = changed_python_files(args.base, args.package)
    if not files:
        _emit(f"ratchet: no changed Python files under {args.package}; nothing to gate.")
        return 0

    _emit("ratchet: gating changed files:\n  " + "\n  ".join(files))

    all_regressions: list[str] = []
    for path in files:
        all_regressions.extend(regressions(args.base, path))

    if all_regressions:
        _emit("\nratchet FAILED: changed files gained ruff violations (shared strict bar):")
        for line in all_regressions:
            _emit(f"  {line}")
        _emit(
            "\nFix the new violations (or clean the file further). The ratchet only "
            "blocks NET-NEW violations - pre-existing legacy in a touched file is "
            "allowed (coding-standards.md section 4.6)."
        )
        return 1

    _emit("ratchet PASSED: no changed file regressed; new violations: none.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
