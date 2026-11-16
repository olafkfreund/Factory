#!/usr/bin/env python3
"""Fail CI when a service's vendored agent_sandbox package drifts from the hub.

The canonical package lives at ``shared/factory-sandbox/agent_sandbox/``
(Factory#3709). AIFactory, PFactory and TFactory each vendor a byte-identical
copy at ``apps/backend/agent_sandbox/``. Byte-exact and directional: every file
in ``CANONICAL_FILES`` must exist in the service copy and match; extra service
files are ignored.

Usage:
    python scripts/check_factory_sandbox_drift.py --service apps/backend/agent_sandbox
    python scripts/check_factory_sandbox_drift.py --self-test

Exit codes: 0 match, 1 drift, 2 missing canonical tree.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from gate_evidence import digest

CANONICAL_FILES: tuple[str, ...] = ("__init__.py", "env.py", "git_pins.py", "policy.py")

_DEFAULT_CANONICAL = Path(__file__).resolve().parent.parent / "shared/factory-sandbox/agent_sandbox"
_EXIT_BAD_CANONICAL = 2


def _emit(message: str) -> None:
    print(message)  # noqa: T201 - a CLI gate's report is its output


def check_drift(canonical_root: Path, service_root: Path) -> list[str]:
    """Return drift problems; the contract list is checked against the tree first."""
    listed = set(CANONICAL_FILES)
    problems = [
        f"{p.name}: in the canonical but not listed in CANONICAL_FILES"
        for p in sorted(canonical_root.glob("*.py"))
        if p.name not in listed
    ]
    for rel in CANONICAL_FILES:
        mine = service_root / rel
        if not mine.is_file():
            problems.append(f"{rel}: present in canonical, missing in service copy")
        elif mine.read_bytes() != (canonical_root / rel).read_bytes():
            problems.append(f"{rel}: differs from canonical (byte mismatch)")
    return problems


def run_check(canonical_root: Path, service_root: Path) -> int:
    """Report and return the exit code."""
    if not canonical_root.is_dir():
        _emit(f"ERROR: canonical tree not found: {canonical_root}")
        return _EXIT_BAD_CANONICAL
    problems = check_drift(canonical_root, service_root)
    _emit(f"factory-sandbox: {service_root} vs {canonical_root}")
    for rel in CANONICAL_FILES:
        c, s = canonical_root / rel, service_root / rel
        _emit(f"  - {rel} [canonical {digest(c)} | service {digest(s)}]")
    if problems:
        _emit("factory-sandbox drift:")
        for problem in problems:
            _emit(f"  - {problem}")
        _emit("Reconcile with shared/factory-sandbox/ in the Factory hub (hub first).")
        return 1
    _emit("OK: the service copy matches the canonical package.")
    return 0


def _self_test() -> int:
    """Check the gate on throwaway trees."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        canonical, service = root / "c", root / "s"
        canonical.mkdir()
        service.mkdir()
        for rel in CANONICAL_FILES:
            (canonical / rel).write_text(f"# {rel}\n")
            (service / rel).write_text(f"# {rel}\n")
        if check_drift(canonical, service):
            failures.append("identical copy must not drift")
        (service / "extra.py").write_text("x = 1\n")
        if check_drift(canonical, service):
            failures.append("extra service file must be ignored")
        (service / "env.py").write_text("# changed\n")
        if len(check_drift(canonical, service)) != 1:
            failures.append("one changed file must give one problem")
        (service / "env.py").unlink()
        if not any("missing" in p for p in check_drift(canonical, service)):
            failures.append("missing file must be reported")
        (canonical / "new.py").write_text("y = 1\n")
        if not any("not listed" in p for p in check_drift(canonical, canonical)):
            failures.append("unlisted canonical file must be reported")
        if run_check(root / "nope", service) != _EXIT_BAD_CANONICAL:
            failures.append("absent canonical must exit 2")
    for failure in failures:
        _emit(f"SELF-TEST FAILED: {failure}")
    if not failures:
        _emit("SELF-TEST OK: factory-sandbox drift gate behaves as specified.")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", default=str(_DEFAULT_CANONICAL))
    parser.add_argument("--service", help="the service's agent_sandbox/ directory")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not args.service:
        parser.error("--service is required (or pass --self-test)")
    return run_check(Path(args.canonical), Path(args.service))


if __name__ == "__main__":
    sys.exit(main())
