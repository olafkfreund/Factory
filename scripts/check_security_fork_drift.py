#!/usr/bin/env python3
"""Fail CI when a security-relevant file forked across sibling repos diverges.

Factory security-cleanup review (2026-08-13). CodeQL reports per-repo, so an
unscanned fork reads clean even when its sibling copy carries a live bug.
Today's evidence, five separate times: ``artifact_store.py`` (tarslip), an
SSRF guard, a workspace lock permission (0o644), ``skills_service.py``
(pickle-vs-JSON), ``bump-version.js`` (fs-race). Each was fixed in one repo
while the others kept the bug, because nothing compared the copies.

This is deliberately NOT the same shape as ``check_factory_github_drift.py``
et al: those check a formally vendored hub-canonical -> service copy
relationship with one fixed relative path. These files were never vendored —
they were pasted independently, so they live at DIFFERENT relative paths in
each repo and there is no single hub "source of truth" to diff against. The
registry below records, per logical file, the repo-relative path in each repo
that carries a copy (``None`` where a repo has no copy — that repo is simply
excluded from the comparison, not a failure by itself). The gate asserts every
PRESENT copy is byte-identical to every other present copy.

A repo missing a copy entirely is not drift (nothing to compare); a repo
whose copy differs in bytes from the others IS drift, and CI must fail.

Usage:
    python scripts/check_security_fork_drift.py --fleet-root /path/to/GitHub
        # fleet-root contains Factory/, PFactory/, AIFactory/, TFactory/, CFactory/

    python scripts/check_security_fork_drift.py --self-test

Exit codes:
    0 - every registered file's present copies match
    1 - drift detected
    2 - bad invocation
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from gate_evidence import digest

# Registry: logical name -> {repo_name: repo-relative path or None}.
# Built from what is ACTUALLY duplicated today (found by hashing candidate
# paths across the fleet checkout), not guessed. See the report accompanying
# this gate for how each entry was found. `None` = repo has no copy of this
# file; it is simply skipped for that repo, not treated as a violation.
REGISTRY: dict[str, dict[str, str | None]] = {
    "artifact_store.py (tarslip guard)": {
        "Factory": "scripts/artifact_store.py",
        "PFactory": "apps/backend/runners/artifact_store.py",
        "AIFactory": "apps/backend/core/artifact_store.py",
        "TFactory": "apps/backend/tools/runners/artifact_store.py",
        "CFactory": None,
    },
    "skills_service.py (pickle cache loader)": {
        "PFactory": "apps/web-server/server/services/skills_service.py",
        "AIFactory": "apps/web-server/server/services/skills_service.py",
    },
}


def _repo_root(fleet_root: Path, repo: str) -> Path:
    return fleet_root / repo


def check_drift(fleet_root: Path) -> list[str]:
    """Return one problem string per logical file whose present copies diverge."""
    problems: list[str] = []
    for name, copies in REGISTRY.items():
        present = {
            repo: (_repo_root(fleet_root, repo) / rel)
            for repo, rel in copies.items()
            if rel is not None
        }
        present = {repo: path for repo, path in present.items() if path.is_file()}
        if len(present) < 2:
            continue  # nothing to compare — 0 or 1 present copies
        digests = {repo: path.read_bytes() for repo, path in present.items()}
        reference_repo, reference_bytes = next(iter(digests.items()))
        diverged = [
            repo for repo, data in digests.items() if data != reference_bytes
        ]
        if diverged:
            cited = ", ".join(
                f"{repo}={digest(path)}" for repo, path in present.items()
            )
            problems.append(
                f"{name}: copies diverge across repos ({cited}); "
                f"reference was {reference_repo}"
            )
    return problems


def run_check(fleet_root: Path) -> int:
    problems = check_drift(fleet_root)
    print(f"security-fork-drift: fleet root {fleet_root}, {len(REGISTRY)} registered file(s)")  # noqa: T201
    if problems:
        print("DRIFT DETECTED — a security-relevant forked file diverges between repos:")  # noqa: T201
        for problem in problems:
            print(f"  - {problem}")  # noqa: T201
        print(  # noqa: T201
            "\nA fix landed in one repo has not propagated to its sibling(s). "
            "Port the fix, or if the divergence is intentional, split the "
            "registry entry or document why the copies are allowed to differ."
        )
        return 1
    print("OK: every registered security-relevant file's present copies match.")  # noqa: T201
    return 0


def _self_test() -> int:
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for repo in ("RepoA", "RepoB", "RepoC"):
            (root / repo / "sub").mkdir(parents=True)

        registry_backup = dict(REGISTRY)
        try:
            REGISTRY.clear()
            REGISTRY["thing.py"] = {
                "RepoA": "sub/thing.py",
                "RepoB": "sub/thing.py",
                "RepoC": "sub/thing.py",
            }

            # Case 1: all three identical -> no drift.
            for repo in ("RepoA", "RepoB", "RepoC"):
                (root / repo / "sub" / "thing.py").write_text("SAFE = 1\n")
            expect(check_drift(root) == [], "identical copies must not drift")

            # Case 2: one repo has no copy at all -> not a failure (nothing to
            # compare it against is not drift).
            (root / "RepoC" / "sub" / "thing.py").unlink()
            expect(
                check_drift(root) == [],
                "a missing copy must not itself count as drift",
            )
            (root / "RepoC" / "sub" / "thing.py").write_text("SAFE = 1\n")

            # Case 3 (the mutation): RepoB's copy silently reverts to the
            # vulnerable version while RepoA and RepoC carry the fix. This is
            # exactly today's failure shape.
            (root / "RepoB" / "sub" / "thing.py").write_text("SAFE = 0  # bug reintroduced\n")
            problems = check_drift(root)
            expect(len(problems) == 1, f"exactly one logical file must drift, got {problems}")
            expect(
                bool(problems) and "thing.py" in problems[0],
                "drift must be attributed to the diverged logical file",
            )
            expect(run_check(root) == 1, "run_check must return 1 when a fork diverges")

            # Case 4: heal it -> back to green.
            (root / "RepoB" / "sub" / "thing.py").write_text("SAFE = 1\n")
            expect(run_check(root) == 0, "run_check must return 0 once copies match again")
        finally:
            REGISTRY.clear()
            REGISTRY.update(registry_backup)

    if failures:
        print("SELF-TEST FAILED:")  # noqa: T201
        for failure in failures:
            print(f"  - {failure}")  # noqa: T201
        return 1
    print("SELF-TEST OK: security-fork-drift gate behaves as specified.")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fleet-root",
        help="directory containing Factory/, PFactory/, AIFactory/, TFactory/, CFactory/ checkouts",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.fleet_root:
        parser.error("--fleet-root is required (or pass --self-test)")
    return run_check(Path(args.fleet_root))


if __name__ == "__main__":
    sys.exit(main())
