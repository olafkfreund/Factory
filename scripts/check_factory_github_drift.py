#!/usr/bin/env python3
"""Fail CI when a service's vendored VCS-client layer drifts from the canonical.

The canonical copy of the GitHub/VCS runner layer lives in the Factory hub at
``shared/factory-github/`` (the single source of truth — see that directory's
``README.md``). PFactory, AIFactory and TFactory each carry a copy under
``apps/backend/runners/github/``. RFC-0011 (auto-merge) plus routine cleanup have
already let those copies diverge; this guard stops them silently drifting further.

The check is **byte-exact and directional** (canonical -> service copy): for every
file the hub canonical defines, the matching file in the service tree must exist
and be byte-identical. Files the service carries that the canonical does not
define (service-specific helpers such as ``bot_detection.py`` or ``cleanup.py``)
are out of scope and ignored — the canonical set is exactly the deduped layer:
``gh_client.py``, ``rate_limiter.py`` and the ``providers/`` tree.

This mirrors PFactory's ``scripts/check_schema_drift.py``: pure stdlib, no third-
party imports, hard-fail (exit 1) on real drift.

Usage:
    # Check a service checkout against the hub canonical (default canonical = the
    # shared/factory-github/ tree next to this script's repo root):
    python scripts/check_factory_github_drift.py \
        --service /path/to/PFactory/apps/backend/runners/github

    # Override the canonical root explicitly:
    python scripts/check_factory_github_drift.py \
        --canonical shared/factory-github \
        --service /path/to/AIFactory/apps/backend/runners/github

    # Run the built-in self-test (no repo state needed):
    python scripts/check_factory_github_drift.py --self-test

Exit codes:
    0 - service copy matches the canonical (or self-test passed)
    1 - drift detected (or self-test failed)
    2 - bad invocation / missing canonical tree
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# The canonical layer is exactly the deduped VCS-client surface (epic Factory#154,
# issue Factory#157). Service trees may carry extra, service-specific files; those
# are intentionally NOT part of the canonical contract and are ignored.
CANONICAL_FILES: tuple[str, ...] = (
    "gh_client.py",
    "rate_limiter.py",
    "providers/__init__.py",
    "providers/protocol.py",
    "providers/factory.py",
    "providers/github_provider.py",
    "providers/gitlab_provider.py",
    "providers/azure_devops_provider.py",
)

# Default canonical root, relative to the repo that contains this script.
_DEFAULT_CANONICAL = Path(__file__).resolve().parent.parent / "shared/factory-github"

# Exit code returned when the canonical tree itself is missing (bad invocation).
_EXIT_BAD_CANONICAL = 2


def _emit(message: str) -> None:
    # This is a CLI drift gate; its stdout report IS its purpose, so the T20
    # (no-print) rule is intentionally suppressed at the single output sink.
    print(message)  # noqa: T201


def check_drift(canonical_root: Path, service_root: Path) -> list[str]:
    """Return drift problems comparing *service_root* against *canonical_root*.

    Directional and byte-exact: every file in :data:`CANONICAL_FILES` must exist
    under *service_root* and match the canonical byte-for-byte. Extra files in the
    service tree are ignored (they are service-specific, not part of the layer).
    """
    problems: list[str] = []
    for rel in CANONICAL_FILES:
        canonical_file = canonical_root / rel
        service_file = service_root / rel
        canonical_bytes = canonical_file.read_bytes()
        if not service_file.is_file():
            problems.append(f"{rel}: present in canonical, missing in service copy")
            continue
        if service_file.read_bytes() != canonical_bytes:
            problems.append(f"{rel}: differs from canonical (byte mismatch)")
    return problems


def run_check(canonical_root: Path, service_root: Path) -> int:
    """Run the drift check and emit a human-readable report. Return an exit code."""
    if not canonical_root.is_dir():
        _emit(f"ERROR: canonical tree not found: {canonical_root}")
        return _EXIT_BAD_CANONICAL
    problems = check_drift(canonical_root, service_root)
    if problems:
        _emit("factory-github drift — the service copy diverges from the canonical:")
        for problem in problems:
            _emit(f"  - {problem}")
        _emit(
            "\nThe canonical layer is shared/factory-github/ in the Factory hub. "
            "Reconcile the service copy with it (or, if the change is intentional, "
            "land it in the hub canonical first via a CODEOWNERS-reviewed PR)."
        )
        return 1
    _emit(
        f"OK: {service_root} matches the canonical factory-github layer "
        f"({len(CANONICAL_FILES)} files)."
    )
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
        (canonical / "providers").mkdir(parents=True)
        for rel in CANONICAL_FILES:
            (canonical / rel).write_text(f"# canonical {rel}\nVALUE = 1\n")

        # Case 1: an identical copy -> no drift.
        identical = root / "identical"
        (identical / "providers").mkdir(parents=True)
        for rel in CANONICAL_FILES:
            (identical / rel).write_bytes((canonical / rel).read_bytes())
        expect(check_drift(canonical, identical) == [], "identical copy must not drift")

        # Case 2: extra service-specific file is ignored (not part of the layer).
        (identical / "bot_detection.py").write_text("# service-only helper\n")
        expect(
            check_drift(canonical, identical) == [],
            "extra service-only file must be ignored",
        )

        # Case 3: a one-byte change in a tracked file -> drift on exactly that file.
        modified = root / "modified"
        (modified / "providers").mkdir(parents=True)
        for rel in CANONICAL_FILES:
            (modified / rel).write_bytes((canonical / rel).read_bytes())
        (modified / "gh_client.py").write_text("# canonical gh_client.py\nVALUE = 2\n")
        problems = check_drift(canonical, modified)
        expect(len(problems) == 1, "single change must yield exactly one problem")
        expect(
            bool(problems) and problems[0].startswith("gh_client.py"),
            "drift must be attributed to gh_client.py",
        )

        # Case 4: a missing tracked file is reported as missing.
        missing = root / "missing"
        (missing / "providers").mkdir(parents=True)
        for rel in CANONICAL_FILES:
            if rel != "rate_limiter.py":
                (missing / rel).write_bytes((canonical / rel).read_bytes())
        problems = check_drift(canonical, missing)
        expect(
            any("rate_limiter.py" in p and "missing" in p for p in problems),
            "missing tracked file must be reported as missing",
        )

        # Case 5: run_check returns the right exit codes end-to-end.
        expect(run_check(canonical, identical) == 0, "run_check must pass on a match")
        expect(run_check(canonical, modified) == 1, "run_check must fail on drift")
        expect(
            run_check(root / "does-not-exist", identical) == _EXIT_BAD_CANONICAL,
            "run_check must return 2 when the canonical tree is absent",
        )

    if failures:
        _emit("SELF-TEST FAILED:")
        for failure in failures:
            _emit(f"  - {failure}")
        return 1
    _emit("SELF-TEST OK: factory-github drift gate behaves as specified.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--canonical",
        default=str(_DEFAULT_CANONICAL),
        help="path to the canonical factory-github tree (default: hub shared/)",
    )
    parser.add_argument(
        "--service",
        help="path to a service's runners/github/ tree to check",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the built-in self-test and exit",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.service:
        parser.error("--service is required (or pass --self-test)")

    return run_check(Path(args.canonical), Path(args.service))


if __name__ == "__main__":
    sys.exit(main())
