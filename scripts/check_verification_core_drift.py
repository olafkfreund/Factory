#!/usr/bin/env python3
"""Fail CI when a service's vendored verification-core modules drift from the hub.

The canonical copies of the Factory verification-core layer live in this hub at
``scripts/`` (the single source of truth — see ``scripts/README-verification-core.md``).
PFactory, AIFactory and TFactory each hand-vendor a subset of these modules into
their own backends (at service-specific paths). This guard stops those copies
silently diverging from the hub canonical.

The canonical set is exactly the deduped verification-core surface (epic
Factory#154, issue Factory#158):

    verification_gate.py     RFC-0006 never-overclaim gate
    verification_profiles.py verification profile selection
    verification_runner.py   verification lane runner
    factory_sandbox.py       unprivileged-sandbox helper
    nix_provisioner.py       per-task Nix environment provisioner

The check is **byte-exact and directional** (hub canonical -> service copy): for
every canonical module a service is known to vendor, the matching file in the
service tree must exist and be byte-identical to the hub copy. Because the three
services vendor *different subsets* at *different paths*, the per-service vendored
layout is described by :data:`SERVICE_LAYOUTS`; only modules a service actually
carries are checked (a service that does not vendor a module is not penalised for
its absence).

This mirrors ``scripts/check_factory_github_drift.py``: pure stdlib, no third-
party imports, hard-fail (exit 1) on real drift.

KNOWN DRIFT (documented, not a bug in this gate): TFactory's
``verification_gate.py`` was reconciled to its local lint bar — the loop variable
was renamed (``l`` -> ``lvl`` for E741), the TypedDict definitions were dropped in
favour of plain ``dict`` hints, and the module-level self-tests were removed. The
gate will therefore flag TFactory's gate copy until it is reconciled back to the
hub canonical. Reconciling the service copy (behaviour-preserving) is a tracked,
deferred follow-on — see ``scripts/README-verification-core.md``.

Usage:
    # Check a known service checkout against the hub canonical:
    python scripts/check_verification_core_drift.py \
        --service tfactory --root /path/to/TFactory

    # List which modules each known service is expected to vendor:
    python scripts/check_verification_core_drift.py --list

    # Override the canonical root explicitly (default: this script's scripts/):
    python scripts/check_verification_core_drift.py \
        --canonical scripts --service aifactory --root /path/to/AIFactory

    # Run the built-in self-test (no repo state needed):
    python scripts/check_verification_core_drift.py --self-test

Exit codes:
    0 - service copies match the canonical (or self-test/list succeeded)
    1 - drift detected (or self-test failed)
    2 - bad invocation / missing canonical tree / unknown service
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# The canonical layer is exactly the deduped verification-core surface (epic
# Factory#154, issue Factory#158). These filenames are the canonical module names
# as they live, flat, in the hub's scripts/ directory.
CANONICAL_MODULES: tuple[str, ...] = (
    "verification_gate.py",
    "verification_profiles.py",
    "verification_runner.py",
    "factory_sandbox.py",
    "nix_provisioner.py",
)

# Per-service vendored layout: which canonical modules each service hand-vendors,
# and the path (relative to that service's repo root) where its copy lives. The
# services deliberately vendor *different subsets* at *different paths*, so this
# map is the contract for what the gate looks for. A service entry that omits a
# canonical module simply means that service does not vendor it (and so it is not
# checked there) — only divergence of a *vendored* copy is drift.
SERVICE_LAYOUTS: dict[str, dict[str, str]] = {
    "pfactory": {},
    "aifactory": {
        "factory_sandbox.py": "apps/backend/core/factory_sandbox.py",
        "nix_provisioner.py": "apps/backend/core/nix_provisioner.py",
    },
    "tfactory": {
        "verification_gate.py": "apps/backend/agents/verification_gate.py",
        "nix_provisioner.py": "apps/backend/tools/runners/nix_provisioner.py",
    },
}

# Default canonical root, relative to the repo that contains this script: the
# hub's scripts/ directory (i.e. the directory this file lives in).
_DEFAULT_CANONICAL = Path(__file__).resolve().parent

# Exit code returned for a bad invocation (missing canonical / unknown service).
_EXIT_BAD_INVOCATION = 2


def _emit(message: str) -> None:
    # This is a CLI drift gate; its stdout report IS its purpose, so the T20
    # (no-print) rule is intentionally suppressed at the single output sink.
    print(message)  # noqa: T201


def check_drift(
    canonical_root: Path,
    service_root: Path,
    layout: dict[str, str],
) -> list[str]:
    """Return drift problems comparing a service tree against the hub canonical.

    Directional and byte-exact: for every (module -> vendored path) pair in
    *layout*, the file under *service_root* must exist and match the canonical
    module under *canonical_root* byte-for-byte. Modules the service does not
    vendor (absent from *layout*) are not checked.
    """
    problems: list[str] = []
    for module, rel_path in layout.items():
        canonical_file = canonical_root / module
        service_file = service_root / rel_path
        canonical_bytes = canonical_file.read_bytes()
        if not service_file.is_file():
            problems.append(f"{module}: present in canonical, missing in service copy ({rel_path})")
            continue
        if service_file.read_bytes() != canonical_bytes:
            problems.append(f"{module}: differs from canonical (byte mismatch at {rel_path})")
    return problems


def run_check(canonical_root: Path, service_root: Path, service: str) -> int:
    """Run the drift check for one service and emit a report. Return an exit code."""
    if not canonical_root.is_dir():
        _emit(f"ERROR: canonical tree not found: {canonical_root}")
        return _EXIT_BAD_INVOCATION
    layout = SERVICE_LAYOUTS.get(service)
    if layout is None:
        _emit(f"ERROR: unknown service {service!r}; known: {', '.join(sorted(SERVICE_LAYOUTS))}")
        return _EXIT_BAD_INVOCATION
    if not layout:
        _emit(f"OK: {service} vendors no verification-core modules (nothing to check).")
        return 0
    problems = check_drift(canonical_root, service_root, layout)
    if problems:
        _emit(f"verification-core drift — {service} diverges from the hub canonical:")
        for problem in problems:
            _emit(f"  - {problem}")
        _emit(
            "\nThe canonical layer is the Factory hub's scripts/ "
            "(see scripts/README-verification-core.md). Reconcile the service copy "
            "with it (or, if the change is intentional, land it in the hub canonical "
            "first via a CODEOWNERS-reviewed PR, then re-vendor)."
        )
        return 1
    _emit(
        f"OK: {service} matches the canonical verification-core layer "
        f"({len(layout)} vendored module(s))."
    )
    return 0


def _list_layouts() -> int:
    """Print the per-service vendored layout (what the gate looks for where)."""
    _emit("verification-core canonical modules (hub scripts/):")
    for module in CANONICAL_MODULES:
        _emit(f"  - {module}")
    _emit("\nper-service vendored layout:")
    for service in sorted(SERVICE_LAYOUTS):
        layout = SERVICE_LAYOUTS[service]
        if not layout:
            _emit(f"  {service}: (vendors none)")
            continue
        _emit(f"  {service}:")
        for module, rel_path in sorted(layout.items()):
            _emit(f"    {module} -> {rel_path}")
    return 0


def _self_test() -> int:
    """Exercise the drift logic on a synthetic canonical/service pair.

    Dependency-free and self-contained: builds tiny throwaway trees in a tmp dir
    so the gate's own logic is verified without touching any real repo.
    """
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        canonical = root / "canonical"
        canonical.mkdir(parents=True)
        for module in CANONICAL_MODULES:
            (canonical / module).write_text(f"# canonical {module}\nVALUE = 1\n")

        # A representative two-module layout vendored at nested service paths.
        layout = {
            "verification_gate.py": "apps/backend/agents/verification_gate.py",
            "nix_provisioner.py": "apps/backend/tools/runners/nix_provisioner.py",
        }

        def make_service(name: str) -> Path:
            svc = root / name
            for module, rel_path in layout.items():
                target = svc / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((canonical / module).read_bytes())
            return svc

        # Case 1: an identical copy -> no drift.
        identical = make_service("identical")
        expect(check_drift(canonical, identical, layout) == [], "identical copy must not drift")

        # Case 2: extra service-specific file is ignored (not part of the layer).
        (identical / "apps/backend/agents/local_helper.py").write_text("# service-only\n")
        expect(
            check_drift(canonical, identical, layout) == [],
            "extra service-only file must be ignored",
        )

        # Case 3: a byte change in a vendored file -> drift on exactly that module.
        modified = make_service("modified")
        (modified / "apps/backend/agents/verification_gate.py").write_text(
            "# canonical verification_gate.py\nVALUE = 2\n"
        )
        problems = check_drift(canonical, modified, layout)
        expect(len(problems) == 1, "single change must yield exactly one problem")
        expect(
            bool(problems) and problems[0].startswith("verification_gate.py"),
            "drift must be attributed to verification_gate.py",
        )

        # Case 4: a missing vendored file is reported as missing.
        missing = root / "missing"
        (missing / "apps/backend/tools/runners").mkdir(parents=True)
        (missing / "apps/backend/tools/runners/nix_provisioner.py").write_bytes(
            (canonical / "nix_provisioner.py").read_bytes()
        )
        problems = check_drift(canonical, missing, layout)
        expect(
            any("verification_gate.py" in p and "missing" in p for p in problems),
            "missing vendored file must be reported as missing",
        )

        # Case 5: a module the service does NOT vendor is not checked.
        partial_layout = {"nix_provisioner.py": "apps/backend/tools/runners/nix_provisioner.py"}
        partial = root / "partial"
        (partial / "apps/backend/tools/runners").mkdir(parents=True)
        (partial / "apps/backend/tools/runners/nix_provisioner.py").write_bytes(
            (canonical / "nix_provisioner.py").read_bytes()
        )
        expect(
            check_drift(canonical, partial, partial_layout) == [],
            "un-vendored modules must not be checked",
        )

        # Case 6: run_check end-to-end via a temporary service entry.
        SERVICE_LAYOUTS["__selftest__"] = layout
        try:
            expect(
                run_check(canonical, identical, "__selftest__") == 0,
                "run_check must pass on a match",
            )
            expect(
                run_check(canonical, modified, "__selftest__") == 1,
                "run_check must fail on drift",
            )
            expect(
                run_check(root / "nope", identical, "__selftest__") == _EXIT_BAD_INVOCATION,
                "run_check must return 2 when the canonical tree is absent",
            )
            expect(
                run_check(canonical, identical, "__unknown__") == _EXIT_BAD_INVOCATION,
                "run_check must return 2 for an unknown service",
            )
        finally:
            del SERVICE_LAYOUTS["__selftest__"]

        # Case 7: an empty layout (a service that vendors nothing) passes trivially.
        expect(check_drift(canonical, identical, {}) == [], "empty layout must not drift")

    if failures:
        _emit("SELF-TEST FAILED:")
        for failure in failures:
            _emit(f"  - {failure}")
        return 1
    _emit("SELF-TEST OK: verification-core drift gate behaves as specified.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--canonical",
        default=str(_DEFAULT_CANONICAL),
        help="path to the canonical verification-core tree (default: hub scripts/)",
    )
    parser.add_argument(
        "--service",
        choices=sorted(SERVICE_LAYOUTS),
        help="which known service to check",
    )
    parser.add_argument(
        "--root",
        help="path to the service's repo root (vendored paths are relative to it)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the per-service vendored layout and exit",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the built-in self-test and exit",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.list:
        return _list_layouts()

    if not args.service:
        parser.error("--service is required (or pass --self-test / --list)")
    if not args.root:
        parser.error("--root is required when --service is given")

    return run_check(Path(args.canonical), Path(args.root), args.service)


if __name__ == "__main__":
    sys.exit(main())
